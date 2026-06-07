import math
from engine.physics import PlayerState, PlayerAttrs, BACKPEDAL_SPEED_FRACTION
from engine.ball import BallState
from engine.resolution import CB_ARM_REACH, CB_HALF_REACH

FIELD_WIDTH = 53.3   # yards sideline to sideline
OOB_WARN_DIST = 3.0  # yards from sideline to trigger OOB warning in WR observation
WR_HISTORY_WINDOW = 10

MAX_BALL_SPEED_MPH = 60.0
MIN_BALL_SPEED_MPH = 20.0

# How many recent history entries to include in the prompt
HISTORY_WINDOW = 20
CB_HISTORY_WINDOW = 10

# Landing zone fuzz: starts at ±4 yd at ball release, tightens to ±0.25 yd at arrival
ZONE_FUZZ_MAX = 4.0
ZONE_FUZZ_MIN = 0.25


def _dist(a: PlayerState, b: PlayerState) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


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
    max_mph = MIN_BALL_SPEED_MPH + (qb_attrs.throw_power / 99.0) * (MAX_BALL_SPEED_MPH - MIN_BALL_SPEED_MPH)
    mid_mph = (MIN_BALL_SPEED_MPH + max_mph) / 2.0
    dist_to_wr = _dist(qb, wr)
    MPH_TO_YDS_S = 1.46667
    bullet_t = dist_to_wr / (max_mph * MPH_TO_YDS_S)
    regular_t = dist_to_wr / (mid_mph * MPH_TO_YDS_S)
    lob_t = dist_to_wr / (MIN_BALL_SPEED_MPH * MPH_TO_YDS_S)

    facing_label, facing_mult = _wr_facing_modifier(wr, qb)

    lines = [
        f"=== QB OBSERVATION  t={t:.1f}s  sack_clock={sack_clock:.1f}s  |  {_down_str(down, distance)} ===",
        "",
        f"YOU (QB):  pos=({qb.x:.1f}, {qb.y:.1f})  dist_to_left_sideline={qb.x:.1f}yd  dist_to_right_sideline={FIELD_WIDTH - qb.x:.1f}yd",
        f"WR1 NOW:   pos=({wr.x:.1f}, {wr.y:.1f})  speed={wr.speed:.1f}yd/s  heading={wr.heading:.0f}° ({_heading_label(wr.heading)})  facing={wr.facing:.0f}°",
        f"  WR dist to sidelines: left={wr.x:.1f}yd  right={FIELD_WIDTH - wr.x:.1f}yd",
        f"  WR facing: {facing_label}  (catch probability modifier: {'x{:.2f}'.format(facing_mult)})",
    ]

    if cb is not None and cb_attrs is not None:
        current_sep = _dist(wr, cb)
        lines += [
            f"CB1 NOW:   pos=({cb.x:.1f}, {cb.y:.1f})  speed={cb.speed:.1f}yd/s  heading={cb.heading:.0f}°",
            f"Current WR-CB separation: {current_sep:.2f} yd  (>3 yd = open, 1.5–3 yd = contested, <1.5 yd = tight)",
        ]
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
        f"Ball travel time to WR's CURRENT position ({dist_to_wr:.1f} yd away): "
        f"bullet={bullet_t:.2f}s ({max_mph:.0f} mph)  regular={regular_t:.2f}s ({mid_mph:.0f} mph)  lob={lob_t:.2f}s ({MIN_BALL_SPEED_MPH:.0f} mph)",
        f"LEAD HINT: at regular speed WR will be ≈({proj_x_reg:.1f}, {proj_y_reg:.1f}) — WR's y is {y_dir}. Throw to the projected coord, not current pos.",
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
                "MOVEMENT HISTORY (most recent last):",
                f"  {'t':>5}  {'WR pos':>14}  {'WR hdg':>7}  {'CB pos':>14}  {'CB hdg':>7}  {'sep':>6}",
            ]
            for h in recent:
                wx_h, wy_h = h["wr"]
                cx_h, cy_h = h["cb"]
                sep_h = math.hypot(wx_h - cx_h, wy_h - cy_h)
                lines.append(
                    f"  {h['t']:>5.1f}  ({wx_h:5.1f},{wy_h:5.1f})  {h['wr_hdg']:>6.0f}°"
                    f"  ({cx_h:5.1f},{cy_h:5.1f})  {h['cb_hdg']:>6.0f}°  {sep_h:>6.2f}"
                )
        else:
            lines += [
                "",
                "MOVEMENT HISTORY (most recent last):",
                f"  {'t':>5}  {'WR pos':>14}  {'WR hdg':>7}  {'WR spd':>7}",
            ]
            for h in recent:
                wx_h, wy_h = h["wr"]
                lines.append(
                    f"  {h['t']:>5.1f}  ({wx_h:5.1f},{wy_h:5.1f})  {h['wr_hdg']:>6.0f}°  {h.get('wr_spd', 0.0):>6.1f}"
                )

    lines += [
        "",
        f"Your throw_power allows ball speeds {MIN_BALL_SPEED_MPH:.0f}–{max_mph:.0f} mph.",
        "Ball travels straight-line to target_coord. Lead the WR — throw to where he will be, not where he is.",
        "WR must be within ~1.3 yd of target_coord when ball arrives.",
        "CRITICAL: Do NOT throw until WR has called for the ball (unless broken play).",
        "",
        "ACTIONS:",
        '  hold  → {"action":"hold","reasoning":"..."}',
        '  throw → {"action":"throw","target_coord":[x,y],"ball_speed_mph":45,"reasoning":"..."}',
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
    """Pre-computed situational context lines so the CB doesn't have to do trig."""
    dx = wr.x - cb.x   # positive = WR is to CB's right
    dy = wr.y - cb.y   # positive = WR is upfield of CB (further from QB)
    sep = math.hypot(dx, dy)
    bearing_to_wr = math.degrees(math.atan2(dx, dy)) % 360.0
    intercept_hdg = _intercept_heading(cb, wr, cb_attrs.max_speed)

    if dx > 0.3:
        x_rel = f"WR is {dx:.1f} yd to your RIGHT"
    elif dx < -0.3:
        x_rel = f"WR is {-dx:.1f} yd to your LEFT"
    else:
        x_rel = "You are directly in line with WR horizontally"

    wr_hdg_norm = wr.heading % 360.0
    wr_coming_back = 135.0 <= wr_hdg_norm <= 225.0
    wr_going_lateral = (45.0 <= wr_hdg_norm <= 135.0) or (225.0 <= wr_hdg_norm <= 315.0)

    if dy < -0.5:
        y_rel = f"You are {-dy:.1f} yd UPFIELD of WR — you are between WR and end zone"
        if wr_coming_back:
            wr_motion = (
                f"WR is running BACK toward QB at {wr.speed:.1f} yd/s (heading {wr.heading:.0f}°). "
                f"Backpedaling widens the gap — you would move further from the WR."
            )
        elif wr_going_lateral:
            wr_motion = (
                f"WR is running LATERALLY at {wr.speed:.1f} yd/s (heading {wr.heading:.0f}°). "
                f"Backpedaling does not close lateral separation."
            )
        else:
            wr_motion = f"WR is running toward you at {wr.speed:.1f} yd/s (heading {wr.heading:.0f}°)."
    elif dy > 2.0:
        y_rel = f"WR is {dy:.1f} yd UPFIELD of you — WR has gotten past you"
        wr_motion = f"WR is running away from you at {wr.speed:.1f} yd/s."
    elif dy > 0:
        y_rel = f"WR is {dy:.1f} yd UPFIELD of you — WR just got past you"
        wr_motion = f"WR is running away from you at {wr.speed:.1f} yd/s."
    else:
        y_rel = "You and WR are at roughly the same depth"
        wr_motion = f"WR speed: {wr.speed:.1f} yd/s  heading: {wr.heading:.0f}°"

    bp_speed = cb_attrs.max_speed * BACKPEDAL_SPEED_FRACTION
    lines = [
        "SITUATION:",
        f"  {y_rel}",
        f"  {x_rel}",
        f"  {wr_motion}",
        f"  Separation: {sep:.1f} yd  |  Bearing to WR: {bearing_to_wr:.0f}°  |  Intercept heading (leads WR 0.5s): {intercept_hdg:.0f}°",
        "  YOUR OPTIONS:",
        f"    backpedal  — move upfield (heading≈0°) while watching WR (facing≈180°). Max speed: {bp_speed:.1f} yd/s. Maintains cushion; you stay between WR and end zone.",
        f"    intercept  — sprint toward WR's projected position at heading≈{intercept_hdg:.0f}°, mode=normal, full speed. Closes gap fastest; commits you in that direction.",
        f"    mirror     — match WR's lateral drift, heading≈{bearing_to_wr:.0f}°, mode=normal. Stays in phase horizontally; neither closes nor opens the gap.",
    ]
    return lines


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

    lines = [
        f"=== CB OBSERVATION  t={t:.1f}s ===",
        "",
        f"YOU (CB):  pos=({cb.x:.1f}, {cb.y:.1f})  speed={cb.speed:.1f}yd/s  heading={cb.heading:.0f}°  facing={cb.facing:.0f}°  mode={cb.mode}",
        f"WR:        pos=({wr.x:.1f}, {wr.y:.1f})  speed={wr.speed:.1f}yd/s  heading={wr.heading:.0f}° ({_heading_label(wr.heading)})  facing={wr.facing:.0f}°",
        "",
    ]
    lines += _cb_situation(cb, wr, cb_attrs)
    lines += [
        "",
        f"YOUR SPEEDS:  forward max={cb_attrs.max_speed:.1f}yd/s  backpedal max={backpedal_speed:.1f}yd/s  accel={cb_attrs.acceleration:.1f}yd/s²",
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
            f"  Landing zone center: ({ball.landing_x:.1f}, {ball.landing_y:.1f})  uncertainty: ±{fuzz:.1f} yd",
            f"  Your distance to zone center: {dist_to_zone:.1f} yd",
            f"  Heading to move toward zone: {bearing_to_zone:.0f}°",
            f"  Your arm tip (facing {cb.facing:.0f}°) is at ({arm_tip_x:.1f},{arm_tip_y:.1f}), "
            f"{arm_dist_to_zone:.1f}yd from zone center",
            f"  FACING: {facing_instruction}",
        ]

    # WR movement history
    if wr_history:
        recent = wr_history[-CB_HISTORY_WINDOW:]
        lines += [
            "",
            "WR RECENT MOVES (recent last):",
            f"  {'t':>5}  {'WR pos':>14}  {'WR hdg':>7}  {'WR spd':>7}",
        ]
        for h in recent:
            wx, wy = h["wr"]
            lines.append(
                f"  {h['t']:>5.1f}  ({wx:5.1f},{wy:5.1f})  {h['wr_hdg']:>6.0f}°  {h.get('wr_spd', 0.0):>6.1f}"
            )

    # CB self-action history
    if wr_history:
        recent = wr_history[-CB_HISTORY_WINDOW:]
        cb_entries = [h for h in recent if h.get("cb_mode")]
        if cb_entries:
            lines += [
                "",
                "YOUR RECENT ACTIONS (what you actually did — check your own pattern):",
                f"  {'t':>5}  {'hdg':>6}  {'mode':<10}",
            ]
            for h in cb_entries:
                lines.append(f"  {h['t']:>5.1f}  {h['cb_hdg']:>5.0f}°  {h.get('cb_mode', ''):<10}")

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
    ]
    if route_phases and len(route_phases) >= 3:
        # Multi-phase route: show full schedule
        lines.append("  FULL ROUTE SCHEDULE:")
        for i, (threshold, heading) in enumerate(route_phases):
            prev_t = route_phases[i-1][0] if i > 0 else 0.0
            if threshold >= 999:
                label = f"  Phase {i+1} ({prev_t:.1f}s+): run {heading:.0f}° ({_heading_label(heading)})"
            else:
                label = f"  Phase {i+1} ({prev_t:.1f}–{threshold:.1f}s): run {heading:.0f}° ({_heading_label(heading)})"
            if i == len(route_phases) - 1:
                label += "  ← REAL BREAK — call for ball here"
            elif i > 0:
                label += "  ← intermediate move"
            lines.append(label)
        lines.append(f"  QB expects you open around t={cut_time:.1f}s — time your cuts precisely.")
    elif cut_time >= 9.0:
        lines += [
            "  Route type: STRAIGHT -- no cut. Full-speed vertical route.",
            "  Run upfield the entire play.",
            "  Call for ball when you have clear separation (2+ yards) from the CB.",
        ]
    else:
        lines += [
            f"  Guideline: run roughly {upfield_yards:.0f} yards upfield, then cut to ~{cut_heading:.0f}° ({_heading_label(cut_heading)})",
            f"  Cut timing: QB expects the cut around t={cut_time:.1f}s — stay within ±0.2s of this",
            f"  The exact distance upfield is flexible, but the cut direction must be roughly correct (±45°).",
        ]
    if route == "curl":
        lines += [
            "",
            "!! CURL TIMING: Call for ball as you BEGIN the turn (heading ~270°), one step BEFORE the full 180°.",
            "  The ball arrives as you complete the turn to face the QB. QB throws immediately on your signal.",
            "  Do not wait until you are fully at 180° — ball will arrive before you finish turning.",
        ]
    lines += [
        "",
        "YOUR GOAL: get open. Use deception — vary your speed, take a false step, use your body.",
        "The CB does not know your route. You do. Use that advantage.",
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
            "  Use this to decide your release plan — if CB is playing inside, attack outside. If press, use a push-off step.",
        ]
    lines += [
        "",
        "Decide your pre-snap plan: what deception technique will you use, and at what moment?",
        "You will re-evaluate every step based on what the CB actually does.",
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
) -> str:
    time_to_cut = cut_time - t

    lines = [
        f"=== WR OBSERVATION  t={t:.1f}s ===",
        "",
        f"YOU (WR): pos=({wr.x:.1f}, {wr.y:.1f})  speed={wr.speed:.1f}yd/s  heading={wr.heading:.0f}° ({_heading_label(wr.heading)})  facing={wr.facing:.0f}°",
    ]

    if cb is not None:
        sep = math.hypot(wr.x - cb.x, wr.y - cb.y)
        dx = cb.x - wr.x
        dy = cb.y - wr.y
        cb_side = "RIGHT" if dx > 0.3 else ("LEFT" if dx < -0.3 else "inline")
        cb_rel = "UPFIELD of you" if dy > 0.5 else ("BEHIND you" if dy < -0.5 else "at same depth")
        lines += [
            f"CB:     pos=({cb.x:.1f}, {cb.y:.1f})  speed={cb.speed:.1f}yd/s  heading={cb.heading:.0f}°  facing={cb.facing:.0f}°  mode={cb.mode}",
            f"  CB is {sep:.1f} yd away — {cb_side}, {cb_rel}",
        ]
        if sep > 4.0:
            lines.append("  CB is giving you a big cushion — consider cutting early to exploit it.")
        elif sep < 1.5:
            lines.append("  CB is tight on you — you need a sharp move to create separation.")
        else:
            lines.append("  CB is in moderate coverage.")
    else:
        lines.append("CB: no CB on field this play.")

    # Sideline proximity warning
    dist_left = wr.x
    dist_right = FIELD_WIDTH - wr.x
    near_side = min(dist_left, dist_right)
    if near_side < OOB_WARN_DIST:
        side_name = "LEFT sideline" if dist_left < dist_right else "RIGHT sideline"
        lines += [
            "",
            f"!! SIDELINE WARNING: you are {near_side:.1f} yd from the {side_name}.",
            f"   If your heading takes you out of bounds, cut back in-bounds, call for the ball, and commit to that path.",
        ]

    # Play state
    lines += [""]
    if broken_play:
        lines += [
            "BROKEN PLAY — original gameplan is void.",
            "Find open space, avoid going out of bounds. Call for the ball when you are open.",
            "You are free to choose any heading and throttle.",
        ]
    elif wr_called_for_ball:
        lines += [
            f"COMMITTED: you called for the ball at t={call_t:.1f}s." if call_t is not None else "COMMITTED: you called for the ball.",
            "Your heading is LOCKED — do not cut. Choose your throttle (accelerate/coast/brake) to position for the catch.",
            "If the throw is bad once ball is in air, you may adjust heading to chase it.",
        ]
    elif cut_time >= 9.0:
        # Go route — no cut, straight vertical
        lines += [
            f"PHASE: STRAIGHT ROUTE ({route}) -- NO CUT. Run straight upfield the entire play.",
            "There is no prescribed cut. Call for the ball whenever you judge you are open — use your own read of the coverage.",
        ]
    elif route_phases and len(route_phases) >= 3:
        # Multi-phase route — determine current phase and show full schedule
        cur_phase_idx = 0
        for i, (threshold, _) in enumerate(route_phases):
            if t < threshold:
                cur_phase_idx = i
                break
        else:
            cur_phase_idx = len(route_phases) - 1

        lines.append(f"ROUTE SCHEDULE ({route}):")
        for i, (threshold, heading) in enumerate(route_phases):
            prev_t = route_phases[i-1][0] if i > 0 else 0.0
            if threshold >= 999:
                entry = f"  Phase {i+1} ({prev_t:.1f}s+): run {heading:.0f}° ({_heading_label(heading)})"
            else:
                entry = f"  Phase {i+1} ({prev_t:.1f}–{threshold:.1f}s): run {heading:.0f}° ({_heading_label(heading)})"
            if i == len(route_phases) - 1:
                entry += " <- REAL BREAK"
            if i == cur_phase_idx:
                entry += "  << CURRENT"
            lines.append(entry)

        # Show current phase instruction
        cur_threshold = route_phases[cur_phase_idx][0]
        time_to_next = cur_threshold - t
        if cur_phase_idx == len(route_phases) - 1:
            # On final (real break) phase
            lines += [
                f"REAL BREAK PHASE — you are past all fakes. Run {cut_heading:.0f}° ({_heading_label(cut_heading)}).",
                "Call for the ball if you are open (2+ yards from CB).",
            ]
        elif cur_phase_idx == 0:
            # Still in stem phase
            lines += [
                f"STEM PHASE — run upfield (0°). {time_to_next:.1f}s until first cut.",
                "Deception: change jab angle each time (e.g., left then right, not same direction twice); go 2-3 steps in a direction before snapping back to sell the fake; mix speed changes (brake then burst) with heading fakes. Do NOT call for ball yet.",
            ]
        else:
            # In an intermediate phase (fake move)
            next_heading = cut_heading
            lines += [
                f"INTERMEDIATE MOVE — hold {route_phases[cur_phase_idx][1]:.0f}° for {time_to_next:.1f}s until the real break.",
                f"HOLD this heading for the FULL phase duration — do NOT return to 0° or oscillate. The CB must commit to this fake.",
                f"After the fake, cut hard to {next_heading:.0f}° ({_heading_label(next_heading)}) — that is your REAL break.",
                "Do NOT call for ball in this fake phase.",
            ]
    else:
        if time_to_cut > 0.3:
            lines += [
                f"PHASE: PRE-CUT  |  Route: {route}  |  Cut heading: ~{cut_heading:.0f}° ({_heading_label(cut_heading)}) at t≈{cut_time:.1f}s  |  Time to cut: {time_to_cut:.1f}s",
                f"KEEP HEADING NEAR 0° (straight upfield). Do NOT move to {cut_heading:.0f}° yet — that telegraphs the route to the CB.",
                "Deception: vary your fakes — change the jab angle each time (not always the same direction), go 2-3 steps in a direction to sell it before snapping back, mix in speed changes (brake then burst). A predictable pattern has no deception value.",
            ]
        elif time_to_cut >= -0.2:
            lines += [
                f"CUT WINDOW — execute your break NOW (t={t:.1f}s, cut guideline t={cut_time:.1f}s).",
                f"Cut toward ~{cut_heading:.0f}° ({_heading_label(cut_heading)}). If you are open after the cut, call for the ball.",
            ]
            if route == "curl":
                lines.append("!! CURL TIMING: Call for ball as you BEGIN the turn (heading ~270°, one step before full 180°). This gives the ball time to arrive as you face up. QB throws immediately on your signal.")
        else:
            lines += [
                f"PAST CUT TIME (cut was at t≈{cut_time:.1f}s, now t={t:.1f}s).",
                "If you have not called for the ball yet, do so if you are open. QB is looking for you.",
            ]

    # Ball state
    if ball.state == "in_air":
        if ball_total_eta and ball_total_eta > 0:
            fuzz = max(0.25, 4.0 * (ball.eta / ball_total_eta))
        else:
            fuzz = 4.0
        dist_to_land = math.hypot(wr.x - ball.landing_x, wr.y - ball.landing_y)
        bearing_to_ball = math.degrees(math.atan2(
            ball.landing_x - wr.x, ball.landing_y - wr.y
        )) % 360.0
        facing_label, _ = _wr_facing_modifier(wr, qb)
        lines += [
            "",
            f"BALL IN AIR — ETA: {ball.eta:.2f}s",
            f"  Landing zone: ({ball.landing_x:.1f}, {ball.landing_y:.1f})  ±{fuzz:.1f} yd",
            f"  Your distance to landing zone: {dist_to_land:.1f} yd",
            f"  Bearing to landing zone: {bearing_to_ball:.0f}°",
            f"  Your facing: {wr.facing:.0f}° — {facing_label}",
            "  Adjust your heading to get under the ball. Face toward the landing zone for best catch chance.",
        ]

    # Side-by-side WR move + CB reaction log
    if wr_history:
        recent = wr_history[-WR_HISTORY_WINDOW:]
        lines += [
            "",
            "MOVE LOG — your moves vs CB reaction (did your moves change what the CB did?):",
            f"  {'t':>5}  {'WR hdg':>7}  {'WR spd':>7}  {'CB hdg':>7}  {'CB mode':<10}  {'CB Δhdg':>8}",
        ]
        prev_cb_hdg: float | None = None
        for h in recent:
            cb_hdg = h.get("cb_hdg")
            cb_mode = h.get("cb_mode", "")
            if cb_hdg is not None and prev_cb_hdg is not None:
                delta = abs((cb_hdg - prev_cb_hdg + 180.0) % 360.0 - 180.0)
                delta_str = f"{delta:+.0f}°" if delta >= 1.0 else "   0°"
            else:
                delta_str = "   --"
            cb_hdg_str = f"{cb_hdg:.0f}°" if cb_hdg is not None else "  --"
            lines.append(
                f"  {h['t']:>5.1f}  {h['wr_hdg']:>6.0f}°  {h.get('wr_spd', 0.0):>6.1f}  "
                f"{cb_hdg_str:>7}  {cb_mode:<10}  {delta_str:>8}"
            )
            if cb_hdg is not None:
                prev_cb_hdg = cb_hdg

    lines += [
        "",
        f"YOUR MAX SPEED: {wr_attrs.max_speed:.1f} yd/s  accel={wr_attrs.acceleration:.1f} yd/s²",
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
