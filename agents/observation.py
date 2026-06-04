import math
from engine.physics import PlayerState, PlayerAttrs, BACKPEDAL_SPEED_FRACTION
from engine.ball import BallState
from engine.resolution import CB_ARM_REACH, CB_HALF_REACH

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
    cb: PlayerState,
    cb_attrs: PlayerAttrs,
    ball: BallState,
    down: int = 1,
    distance: int = 10,
    history: list[dict] | None = None,  # [{"t": float, "wr": [x,y], "wr_hdg": float, "cb": [x,y], "cb_hdg": float}, ...]
    expected_open_t: float | None = None,
    route_phases: list[tuple[float, float]] | None = None,  # [(cut_time, heading_deg), ...]
) -> str:
    current_sep = _dist(wr, cb)
    max_mph = MIN_BALL_SPEED_MPH + (qb_attrs.throw_power / 99.0) * (MAX_BALL_SPEED_MPH - MIN_BALL_SPEED_MPH)
    mid_mph = (MIN_BALL_SPEED_MPH + max_mph) / 2.0

    dist_to_wr = _dist(qb, wr)
    MPH_TO_YDS_S = 1.46667
    bullet_t = dist_to_wr / (max_mph * MPH_TO_YDS_S)
    regular_t = dist_to_wr / (mid_mph * MPH_TO_YDS_S)
    lob_t = dist_to_wr / (MIN_BALL_SPEED_MPH * MPH_TO_YDS_S)

    open_hint = (
        f"ROUTE HINT: WR is expected to be open around t={expected_open_t:.1f}s — "
        "but read the field. He may get open earlier or later. "
        "Account for ball travel time: throw BEFORE he reaches the window."
    ) if expected_open_t is not None else ""

    lines = [
        f"=== QB OBSERVATION  t={t:.1f}s  sack_clock={sack_clock:.1f}s  |  {_down_str(down, distance)} ===",
    ]
    if open_hint:
        lines += ["", open_hint]
    lines += [
        "",
        f"YOU (QB):  pos=({qb.x:.1f}, {qb.y:.1f})  speed={qb.speed:.1f}yd/s",
        f"WR1 NOW:   pos=({wr.x:.1f}, {wr.y:.1f})  speed={wr.speed:.1f}yd/s  heading={wr.heading:.0f}°",
        f"CB1 NOW:   pos=({cb.x:.1f}, {cb.y:.1f})  speed={cb.speed:.1f}yd/s  heading={cb.heading:.0f}°",
        f"Current WR-CB separation: {current_sep:.2f} yd  (>3 yd = open, 1.5–3 yd = contested, <1.5 yd = tight coverage)",
        f"Ball travel time to WR's CURRENT position ({dist_to_wr:.1f} yd away): bullet={bullet_t:.2f}s ({max_mph:.0f} mph)  regular={regular_t:.2f}s ({mid_mph:.0f} mph)  lob={lob_t:.2f}s ({MIN_BALL_SPEED_MPH:.0f} mph)",
    ]

    if route_phases:
        lines += ["", "WR ROUTE SCHEDULE (scripted — actual execution may vary slightly):"]
        # Project WR position forward through each phase from current state
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
                    f"[in ~{cut_t - t:.1f}s — WR estimated near ({proj_x:.1f}, {proj_y:.1f})]"
                )
                proj_hdg = cut_hdg
                proj_t = cut_t
        final_hdg = route_phases[-1][1]
        final_label = _heading_label(final_hdg)
        lines.append(f"  after last cut: WR runs {final_hdg:.0f}° ({final_label}) — lead him to where he will be when ball arrives")

    # Movement history
    if history:
        recent = history[-HISTORY_WINDOW:]
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

    lines += [
        "",
        f"Your throw_power allows ball speeds {MIN_BALL_SPEED_MPH:.0f}–{max_mph:.0f} mph.",
        "Ball travels straight-line to target_coord. Account for travel time — throw to where WR will be, not where he is now.",
        "WR must be within ~1.3 yd of target_coord when ball arrives.",
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

    # Is the WR running back toward the QB (comeback/out-and-in)?
    # Heading 180° = straight back, treat 135–225° as "coming back."
    wr_coming_back = 135.0 <= (wr.heading % 360.0) <= 225.0

    # Four meaningful situations with unambiguous action advice
    if dy < -0.5 and wr_coming_back:
        # CB is upfield but WR has cut back toward QB — backpedaling further widens the gap.
        # CB must flip and chase the WR downfield.
        y_rel = f"You are {-dy:.1f} yd UPFIELD of WR — WR has cut BACK toward QB ✗ (comeback/curl)"
        wr_motion = f"WR is running AWAY from you (back toward QB) at {wr.speed:.1f} yd/s heading {wr.heading:.0f}°"
        action = (
            f"RECOMMENDED: flip hips and CHASE downfield — WR is running away from you toward QB. "
            f"Use intercept heading ≈ {intercept_hdg:.0f}° (leads WR's path), facing ≈ {intercept_hdg:.0f}°. mode=normal. "
            f"Do NOT backpedal — that moves you further away."
        )
    elif dy < -0.5:
        # CB is upfield (between WR and end zone) — correct position, WR approaching
        y_rel = f"You are {-dy:.1f} yd UPFIELD of WR — you are between WR and end zone ✓"
        wr_motion = f"WR is running TOWARD you at {wr.speed:.1f} yd/s"
        action = (
            f"RECOMMENDED: backpedal to maintain cushion. "
            f"Move upfield (heading ≈ 0°) while facing WR (facing ≈ 180°). mode=backpedal"
        )
    elif dy > 2.0:
        # WR has beaten CB by more than 2 yd — CB must chase, not backpedal
        y_rel = f"WR is {dy:.1f} yd UPFIELD of you — WR has beaten you, you are behind ✗"
        wr_motion = f"WR is running AWAY from you at {wr.speed:.1f} yd/s"
        action = (
            f"RECOMMENDED: CHASE — flip hips and sprint toward WR. "
            f"Use intercept heading ≈ {intercept_hdg:.0f}° (leads WR's path, not just current spot), "
            f"facing ≈ {intercept_hdg:.0f}°. mode=normal"
        )
    elif dy > 0:
        # WR has just passed — close gap urgently
        y_rel = f"WR is {dy:.1f} yd UPFIELD of you — WR just got past you, close immediately"
        wr_motion = f"WR is running AWAY from you at {wr.speed:.1f} yd/s"
        action = (
            f"RECOMMENDED: sprint toward WR to close gap. "
            f"Use intercept heading ≈ {intercept_hdg:.0f}° (leads WR's path), "
            f"facing ≈ {intercept_hdg:.0f}°. mode=normal"
        )
    else:
        y_rel = "You and WR are at roughly the same depth"
        wr_motion = f"WR speed: {wr.speed:.1f} yd/s"
        action = f"Mirror WR's horizontal movement. heading ≈ {bearing_to_wr:.0f}° toward WR. mode=normal"

    lines = [
        "SITUATION:",
        f"  {y_rel}",
        f"  {x_rel}",
        f"  {wr_motion}",
        f"  Separation: {sep:.1f} yd  |  Bearing directly to WR: {bearing_to_wr:.0f}°  |  Intercept heading: {intercept_hdg:.0f}°",
        f"  {action}",
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

    # WR history
    if wr_history:
        recent = wr_history[-CB_HISTORY_WINDOW:]
        lines += [
            "",
            "WR HISTORY (recent last):",
            f"  {'t':>5}  {'WR pos':>14}  {'WR hdg':>7}  {'WR spd':>7}",
        ]
        for h in recent:
            wx, wy = h["wr"]
            lines.append(
                f"  {h['t']:>5.1f}  ({wx:5.1f},{wy:5.1f})  {h['wr_hdg']:>6.0f}°  {h.get('wr_spd', 0.0):>6.1f}"
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
