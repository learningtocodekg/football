import math
from engine.physics import (
    PlayerState, PlayerAttrs, BACKPEDAL_SPEED_FRACTION,
    CUT_RECOVERY_BASE_STEPS, CUT_ANGLE_THRESHOLD, PLAYER_RADIUS,
)
from engine.ball import (
    BallState, solve_arc, max_ball_speed, max_range, ARC_ANGLES, YD_S_TO_MPH,
)
from engine.resolution import (
    CB_ARM_REACH, CB_HALF_REACH, CB_VERTICAL_REACH, WR_VERTICAL_REACH, HIGH_BALL_Z,
)

FIELD_WIDTH = 53.3   # yards sideline to sideline
OOB_WARN_DIST = 3.0  # yards from sideline to trigger OOB warning in WR observation
WR_HISTORY_WINDOW = 20

# How many recent history entries to include in the prompt
HISTORY_WINDOW = 20
CB_HISTORY_WINDOW = 10

# Landing zone fuzz: starts at ±4 yd at ball release, tightens to ±0.25 yd at arrival
ZONE_FUZZ_MAX = 4.0
ZONE_FUZZ_MIN = 0.25


def _dist(a: PlayerState, b: PlayerState) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _height_label(z: float) -> str:
    """Human-readable label for a ball height in yards."""
    if z < 0.9:
        return "low (at the knees)"
    if z <= 2.0:
        return "chest-high"
    if z <= HIGH_BALL_Z:
        return "above the shoulders"
    return "high point (full extension)"


def _accel_status(cut_recovery: int) -> str:
    """Human-readable burst acceleration status based on cut_recovery steps remaining."""
    if cut_recovery == 0:
        return "FULL burst available"
    frac = cut_recovery / CUT_RECOVERY_BASE_STEPS
    if frac >= 0.75:
        return f"RECOVERING from cut — {cut_recovery} steps left, burst ~{int((1-frac*0.75)*100)}% (hips just turned)"
    elif frac >= 0.5:
        return f"RECOVERING from cut — {cut_recovery} steps left, burst ~{int((1-frac*0.75)*100)}% (hips mid-turn)"
    else:
        return f"RECOVERING from cut — {cut_recovery} steps left, burst ~{int((1-frac*0.75)*100)}% (almost set)"


def build_qb_observation(
    t: float,
    sack_clock: float,
    qb: PlayerState,
    qb_attrs: PlayerAttrs,
    wr: PlayerState,
    wr_attrs: PlayerAttrs,
    cb: PlayerState | None,
    cb_attrs: PlayerAttrs | None,
    ball: BallState,
    down: int = 1,
    distance: int = 10,
    history: list[dict] | None = None,
    expected_open_t: float | None = None,
    route_phases: list[tuple[float, float]] | None = None,
    wr_called_for_ball: bool = False,
    wr_call_t: float | None = None,
    wr_call_heading: float | None = None,
    broken_play: bool = False,
    detected_cut_t: float | None = None,
    route: str = "",
    wr_start: tuple[float, float] | None = None,
) -> str:
    """Lean, factual QB observation. No pre-computed throw, no editorial 'open' verdict -
    the QB anticipates from the raw positions/speeds/history. The QB only runs once the WR
    has called (heading locked), so we report off the locked call heading."""
    dist_to_wr = _dist(qb, wr)
    wr_depth = (wr.y - wr_start[1]) if wr_start is not None else None
    locked_hdg = wr_call_heading if wr_call_heading is not None else wr.heading

    lines = [
        f"=== QB DECISION  t={t:.1f}s  |  sack clock {sack_clock:.1f}s  |  {_down_str(down, distance)} ===",
        "",
    ]
    if route and route in _ROUTE_GEOMETRY:
        lines += [f"Your WR is running a {route.upper()} route: {_ROUTE_GEOMETRY[route]}", ""]

    if wr_called_for_ball and wr_call_heading is not None:
        call_str = f" at t={wr_call_t:.1f}s" if wr_call_t is not None else ""
        lines += [
            f"He has CALLED for the ball{call_str} and his heading is now LOCKED at {locked_hdg:.0f}deg "
            f"({_heading_label(locked_hdg)}) - he is committed to this path; only his speed can still change.",
            "",
        ]

    depth_str = f"  ({wr_depth:.0f}yd downfield of his snap)" if wr_depth is not None else ""
    wr_rec = (
        f"  [recovering from his cut - limited acceleration for {wr.cut_recovery} more steps]"
        if wr.cut_recovery > 0 else ""
    )
    lines += [
        "POSITIONS NOW:",
        f"  You (QB): ({qb.x:.1f}, {qb.y:.1f})",
        f"  WR: ({wr.x:.1f}, {wr.y:.1f})  heading {wr.heading:.0f}deg ({_heading_label(wr.heading)})  "
        f"speed {wr.speed:.1f} yd/s{depth_str}{wr_rec}",
    ]
    if cb is not None:
        sep = _dist(wr, cb)
        cb_rec = (
            f"  [recovering from a cut - cannot accelerate for {cb.cut_recovery} more steps]"
            if cb.cut_recovery > 0 else ""
        )
        lines += [
            f"  CB: ({cb.x:.1f}, {cb.y:.1f})  heading {cb.heading:.0f}deg  speed {cb.speed:.1f} yd/s{cb_rec}",
            f"  Separation now (center-to-center): {sep:.1f} yd.",
        ]
    else:
        lines.append("  CB: none on the field this play.")
    lines.append(
        f"  Throw distance you->WR right now: {dist_to_wr:.1f} yd.  WR top speed: {wr_attrs.max_speed:.1f} yd/s."
    )

    if history and cb is not None:
        recent = history[-HISTORY_WINDOW:]
        lines += [
            "",
            "RECENT MOVEMENT (every 0.1s - read the trend in speed and separation):",
            f"  {'t':>5}  {'WR pos':>14}  {'spd':>5}  {'CB pos':>14}  {'spd':>5}  {'sep':>5}",
        ]
        for h in recent:
            wx_h, wy_h = h["wr"]
            cx_h, cy_h = h["cb"]
            sep_h = math.hypot(wx_h - cx_h, wy_h - cy_h)
            lines.append(
                f"  {h['t']:>5.1f}  ({wx_h:5.1f},{wy_h:5.1f})  {h.get('wr_spd', 0.0):>5.1f}"
                f"  ({cx_h:5.1f},{cy_h:5.1f})  {h.get('cb_spd', 0.0):>5.1f}  {sep_h:>5.1f}"
            )

    return "\n".join(lines)


def build_cb_pre_snap_observation(
    cb: PlayerState,
    cb_attrs: PlayerAttrs,
    wr: PlayerState,
) -> str:
    """Observation for the CB's one-time pre-snap alignment decision."""
    sep = _dist(cb, wr)
    backpedal_speed = cb_attrs.max_speed * BACKPEDAL_SPEED_FRACTION

    lines = [
        "=== CB PRE-SNAP OBSERVATION ===",
        "",
        f"WR starting pos: ({wr.x:.1f}, {wr.y:.1f})",
        f"YOUR starting pos: ({cb.x:.1f}, {cb.y:.1f})",
        f"Current separation: {sep:.1f} yd",
        "",
        f"YOUR ATTRIBUTES:",
        f"  max_speed (forward):  {cb_attrs.max_speed:.1f} yd/s",
        f"  max_speed (backpedal): {backpedal_speed:.1f} yd/s",
        f"  acceleration: {cb_attrs.acceleration:.1f} yd/s²",
        f"  coverage: {cb_attrs.coverage:.0f}/99",
        f"  ball_skills: {cb_attrs.ball_skills:.0f}/99",
        "",
        "Choose your alignment before the snap:",
        "  offset_yards: distance off the WR (0=press, 5=off-coverage, 8+=deep)",
        "  side: 'inside' (shade toward field center), 'outside' (shade toward sideline), 'press' (directly over)",
    ]
    return "\n".join(lines)


def _intercept_heading(cb: PlayerState, wr: PlayerState, cb_speed: float) -> float:
    """Compute the heading CB should run to intercept WR's projected path.

    Projects the WR forward 0.5s along its current heading/speed, then returns
    the bearing from CB's current position to that projected point.  This gives
    the CB a lead angle rather than always chasing the WR's current spot.
    """
    LOOK_AHEAD = 0.5  # seconds
    wr_hdg_rad = math.radians(wr.heading)
    proj_x = wr.x + math.sin(wr_hdg_rad) * wr.speed * LOOK_AHEAD
    proj_y = wr.y + math.cos(wr_hdg_rad) * wr.speed * LOOK_AHEAD
    return math.degrees(math.atan2(proj_x - cb.x, proj_y - cb.y)) % 360.0


def _cb_situation(cb: PlayerState, wr: PlayerState, cb_attrs: PlayerAttrs) -> list[str]:
    """Raw relational geometry — no option labels or tradeoff descriptions."""
    dx = wr.x - cb.x
    dy = wr.y - cb.y
    sep = math.hypot(dx, dy)
    bearing_to_wr = math.degrees(math.atan2(dx, dy)) % 360.0
    intercept_hdg = _intercept_heading(cb, wr, cb_attrs.max_speed)

    LOOK_AHEAD = 0.5
    wr_hdg_rad = math.radians(wr.heading)
    proj_x = wr.x + math.sin(wr_hdg_rad) * wr.speed * LOOK_AHEAD
    proj_y = wr.y + math.cos(wr_hdg_rad) * wr.speed * LOOK_AHEAD

    return [
        "GEOMETRY:",
        f"  Separation: {sep:.1f} yd (body gap: {max(0.0, sep - 2*PLAYER_RADIUS):.1f} yd)  |  Bearing from you to WR: {bearing_to_wr:.0f}°",
        f"  WR projected pos in 0.5s: ({proj_x:.1f}, {proj_y:.1f})",
        f"  Bearing to reach WR's projected position: {intercept_hdg:.0f}°",
    ]


def build_cb_observation(
    t: float,
    cb: PlayerState,
    cb_attrs: PlayerAttrs,
    wr: PlayerState,
    ball: BallState,
    wr_history: list[dict] | None = None,
    ball_total_eta: float | None = None,
    cb_intent: str = "play_man",
    detected_cut_t: float | None = None,
) -> str:
    """Observation for the CB's per-step movement decision (LIVE and BALL_IN_AIR phases)."""
    sep = _dist(cb, wr)
    backpedal_speed = cb_attrs.max_speed * BACKPEDAL_SPEED_FRACTION

    dx_wr = wr.x - cb.x
    dy_wr = wr.y - cb.y
    bearing_to_wr = math.degrees(math.atan2(dx_wr, dy_wr)) % 360.0

    cb_accel_str = _accel_status(cb.cut_recovery)
    wr_accel_str = _accel_status(wr.cut_recovery)
    lines = [
        f"=== CB OBSERVATION  t={t:.1f}s ===",
        "",
        f"YOU (CB):  pos=({cb.x:.1f}, {cb.y:.1f})  speed={cb.speed:.1f}yd/s  heading={cb.heading:.0f}°  facing={cb.facing:.0f}°  mode={cb.mode}",
        f"  YOUR BURST: {cb_accel_str}",
        f"WR:        pos=({wr.x:.1f}, {wr.y:.1f})  speed={wr.speed:.1f}yd/s  heading={wr.heading:.0f}° ({_heading_label(wr.heading)})  facing={wr.facing:.0f}°",
        f"  WR BURST:  {wr_accel_str}",
        "",
    ]
    if wr.cut_recovery >= 2:
        lines += [
            f"  !! WR HIP-TURNED — {wr.cut_recovery} recovery steps left. WR cannot explode. Close hard now.",
            "",
        ]
    lines += _cb_situation(cb, wr, cb_attrs)
    lines += [
        "",
        f"YOUR SPEEDS:  forward max={cb_attrs.max_speed:.1f}yd/s  backpedal max={backpedal_speed:.1f}yd/s  peak_accel={cb_attrs.acceleration:.1f}yd/s² (tapers near top speed)",
        f"ARM REACH: PBU (swat)={CB_ARM_REACH:.1f}yd  INT (pick)={CB_HALF_REACH:.1f}yd",
    ]

    # Ball state
    if ball.state == "held":
        lines += [
            "",
            "BALL: held by QB — no throw yet.",
        ]
    elif ball.state == "in_air":
        if ball_total_eta and ball_total_eta > 0:
            fuzz = ZONE_FUZZ_MAX * (ball.eta / ball_total_eta)
        else:
            fuzz = ZONE_FUZZ_MAX
        fuzz = max(ZONE_FUZZ_MIN, fuzz)

        dist_to_zone = math.hypot(cb.x - ball.landing_x, cb.y - ball.landing_y)
        bearing_to_zone = math.degrees(math.atan2(
            ball.landing_x - cb.x, ball.landing_y - cb.y
        )) % 360.0

        arm_tip_x = cb.x + math.sin(math.radians(cb.facing)) * CB_ARM_REACH
        arm_tip_y = cb.y + math.cos(math.radians(cb.facing)) * CB_ARM_REACH
        arm_dist_to_zone = math.hypot(arm_tip_x - ball.landing_x, arm_tip_y - ball.landing_y)

        bearing_to_wr_now = math.degrees(math.atan2(wr.x - cb.x, wr.y - cb.y)) % 360.0
        if cb_intent == "play_man":
            facing_instruction = (
                f"INTENT=play_man: face the WR ({bearing_to_wr_now:.0f}°), not the ball. "
                f"Use heading={bearing_to_zone:.0f}° to close on the zone, facing={bearing_to_wr_now:.0f}° toward WR."
            )
        else:
            facing_instruction = (
                f"INTENT={cb_intent}: face the landing zone to contest the ball. "
                f"Use heading={bearing_to_zone:.0f}° AND facing={bearing_to_zone:.0f}°."
            )

        lines += [
            "",
            f"BALL IN AIR (your intent: {cb_intent}):",
            f"  ETA: {ball.eta:.2f}s",
            f"  Ball height now: z={ball.z:.1f} yd ({ball.arc} arc) — arrives at z={ball.landing_z:.1f} ({_height_label(ball.landing_z)})",
            f"  Your vertical reach: {CB_VERTICAL_REACH:.1f} yd — you cannot touch the ball while it is above that.",
            f"  Landing zone center: ({ball.landing_x:.1f}, {ball.landing_y:.1f})  uncertainty: ±{fuzz:.1f} yd",
            f"  Your distance to zone center: {dist_to_zone:.1f} yd",
            f"  Heading to move toward zone: {bearing_to_zone:.0f}°",
            f"  Your arm tip (facing {cb.facing:.0f}°) is at ({arm_tip_x:.1f},{arm_tip_y:.1f}), "
            f"{arm_dist_to_zone:.1f}yd from zone center",
            f"  FACING: {facing_instruction}",
        ]
        if ball.landing_z > HIGH_BALL_Z:
            lines.append(
                f"  HIGH BALL: arrives at z={ball.landing_z:.1f} — you can only swat/pick at full extension (reduced odds)."
            )

    # WR movement history with cut_recovery
    if wr_history:
        recent = wr_history[-CB_HISTORY_WINDOW:]
        lines += [
            "",
            "WR RECENT MOVES (rec = cut_recovery steps after that move — when WR rec>0, they can't burst):",
            f"  {'t':>5}  {'WR pos':>14}  {'WR hdg':>7}  {'WR spd':>7}  {'WR rec':>7}",
        ]
        for h in recent:
            wx, wy = h["wr"]
            wr_cut = h.get("wr_cut_rec", 0)
            rec_str = f"{wr_cut}rec" if wr_cut > 0 else "free"
            lines.append(
                f"  {h['t']:>5.1f}  ({wx:5.1f},{wy:5.1f})  {h['wr_hdg']:>6.0f}°  {h.get('wr_spd', 0.0):>6.1f}  {rec_str:>7}"
            )

    # CB self-action history
    if wr_history:
        recent = wr_history[-CB_HISTORY_WINDOW:]
        cb_entries = [h for h in recent if h.get("cb_mode")]
        if cb_entries:
            lines += [
                "",
                "YOUR RECENT ACTIONS (rec = cut_recovery steps — when YOUR rec>0, you cannot burst freely):",
                f"  {'t':>5}  {'hdg':>6}  {'spd':>6}  {'rec':>6}  {'mode':<10}",
            ]
            for h in cb_entries:
                cb_cut = h.get("cb_cut_rec", 0)
                rec_str = f"{cb_cut}rec" if cb_cut > 0 else "free"
                lines.append(
                    f"  {h['t']:>5.1f}  {h['cb_hdg']:>5.0f}°  {h.get('cb_spd', 0.0):>5.1f}  {rec_str:>6}  {h.get('cb_mode', ''):<10}"
                )

    if detected_cut_t is not None:
        lines += [
            "",
            f"CUT CONFIRMED: WR made a real heading change at t={detected_cut_t:.1f}s. This is established — do not re-derive it each step.",
        ]

    return "\n".join(lines)


def build_cb_intent_observation(
    t: float,
    cb: PlayerState,
    cb_attrs: PlayerAttrs,
    wr: PlayerState,
    ball: BallState,
    ball_total_eta: float,
    cb_intent_so_far: str,
) -> str:
    """Focused observation for the CB's intent decision when ball enters the air."""
    sep = _dist(cb, wr)

    fuzz = max(ZONE_FUZZ_MIN, ZONE_FUZZ_MAX * (ball.eta / max(ball_total_eta, 0.01)))
    dist_to_zone = math.hypot(cb.x - ball.landing_x, cb.y - ball.landing_y)

    # Bearing from CB to landing zone
    dx = ball.landing_x - cb.x
    dy = ball.landing_y - cb.y
    bearing_to_ball = math.degrees(math.atan2(dx, dy)) % 360.0
    facing_diff = abs((bearing_to_ball - cb.facing + 180.0) % 360.0 - 180.0)
    zone_upfield = ball.landing_y > cb.y

    # Arm tip positions
    arm_tip_pbu_x = cb.x + math.sin(math.radians(cb.facing)) * CB_ARM_REACH
    arm_tip_pbu_y = cb.y + math.cos(math.radians(cb.facing)) * CB_ARM_REACH
    arm_tip_int_x = cb.x + math.sin(math.radians(cb.facing)) * CB_HALF_REACH
    arm_tip_int_y = cb.y + math.cos(math.radians(cb.facing)) * CB_HALF_REACH

    arm_pbu_dist = math.hypot(arm_tip_pbu_x - ball.landing_x, arm_tip_pbu_y - ball.landing_y)
    arm_int_dist = math.hypot(arm_tip_int_x - ball.landing_x, arm_tip_int_y - ball.landing_y)

    facing_ok = "YES" if facing_diff <= 60.0 else f"NO (off by {facing_diff:.0f}°)"

    zone_dir = "UPFIELD of you" if zone_upfield else "DOWNFIELD of you (toward QB)"
    wr_dist_to_zone = math.hypot(wr.x - ball.landing_x, wr.y - ball.landing_y)
    wr_speed_for_eta = max(wr.speed, 1.0)
    wr_eta_to_zone = wr_dist_to_zone / wr_speed_for_eta
    lines = [
        f"=== CB INTENT DECISION  t={t:.1f}s  ETA={ball.eta:.2f}s ===",
        "",
        f"BALL landing zone: ({ball.landing_x:.1f}, {ball.landing_y:.1f})  ±{fuzz:.1f}yd  [{zone_dir}]",
        f"BALL arrives at height z={ball.landing_z:.1f} ({_height_label(ball.landing_z)}) — your vertical reach is {CB_VERTICAL_REACH:.1f} yd."
        + (" HIGH BALL: swat/pick only at full extension (reduced odds) — playing the man may be better." if ball.landing_z > HIGH_BALL_Z else ""),
        f"  To move toward ball: heading ≈ {bearing_to_ball:.0f}°",
        f"WR pos: ({wr.x:.1f}, {wr.y:.1f})  sep from you: {sep:.2f}yd  WR speed: {wr.speed:.1f}yd/s",
        f"  WR dist to zone: {wr_dist_to_zone:.1f}yd → WR eta to zone: {wr_eta_to_zone:.2f}s",
        f"YOUR pos: ({cb.x:.1f}, {cb.y:.1f})  facing={cb.facing:.0f}°  speed={cb.speed:.1f}yd/s",
        "",
        f"GEOMETRY CHECK:",
        f"  Bearing to ball: {bearing_to_ball:.0f}°  Your facing: {cb.facing:.0f}°",
        f"  Facing within 60° of ball? {facing_ok}",
        f"  PBU arm tip ({CB_ARM_REACH:.1f}yd reach): ({arm_tip_pbu_x:.1f},{arm_tip_pbu_y:.1f})  dist to zone={arm_pbu_dist:.1f}yd",
        f"  INT arm tip ({CB_HALF_REACH:.1f}yd reach): ({arm_tip_int_x:.1f},{arm_tip_int_y:.1f})  dist to zone={arm_int_dist:.1f}yd",
        f"  Distance to zone center: {dist_to_zone:.1f}yd",
        f"  Your top speed: {cb_attrs.max_speed:.1f}yd/s → sprint time to zone: {dist_to_zone/cb_attrs.max_speed:.2f}s  vs  ball ETA: {ball.eta:.2f}s",
        "",
        "CHOOSE: 'go_for_pick', 'swat', or 'play_man'",
        "  go_for_pick: INT attempt (0.5yd reach, must be facing ball, arm on path) — risky, high reward",
        "  swat: PBU attempt (1.0yd reach, must be facing ball, arm on path) — safer disruption",
        "  play_man: hit receiver at catch (no facing req, must be within 1yd of WR) — closer hit = more likely drop",
    ]
    return "\n".join(lines)


def _wr_facing_modifier(wr: PlayerState, qb: PlayerState) -> tuple[str, float]:
    """Return (label, multiplier) for WR catch probability based on facing vs ball direction."""
    dx = qb.x - wr.x
    dy = qb.y - wr.y
    ball_bearing = math.degrees(math.atan2(dx, dy)) % 360.0
    diff = abs((ball_bearing - wr.facing + 180.0) % 360.0 - 180.0)
    if diff <= 30.0:
        return "facing QB (looking back for ball)", 1.15
    elif diff <= 90.0:
        return "sideways to QB (after cut — normal)", 1.0
    else:
        return "facing away from QB (running blind)", 0.80


# One short line per route. Depths are WR-relative (downfield from his snap spot).
# WR1 is on the LEFT, so 90°=inside (toward middle), 270°=toward his sideline.
_ROUTE_GEOMETRY: dict[str, str] = {
    "go":          "GO/FLY - sprint straight upfield (0 deg), no break. He has to beat the CB deep with pure speed; lead him over the top.",
    "slant":       "SLANT - 5yd stem, then a quick break inside across the field (45 deg). Short and fast.",
    "post":        "POST - 10yd stem, then break inside toward the goalpost (30 deg), heading deep.",
    "curl":        "CURL - 10yd stem, then hook back toward you (180 deg) and settle ~2yd back; he decelerates into it.",
    "comeback":    "COMEBACK - 12yd stem, then plant and break back toward the sideline (225 deg) only 1-2yd and SETTLE/STOP, squaring up to you. He is coming BACK to the ball, not running away - put a firm BULLET on him where he settles (right around his break point); do NOT lead him further back or loft it.",
    "out":         "OUT - 10yd stem, then break flat to the sideline (270 deg).",
    "in":          "IN/DIG - 10yd stem, then cut hard inside across the field (90 deg).",
    "corner":      "CORNER - 10yd stem, then break to the deep sideline corner (315 deg).",
    "post_corner": "POST-CORNER - 10yd stem, fake inside to the post (45 deg), then break back out to the corner (315 deg).",
    "zig":         "ZIG - 5yd stem, jab inside (90 deg), then snap out to the sideline (270 deg).",
    "double_move": "DOUBLE MOVE - 8yd stem, fake inside (90 deg), then snap back vertical (0 deg) and go deep.",
    "drag":        "DRAG - shallow 4yd stem, then a flat cross inside (90 deg); stays low.",
}


def build_wr_pre_snap_observation(
    wr: PlayerState,
    wr_attrs: PlayerAttrs,
    cb: PlayerState | None,
    route: str,
    cut_time: float,
    cut_heading: float,
    upfield_yards: float,
    route_phases: list[tuple[float, float]] | None = None,
) -> str:
    lines = [
        "=== WR PRE-SNAP OBSERVATION ===",
        "",
        f"YOUR POSITION: ({wr.x:.1f}, {wr.y:.1f})",
        f"YOUR ATTRIBUTES:  speed={wr_attrs.max_speed:.1f}yd/s  accel={wr_attrs.acceleration:.1f}yd/s²  catch={wr_attrs.catch:.0f}/99",
        "",
        "ROUTE CALLED:",
        f"  Route: {route}",
        f"  Route shape: {_ROUTE_GEOMETRY.get(route, 'Execute the route as called.')}",
    ]
    if route_phases and len(route_phases) >= 3:
        lines.append("  FULL ROUTE SCHEDULE:")
        for i, (threshold, heading) in enumerate(route_phases):
            prev_t = route_phases[i-1][0] if i > 0 else 0.0
            if threshold >= 999:
                label = f"  Phase {i+1} ({prev_t:.1f}s+): run {heading:.0f}° ({_heading_label(heading)})"
            else:
                label = f"  Phase {i+1} ({prev_t:.1f}–{threshold:.1f}s): run {heading:.0f}° ({_heading_label(heading)})"
            if i == len(route_phases) - 1:
                label += "  ← final break"
            lines.append(label)
        lines.append(f"  QB expects you open around t={cut_time:.1f}s — timing is yours to feel, stay roughly on schedule.")
    elif cut_time >= 9.0:
        lines += [
            "  Route type: STRAIGHT — no cut, full-speed vertical.",
            "  Call for ball when you have separation.",
        ]
    else:
        lines += [
            f"  Break to ~{cut_heading:.0f}° ({_heading_label(cut_heading)}) around t≈{cut_time:.1f}s.",
            f"  QB is expecting you to be open around that time — stay roughly on schedule.",
        ]
    if cb is not None:
        sep = math.hypot(wr.x - cb.x, wr.y - cb.y)
        dx = cb.x - wr.x
        dy = cb.y - wr.y
        cb_side = "to your RIGHT" if dx > 0.3 else ("to your LEFT" if dx < -0.3 else "directly across from you")
        cb_depth = f"{abs(dy):.1f} yd {'UPFIELD' if dy > 0 else 'behind'} you"
        press_note = ""
        if sep <= 1.5:
            press_note = (
                "  PRESS COVERAGE: CB is in your face. Expect a physical jam off the line for the first ~0.3s. "
                "An aggressive release move (attack inside or outside hard on your first step) can help you shed "
                "the jam faster and get into your stem."
            )
        lines += [
            "",
            "CB ALIGNMENT:",
            f"  CB pos: ({cb.x:.1f}, {cb.y:.1f})  separation: {sep:.1f} yd",
            f"  CB is {cb_side}, {cb_depth}",
        ]
        if press_note:
            lines.append(press_note)
    lines += [
        "",
        "Decide your pre-snap plan.",
    ]
    return "\n".join(lines)


def build_wr_observation(
    t: float,
    wr: PlayerState,
    wr_attrs: PlayerAttrs,
    cb: PlayerState | None,
    qb: PlayerState,
    ball: BallState,
    route: str,
    cut_time: float,
    cut_heading: float,
    wr_called_for_ball: bool,
    call_t: float | None,
    broken_play: bool,
    wr_history: list[dict] | None = None,
    ball_total_eta: float | None = None,
    detected_cut_t: float | None = None,
    route_phases: list[tuple[float, float]] | None = None,
    call_heading: float | None = None,
    wr_note: str = "",
    route_description: dict | None = None,
    pre_snap_plan: str = "",
    wr_start: tuple[float, float] | None = None,
    rail_status: str = "",
) -> str:
    wr_accel_str = _accel_status(wr.cut_recovery)

    steps_on_current_heading = 1
    if wr_history:
        for h in reversed(wr_history):
            diff = abs((h["wr_hdg"] - wr.heading + 180) % 360 - 180)
            if diff <= 20.0:
                steps_on_current_heading += 1
            else:
                break

    all_phases = route_phases if route_phases else (
        [(cut_time, 0.0), (999, cut_heading)] if cut_time < 9.0 else [(999, cut_heading)]
    )

    # ── Header ───────────────────────────────────────────────────────────────
    lines = [f"=== WR OBSERVATION  t={t:.1f}s ===", ""]

    # ── Snap position reference ───────────────────────────────────────────────
    if wr_start:
        lines += [
            f"SNAP POSITION: ({wr_start[0]:.1f}, {wr_start[1]:.1f})  — use this to gauge how far into the route you are",
            "",
        ]

    # ── Route description + rail backstop (always first) ─────────────────────
    ctx = (route_description.get("description", "") if route_description else "")
    lines += [f"ROUTE: {route}"]
    if ctx:
        lines.append(f"  WHY: {ctx}")
    if rail_status and not wr_called_for_ball and not broken_play and ball.state != "in_air":
        lines.append(f"  {rail_status}")
        lines.append(
            f"  PLAN WINDOW: you are at t={t:.1f}s — plan t={t + 0.1:.1f} through t={t + 0.4:.1f} (1-4 steps)."
        )
    lines.append("")

    # ── Pre-snap plan + note ──────────────────────────────────────────────────
    lines += [
        f"PRE-SNAP READ: {pre_snap_plan if pre_snap_plan else '(none)'}",
        f"YOUR NOTE: {wr_note if wr_note else '(none yet)'}",
        "",
    ]

    # ── WR position ───────────────────────────────────────────────────────────
    lines += [
        f"YOU (WR): pos=({wr.x:.1f}, {wr.y:.1f})  speed={wr.speed:.1f}yd/s  heading={wr.heading:.0f}° ({_heading_label(wr.heading)})  facing={wr.facing:.0f}°  steps_on_this_heading={steps_on_current_heading}",
        f"  YOUR BURST: {wr_accel_str}",
    ]

    # ── CB ────────────────────────────────────────────────────────────────────
    if cb is not None:
        sep = math.hypot(wr.x - cb.x, wr.y - cb.y)
        dx = cb.x - wr.x
        dy = cb.y - wr.y
        cb_side = "RIGHT" if dx > 0.3 else ("LEFT" if dx < -0.3 else "inline")
        cb_rel = "UPFIELD of you" if dy > 0.5 else ("BEHIND you" if dy < -0.5 else "at same depth")
        cb_accel_str = _accel_status(cb.cut_recovery)
        lines += [
            f"CB:     pos=({cb.x:.1f}, {cb.y:.1f})  speed={cb.speed:.1f}yd/s  heading={cb.heading:.0f}°  facing={cb.facing:.0f}°  mode={cb.mode}",
            f"  CB is {sep:.1f} yd away — {cb_side}, {cb_rel}",
            f"  CB BURST: {cb_accel_str}",
        ]
        if cb.cut_recovery >= 2:
            lines.append(
                f"  CB HIP-TURNED — {cb.cut_recovery} recovery steps remaining. "
                f"CB is committed and cannot change direction freely yet."
            )
        body_gap = max(0.0, sep - 2 * PLAYER_RADIUS)
        lines.append(f"  Body gap: {body_gap:.1f} yd")
        # CB orientation hint — describe facing relative to WR, no editorial conclusion
        if cb.cut_recovery == 0:
            brng_cb_to_wr = math.degrees(math.atan2(wr.x - cb.x, wr.y - cb.y)) % 360.0
            face_off = abs((cb.facing - brng_cb_to_wr + 180) % 360 - 180)
            facing_label = _heading_label(cb.facing)
            if face_off > 60:
                lines.append(
                    f"  CB hips at {cb.facing:.0f}° ({facing_label}), {face_off:.0f}° away from your position — advantageous angle"
                )
            else:
                lines.append(
                    f"  CB hips at {cb.facing:.0f}° ({facing_label}), squared toward you — CB is set and mobile"
                )
    else:
        lines.append("CB: no CB on field this play.")

    # ── Sideline warning ──────────────────────────────────────────────────────
    dist_left = wr.x
    dist_right = FIELD_WIDTH - wr.x
    near_side = min(dist_left, dist_right)
    if near_side < OOB_WARN_DIST:
        side_name = "LEFT sideline" if dist_left < dist_right else "RIGHT sideline"
        lines += [
            "",
            f"!! SIDELINE WARNING: you are {near_side:.1f} yd from the {side_name}.",
            f"   Cut back in-bounds, call for the ball, and commit to that path.",
        ]

    # ── Play state ────────────────────────────────────────────────────────────
    lines += [""]
    if broken_play:
        lines += [
            "BROKEN PLAY — original gameplan is void.",
            "Find open space, avoid going out of bounds. Call for the ball when you are open.",
        ]
    elif wr_called_for_ball:
        msg = (
            f"SIGNAL SENT: you called for the ball at t={call_t:.1f}s heading {call_heading:.0f}° ({_heading_label(call_heading)})."
            if call_t is not None and call_heading is not None
            else "SIGNAL SENT: you called for the ball."
        )
        lines += [
            msg,
            "QB threw to where you were going — hold this heading. Cutting now will cause a miss.",
        ]
    elif cut_time >= 9.0:
        lines += [
            "CALL FOR BALL: once you are 10+ yards into the stem and feel your speed is about to break the cushion — "
            "call so the QB can lead you deep. Pre-snap cushion is not earned separation; earn it with your pace.",
        ]
    else:
        lines += [
            f"CALL FOR BALL: 0.1-0.2s before your final {cut_heading:.0f}° cut (anticipatory) OR immediately after that cut when CB rec > 0.",
            f"  Current body gap alone is NOT the signal — pre-snap cushion is not earned separation.",
            f"  The CB can close freely until your stem commits their hips. Call after the stem does its job.",
        ]

    # ── Ball in air ───────────────────────────────────────────────────────────
    if ball.state == "in_air":
        if ball_total_eta and ball_total_eta > 0:
            fuzz = max(0.25, 4.0 * (ball.eta / ball_total_eta))
        else:
            fuzz = 4.0
        dist_to_land = math.hypot(wr.x - ball.landing_x, wr.y - ball.landing_y)
        bearing_to_qb = math.degrees(math.atan2(qb.x - wr.x, qb.y - wr.y)) % 360.0
        facing_label, _ = _wr_facing_modifier(wr, qb)
        req_speed = dist_to_land / max(ball.eta, 0.01)
        lines += [
            "",
            f"BALL IN AIR — ETA: {ball.eta:.2f}s",
            f"  Landing zone: ({ball.landing_x:.1f}, {ball.landing_y:.1f})  +/-{fuzz:.1f} yd",
            f"  Ball arrives at height z={ball.landing_z:.1f} ({_height_label(ball.landing_z)}) — be at the spot; your body adjusts to the height.",
            f"  Your distance to landing zone: {dist_to_land:.1f} yd",
            f"  Your current speed: {wr.speed:.1f} yd/s  |  Required speed to arrive on time: {req_speed:.1f} yd/s",
            f"  FACING: set facing={bearing_to_qb:.0f} exactly (bearing from you to QB). Do NOT estimate.",
            f"  Your current facing: {wr.facing:.0f}° — {facing_label}",
            f"  YOUR HEADING: {wr.heading:.0f}° — do not change.",
        ]

    # ── Move log (last 2s) ────────────────────────────────────────────────────
    if wr_history:
        recent = wr_history[-WR_HISTORY_WINDOW:]
        lines += [
            "",
            "MOVE LOG (last 2s) — your moves vs CB reaction",
            "  (rec: free=full burst available; Nrec=hip turned, N more steps until full burst returns)",
            f"  {'t':>5}  {'WR hdg':>7}  {'WR spd':>7}  {'WR rec':>7}  {'CB hdg':>7}  {'CB spd':>7}  {'CB rec':>7}  {'CB dhdg':>9}",
        ]
        prev_cb_hdg: float | None = None
        for h in recent:
            cb_hdg = h.get("cb_hdg")
            cb_spd = h.get("cb_spd", 0.0)
            cb_cut = h.get("cb_cut_rec", 0)
            wr_cut = h.get("wr_cut_rec", 0)
            if cb_hdg is not None and prev_cb_hdg is not None:
                delta = abs((cb_hdg - prev_cb_hdg + 180.0) % 360.0 - 180.0)
                delta_str = f"+{delta:.0f}deg" if delta >= 1.0 else "     0deg"
            else:
                delta_str = "       --"
            cb_hdg_str = f"{cb_hdg:.0f}deg" if cb_hdg is not None else "    --"
            wr_rec_str = f"{wr_cut}rec" if wr_cut > 0 else "free"
            cb_rec_str = f"{cb_cut}rec" if cb_cut > 0 else "free"
            lines.append(
                f"  {h['t']:>5.1f}  {h['wr_hdg']:>6.0f}deg  {h.get('wr_spd', 0.0):>6.1f}  {wr_rec_str:>7}"
                f"  {cb_hdg_str:>7}  {cb_spd:>6.1f}  {cb_rec_str:>7}  {delta_str:>9}"
            )
            if cb_hdg is not None:
                prev_cb_hdg = cb_hdg

    lines += [
        "",
        f"YOUR MAX SPEED: {wr_attrs.max_speed:.1f} yd/s  peak_accel={wr_attrs.acceleration:.1f} yd/s²",
    ]
    return "\n".join(lines)


def _down_str(down: int, distance: int) -> str:
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    s = suffixes.get(down, "th")
    return f"{down}{s} & {distance}"


def _heading_label(deg: float) -> str:
    """Human-readable direction for a heading in the simulation's coordinate system.
    0°=upfield, 90°=right, 180°=back toward QB, 270°=left."""
    deg = deg % 360
    if deg <= 22 or deg >= 338:
        return "straight upfield"
    elif deg <= 67:
        return "diagonal upfield-right (toward right sideline)"
    elif deg <= 112:
        return "right (toward right sideline)"
    elif deg <= 157:
        return "diagonal back-right (toward QB, right side)"
    elif deg <= 202:
        return "straight back toward QB"
    elif deg <= 247:
        return "diagonal back-left (toward QB, left side)"
    elif deg <= 292:
        return "left (toward left sideline)"
    else:
        return "diagonal upfield-left (toward left sideline)"
