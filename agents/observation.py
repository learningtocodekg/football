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
) -> str:
    dist_to_wr = _dist(qb, wr)
    v_max = max_ball_speed(qb_attrs.throw_power)
    arc_strs = []
    lead_arc, lead_t = None, None
    for arc in ARC_ANGLES:
        sol = solve_arc(dist_to_wr, arc)
        if sol is None or sol[1] > v_max:
            arc_strs.append(f"{arc}=OUT OF RANGE")
            continue
        t_f, _v, peak = sol
        arc_strs.append(f"{arc}={t_f:.2f}s (peak z={peak:.1f})")
        if lead_arc is None or arc == "drive":
            lead_arc, lead_t = arc, t_f
    if lead_t is None:
        lead_arc, lead_t = "loft", dist_to_wr / max(v_max * 0.7, 1.0)
    regular_t = lead_t

    facing_label, facing_mult = _wr_facing_modifier(wr, qb)

    wr_accel_str = _accel_status(wr.cut_recovery)
    lines = [
        f"=== QB OBSERVATION  t={t:.1f}s  sack_clock={sack_clock:.1f}s  |  {_down_str(down, distance)} ===",
        "",
        f"YOU (QB):  pos=({qb.x:.1f}, {qb.y:.1f})  dist_to_left_sideline={qb.x:.1f}yd  dist_to_right_sideline={FIELD_WIDTH - qb.x:.1f}yd",
        f"WR1 NOW:   pos=({wr.x:.1f}, {wr.y:.1f})  speed={wr.speed:.1f}yd/s  heading={wr.heading:.0f}° ({_heading_label(wr.heading)})  facing={wr.facing:.0f}°",
        f"  WR dist to sidelines: left={wr.x:.1f}yd  right={FIELD_WIDTH - wr.x:.1f}yd",
        f"  WR facing: {facing_label}  (catch probability modifier: {'x{:.2f}'.format(facing_mult)})",
        f"  WR BURST: {wr_accel_str}",
    ]

    if cb is not None and cb_attrs is not None:
        current_sep = _dist(wr, cb)
        cb_accel_str = _accel_status(cb.cut_recovery)
        lines += [
            f"CB1 NOW:   pos=({cb.x:.1f}, {cb.y:.1f})  speed={cb.speed:.1f}yd/s  heading={cb.heading:.0f}°",
            f"  CB BURST: {cb_accel_str}",
            f"Current WR-CB separation: {current_sep:.2f} yd  body gap: {max(0.0, current_sep - 2*PLAYER_RADIUS):.1f} yd  (>2.5 yd = open/>1.5 yd gap, 1.5–2.5 yd = contested, <1.5 yd = contact)",
        ]
        if cb.cut_recovery >= 2:
            lines.append(
                f"  !! CB IN RECOVERY — hip-turned, {cb.cut_recovery} steps of reduced burst. "
                f"Separation is likely to GROW even if it looks close right now."
            )
        elif wr.cut_recovery >= 2:
            lines.append(
                f"  NOTE: WR just cut — {wr.cut_recovery} steps of reduced burst. "
                f"Separation may be about to SHRINK as CB closes."
            )
    else:
        lines.append("CB1: no CB on field this play.")

    proj_x_reg = wr.x + math.sin(math.radians(wr.heading)) * wr.speed * regular_t
    proj_y_reg = wr.y + math.cos(math.radians(wr.heading)) * wr.speed * regular_t
    wr_hdg_norm = wr.heading % 360.0
    if 90.0 < wr_hdg_norm < 270.0:
        y_dir = f"DECREASING toward QB (current y={wr.y:.1f} → projected y={proj_y_reg:.1f})"
    else:
        y_dir = f"INCREASING upfield (current y={wr.y:.1f} → projected y={proj_y_reg:.1f})"
    lines += [
        f"ARC FLIGHT TIMES to WR's CURRENT position ({dist_to_wr:.1f} yd away): " + "  ".join(arc_strs),
        f"LEAD HINT: on a {lead_arc} arc ({lead_t:.2f}s flight) WR will be ≈({proj_x_reg:.1f}, {proj_y_reg:.1f}) — WR's y is {y_dir}. Throw to the projected coord, not current pos.",
    ]


    # WR signal block
    lines += [""]
    if broken_play:
        lines += [
            "!! BROKEN PLAY — WR deviated from route plan. Original cut schedule is void.",
            "Wait for the WR to call for the ball and look for an open window.",
        ]
    elif wr_called_for_ball:
        lines += [
            f"** WR CALLED FOR BALL at t={wr_call_t:.1f}s — heading {wr_call_heading:.0f}° ({_heading_label(wr_call_heading)}) **",
            "WR is committed to this path (heading locked). Speed may vary. Lead him where he will be when ball arrives.",
            "If coverage is too tight, hold — WR stays on this path.",
        ]
        # Go-route hint: CB plays cushion ahead of WR, throw must clear CB
        if cb is not None and expected_open_t is not None and expected_open_t >= 9.0:
            cb_y = cb.y
            lines += [
                f"GO ROUTE — CB plays CUSHION (ahead of WR at y={cb_y:.1f}). Your throw target MUST be further upfield than y={cb_y:.1f}.",
                f"  If you throw to WR's current projected y and the CB is at y={cb_y:.1f}, the CB is already between the ball and the WR.",
                f"  Throw PAST the CB: target y > {cb_y:.1f}. On a go route, use a lob and aim deep enough that the WR runs under it.",
            ]
        lines += [
            "",
            "WR CALLED FOR BALL — use your own judgment:",
            "  A WR calling for the ball means he believes he will be open soon. It does NOT mean you must throw immediately.",
            "  Check: is coverage actually open right now? Is the CB still closing? Is the WR in the right position?",
            "  If coverage looks tight, hold — the WR will maintain his heading.",
            "  If coverage is open, throw now. Every step you wait gives the CB more time to close.",
        ]
    else:
        if expected_open_t is not None and expected_open_t < 9.0:
            lines.append(
                f"ROUTE HINT: WR expected to break around t={expected_open_t:.1f}s — "
                "WR has NOT yet called for the ball. Do not throw until WR signals."
            )
        if detected_cut_t is not None:
            if expected_open_t is not None and abs(detected_cut_t - expected_open_t) <= 0.4:
                lines.append(f"DETECTED: WR made a significant heading change at t={detected_cut_t:.1f}s — this matches the expected route cut (t≈{expected_open_t:.1f}s).")
            else:
                lines.append(f"DETECTED: WR made a heading change at t={detected_cut_t:.1f}s — likely a jab/fake (real cut expected around t≈{expected_open_t:.1f}s). Wait for the WR call.")
        lines.append("WR has not called for the ball. Hold until the call comes in.")

    if route_phases:
        lines += ["", "WR ROUTE SCHEDULE (guideline — WR is AI-driven, actual timing may vary):"]
        proj_x, proj_y = wr.x, wr.y
        proj_hdg = wr.heading
        proj_t = t
        for cut_t, cut_hdg in route_phases:
            if cut_t >= 999:
                continue
            label = _heading_label(cut_hdg)
            if t >= cut_t:
                lines.append(f"  t={cut_t:.1f}s  cut to {cut_hdg:.0f}° ({label})  [DONE]")
            else:
                dt = cut_t - proj_t
                proj_x += math.sin(math.radians(proj_hdg)) * wr.speed * dt
                proj_y += math.cos(math.radians(proj_hdg)) * wr.speed * dt
                lines.append(
                    f"  t={cut_t:.1f}s  cut to {cut_hdg:.0f}° ({label})  "
                    f"[in ~{cut_t - t:.1f}s — WR est. near ({proj_x:.1f}, {proj_y:.1f})]"
                )
                proj_hdg = cut_hdg
                proj_t = cut_t
        final_hdg = route_phases[-1][1]
        lines.append(f"  after last cut: WR runs {final_hdg:.0f}° ({_heading_label(final_hdg)}) — lead him")

    if history:
        recent = history[-HISTORY_WINDOW:]
        if cb is not None:
            lines += [
                "",
                "MOVEMENT HISTORY (rec=cut_recovery — when rec>0, that player cannot burst freely):",
                f"  {'t':>5}  {'WR pos':>14}  {'WR hdg':>7}  {'WR rec':>7}  {'CB pos':>14}  {'CB hdg':>7}  {'CB rec':>7}  {'sep':>6}",
            ]
            for h in recent:
                wx_h, wy_h = h["wr"]
                cx_h, cy_h = h["cb"]
                sep_h = math.hypot(wx_h - cx_h, wy_h - cy_h)
                wr_cut = h.get("wr_cut_rec", 0)
                cb_cut = h.get("cb_cut_rec", 0)
                wr_rec_str = f"{wr_cut}rec" if wr_cut > 0 else "free"
                cb_rec_str = f"{cb_cut}rec" if cb_cut > 0 else "free"
                lines.append(
                    f"  {h['t']:>5.1f}  ({wx_h:5.1f},{wy_h:5.1f})  {h['wr_hdg']:>6.0f}°  {wr_rec_str:>7}"
                    f"  ({cx_h:5.1f},{cy_h:5.1f})  {h['cb_hdg']:>6.0f}°  {cb_rec_str:>7}  {sep_h:>6.2f}"
                )
        else:
            lines += [
                "",
                "MOVEMENT HISTORY (most recent last):",
                f"  {'t':>5}  {'WR pos':>14}  {'WR hdg':>7}  {'WR spd':>7}  {'WR rec':>7}",
            ]
            for h in recent:
                wx_h, wy_h = h["wr"]
                wr_cut = h.get("wr_cut_rec", 0)
                rec_str = f"{wr_cut}rec" if wr_cut > 0 else "free"
                lines.append(
                    f"  {h['t']:>5.1f}  ({wx_h:5.1f},{wy_h:5.1f})  {h['wr_hdg']:>6.0f}°  {h.get('wr_spd', 0.0):>6.1f}  {rec_str:>7}"
                )

    lines += [
        "",
        f"YOUR ARM: max ball speed {v_max * YD_S_TO_MPH:.0f} mph — bullet feasible to ≈{max_range('bullet', v_max):.0f} yd, "
        f"max range ≈{max_range('loft', v_max):.0f} yd on a loft.",
        "The ball flies a real 3D arc. Flatter arcs (bullet/drive) arrive sooner but pass through the lane "
        "at reachable height; higher arcs (touch/loft) clear underneath defenders but hang longer — the CB closes the whole time.",
        "Lead the WR — throw to where he will be, not where he is.",
        "CRITICAL: Do NOT throw until WR has called for the ball (unless broken play).",
    ]
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
    lines = [
        f"=== CB INTENT DECISION  t={t:.1f}s  ETA={ball.eta:.2f}s ===",
        "",
        f"BALL landing zone: ({ball.landing_x:.1f}, {ball.landing_y:.1f})  ±{fuzz:.1f}yd  [{zone_dir}]",
        f"BALL arrives at height z={ball.landing_z:.1f} ({_height_label(ball.landing_z)}) — your vertical reach is {CB_VERTICAL_REACH:.1f} yd."
        + (" HIGH BALL: swat/pick only at full extension (reduced odds) — playing the man may be better." if ball.landing_z > HIGH_BALL_Z else ""),
        f"  To move toward ball: heading ≈ {bearing_to_ball:.0f}°",
        f"WR pos: ({wr.x:.1f}, {wr.y:.1f})  sep from you: {sep:.2f}yd",
        f"YOUR pos: ({cb.x:.1f}, {cb.y:.1f})  facing={cb.facing:.0f}°  speed={cb.speed:.1f}yd/s",
        "",
        f"GEOMETRY CHECK:",
        f"  Bearing to ball: {bearing_to_ball:.0f}°  Your facing: {cb.facing:.0f}°",
        f"  Facing within 60° of ball? {facing_ok}",
        f"  PBU arm tip ({CB_ARM_REACH:.1f}yd reach): ({arm_tip_pbu_x:.1f},{arm_tip_pbu_y:.1f})  dist to zone={arm_pbu_dist:.1f}yd",
        f"  INT arm tip ({CB_HALF_REACH:.1f}yd reach): ({arm_tip_int_x:.1f},{arm_tip_int_y:.1f})  dist to zone={arm_int_dist:.1f}yd",
        f"  Distance to zone center: {dist_to_zone:.1f}yd",
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


_ROUTE_GEOMETRY: dict[str, str] = {
    "go": "FLY ROUTE — run straight upfield at full speed the ENTIRE play. NO cut. Create separation through pure speed. Call when you have a step on the CB.",
    "slant": "SLANT — stem upfield 2-3 steps, then cut sharp diagonally ACROSS the field (heading ~135deg or ~45deg toward the QB side). Low-depth crossing route.",
    "curl": "CURL — stem upfield 4-6 steps, then HOOK BACK toward the QB (heading ~180deg). You turn around and come back to the ball. Final heading is roughly back toward QB.",
    "comeback": "COMEBACK — stem upfield 6-8 steps toward the sideline, then break BACK toward the sideline at the same depth (heading ~270deg if left, ~90deg if right). You stop going upfield and come back flat.",
    "in": "IN (DIG) — stem upfield 4-5 steps, then cut HARD across the field toward the opposite hash (heading ~90deg or ~270deg). Sharp flat cross.",
    "out": "OUT — stem upfield 4-5 steps, then cut HARD to the sideline (heading ~270deg or ~90deg).",
    "corner": "CORNER — stem upfield, make an inside fake, then break diagonally to the CORNER of the end zone (heading ~315deg or ~45deg). Ends outside and deep.",
    "post": "POST — stem upfield, make an outside fake, then break diagonally toward the GOALPOST (heading ~45deg or ~315deg). Ends inside and deep.",
    "post_corner": "POST-CORNER — three committed phases: stem upfield, break toward post (~45deg), then break back to corner (~315deg). Each phase must be held for multiple steps.",
    "zig": "ZIG — stem upfield, make a hard break at one angle (e.g. ~45deg or ~135deg), then snap to the opposite angle. Two distinct committed cuts.",
    "double_move": "DOUBLE MOVE — run an initial route convincingly for 3-4+ steps to commit the CB's hips, then snap hard to the opposite direction. The fake must look real.",
    "drag": "DRAG — flat crossing route at very low depth (~1-3 yards past LOS), heading directly across the field toward the opposite hash. Stays low and flat.",
}


def _est_yards(threshold: float, from_rest: bool = True, max_speed: float = 8.5, accel: float = 14.0) -> int:
    """Estimate yards traveled over `threshold` seconds."""
    if from_rest:
        t_max = max_speed / accel
        if threshold <= t_max:
            return round(0.5 * accel * threshold ** 2)
        return round(0.5 * accel * t_max ** 2 + max_speed * (threshold - t_max))
    return round(max_speed * threshold)


def _phase_instruction(route_phases: list[tuple[float, float]], cut_time: float, cut_heading: float) -> str:
    """Generate a concrete, specific one-paragraph route instruction from the phase schedule."""
    if not route_phases:
        return f"Run {cut_heading:.0f}° ({_heading_label(cut_heading)}) the entire play."
    if len(route_phases) == 1 and route_phases[0][0] >= 999:
        h = route_phases[0][1]
        return f"Run {h:.0f}° ({_heading_label(h)}) the entire play — no cuts."

    parts = []
    for i, (threshold, heading) in enumerate(route_phases):
        label = _heading_label(heading)
        is_final = threshold >= 999
        if i == 0:
            if is_final:
                parts.append(f"Run {heading:.0f}° ({label}) the entire play.")
            else:
                yards = _est_yards(threshold, from_rest=True)
                parts.append(f"Head {heading:.0f}° ({label}) for ~{yards} yards (~{threshold:.1f}s).")
        elif is_final:
            parts.append(
                f"Around t={cut_time:.1f}s — when you feel a {heading:.0f}° cut would give "
                f"you enough separation — cut to {heading:.0f}° ({label}) and continue through the catch."
            )
        else:
            prev_t = route_phases[i - 1][0]
            dt = threshold - prev_t
            yards = _est_yards(dt, from_rest=False)
            parts.append(f"Then head {heading:.0f}° ({label}) for ~{yards} yards (~{dt:.1f}s).")
    return " ".join(parts)


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
        lines += [
            "",
            "CB ALIGNMENT:",
            f"  CB pos: ({cb.x:.1f}, {cb.y:.1f})  separation: {sep:.1f} yd",
            f"  CB is {cb_side}, {cb_depth}",
        ]
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

    # ── Route description (always first) ─────────────────────────────────────
    mech = _phase_instruction(all_phases, cut_time, cut_heading)
    ctx = (route_description.get("description", "") if route_description else "")
    lines += [f"ROUTE: {route}", f"  {mech}"]
    if ctx:
        lines.append(f"  WHY: {ctx}")
    lines.append("")

    # ── Current heading instruction (only while route is free / not committed) ─
    if not wr_called_for_ball and not broken_play and ball.state != "in_air":
        current_phase_idx = len(all_phases) - 1
        for i, (threshold, _) in enumerate(all_phases):
            if t < threshold:
                current_phase_idx = i
                break
        phase_thresh, phase_heading = all_phases[current_phase_idx]
        is_final = phase_thresh >= 999
        if is_final:
            lines += [
                f"YOUR HEADING NOW: {phase_heading:.0f}° ({_heading_label(phase_heading)}) — this is your final break. Run it.",
                "",
            ]
        else:
            time_left = phase_thresh - t
            next_heading = all_phases[current_phase_idx + 1][1] if current_phase_idx + 1 < len(all_phases) else phase_heading
            lines += [
                f"YOUR HEADING NOW: {phase_heading:.0f}° ({_heading_label(phase_heading)}) | ~{time_left:.1f}s remaining, then cut to {next_heading:.0f}°",
                "",
            ]

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
        lines += [
            "",
            f"BALL IN AIR — ETA: {ball.eta:.2f}s",
            f"  Landing zone: ({ball.landing_x:.1f}, {ball.landing_y:.1f})  +/-{fuzz:.1f} yd",
            f"  Ball arrives at height z={ball.landing_z:.1f} ({_height_label(ball.landing_z)}) — be at the spot; your body adjusts to the height.",
            f"  Your distance to landing zone: {dist_to_land:.1f} yd",
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
