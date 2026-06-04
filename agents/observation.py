import math
from engine.physics import PlayerState, PlayerAttrs
from engine.ball import BallState

MAX_BALL_SPEED_MPH = 60.0
MIN_BALL_SPEED_MPH = 20.0

# How many recent history entries to include in the prompt
HISTORY_WINDOW = 20


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
