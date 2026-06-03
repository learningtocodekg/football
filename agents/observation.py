import math
from engine.physics import PlayerState, PlayerAttrs, heading_to_dxdy
from engine.ball import BallState, MPH_TO_YDS

MAX_BALL_SPEED_MPH = 60.0
MIN_BALL_SPEED_MPH = 20.0


def _dist(a: PlayerState, b: PlayerState) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _extrapolate(state: PlayerState, t: float) -> tuple[float, float]:
    dx, dy = heading_to_dxdy(state.heading)
    return state.x + dx * state.speed * t, state.y + dy * state.speed * t


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
) -> str:
    current_sep = _dist(wr, cb)
    max_mph = MIN_BALL_SPEED_MPH + (qb_attrs.throw_power / 99.0) * (MAX_BALL_SPEED_MPH - MIN_BALL_SPEED_MPH)

    # Projected throw options: for each horizon T, where will WR/CB be?
    horizons = [0.3, 0.5, 0.7, 0.9, 1.1]
    options = []
    for T in horizons:
        wx, wy = _extrapolate(wr, T)
        cx, cy = _extrapolate(cb, T)
        sep_at_T = math.hypot(wx - cx, wy - cy)
        dist_to_target = math.hypot(wx - qb.x, wy - qb.y)
        speed_needed_mph = (dist_to_target / T) / MPH_TO_YDS
        feasible = MIN_BALL_SPEED_MPH <= speed_needed_mph <= max_mph
        options.append({
            "T": T,
            "wr": (round(wx, 1), round(wy, 1)),
            "cb": (round(cx, 1), round(cy, 1)),
            "sep": round(sep_at_T, 2),
            "mph": round(speed_needed_mph, 1),
            "ok": feasible,
        })

    lines = [
        f"=== QB OBSERVATION  t={t:.1f}s  sack_clock={sack_clock:.1f}s ===",
        "",
        f"YOU (QB):  pos=({qb.x:.1f}, {qb.y:.1f})  speed={qb.speed:.1f}yd/s",
        f"WR1:       pos=({wr.x:.1f}, {wr.y:.1f})  speed={wr.speed:.1f}yd/s  heading={wr.heading:.0f}°",
        f"CB1:       pos=({cb.x:.1f}, {cb.y:.1f})  speed={cb.speed:.1f}yd/s  heading={cb.heading:.0f}°",
        f"Current WR-CB separation: {current_sep:.2f} yd",
        "",
        "PROJECTED THROW OPTIONS (throw NOW, ball arrives in T seconds):",
        f"  {'T':>4}  {'WR pos':>14}  {'CB pos':>14}  {'sep':>6}  {'mph':>6}  feasible?",
    ]
    for o in options:
        feas = "YES" if o["ok"] else "NO — out of range"
        lines.append(
            f"  {o['T']:>4.1f}  {str(o['wr']):>14}  {str(o['cb']):>14}"
            f"  {o['sep']:>6.2f}  {o['mph']:>6.1f}  {feas}"
        )

    lines += [
        "",
        f"Your throw_power allows ball speeds {MIN_BALL_SPEED_MPH:.0f}–{max_mph:.0f} mph.",
        "Ball travels straight-line to target_coord.",
        "WR must be within ~1.3 yd of target_coord when ball arrives (lead him!).",
        "",
        "ACTIONS:",
        '  hold  → {"action":"hold","reasoning":"..."}',
        '  throw → {"action":"throw","target_coord":[x,y],"ball_speed_mph":45,"reasoning":"..."}',
    ]
    return "\n".join(lines)
