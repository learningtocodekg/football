"""
Deterministic WR end-route execution + the QB lead-throw solver.

When the WR "calls for the ball" it declares an `end_route` — the remainder of its motion as a
simple script. From that moment the engine drives the WR deterministically (no LLM) until the ball
is in the air, then the WR comes alive to adjust. Because the post-call path is deterministic, the
QB's throw can be led EXACTLY: the engine simulates the WR forward and solves the meeting point.

end_route = {
  "heading": float,           # final committed run direction (deg)
  "mode": "run" | "settle",
  "settle_ticks": int|None,   # settle only: run heading this many 0.1s ticks, then brake & hold
}
"""
import math

from .physics import PlayerState, PlayerAttrs, apply_action, angle_diff
from .ball import solve_arc, max_ball_speed, DEFAULT_TARGET_Z


def _normalize(end_route: dict) -> dict:
    heading = float(end_route.get("heading", 0.0)) % 360.0
    mode = str(end_route.get("mode", "run")).strip().lower()
    if mode not in ("run", "settle"):
        mode = "run"
    st = end_route.get("settle_ticks")
    settle_ticks = int(st) if isinstance(st, (int, float)) else (8 if mode == "settle" else None)
    return {"heading": heading, "mode": mode, "settle_ticks": settle_ticks}


def step_endroute(
    state: PlayerState,
    attrs: PlayerAttrs,
    end_route: dict,
    progress_ticks: int,
    dt: float = 0.1,
) -> PlayerState:
    """Advance one deterministic step along the end_route. `progress_ticks` = ticks executed so far
    in this end_route, including this one (1 on the first deterministic step)."""
    er = _normalize(end_route)
    turn = max(-90.0, min(90.0, angle_diff(er["heading"], state.heading)))

    settling = (
        er["mode"] == "settle"
        and er["settle_ticks"] is not None
        and progress_ticks > er["settle_ticks"]
    )
    throttle = "brake" if settling else "accelerate"
    # Facing is cosmetic during deterministic execution; the WR fixes it when it comes alive in the
    # air. On a settle, square back toward the throw once planted so a frozen frame still looks right.
    facing = (er["heading"] + 180.0) % 360.0 if settling else er["heading"]
    return apply_action(state, attrs, turn, throttle, dt, new_facing=facing)


def simulate_endroute(
    state: PlayerState,
    attrs: PlayerAttrs,
    end_route: dict,
    progress_ticks: int,
    duration: float,
    dt: float = 0.05,
) -> PlayerState:
    """Where the WR will be `duration` seconds from now if it keeps running its end_route."""
    s = state
    elapsed = 0.0
    p = progress_ticks
    while elapsed < duration - 1e-9:
        step_dt = min(dt, duration - elapsed)
        # progress in 0.1s tick units (settle_ticks is expressed in 0.1s ticks)
        p_for_step = progress_ticks + int(round((elapsed + step_dt) / 0.1))
        s = step_endroute(s, attrs, end_route, p_for_step, step_dt)
        elapsed += step_dt
    return s


def solve_lead(
    qb_x: float,
    qb_y: float,
    wr_state: PlayerState,
    attrs: PlayerAttrs,
    end_route: dict,
    progress_ticks: int,
    arc: str,
    throw_power: float,
    target_z: float = DEFAULT_TARGET_Z,
    t_now: float = 0.0,
) -> dict:
    """Solve the self-consistent meeting point for a ball released NOW on `arc`.

    Finds tau where flight_time(arc, |WR(tau) - QB|) == tau by bisection (one crossing exists:
    flight time grows sublinearly with distance, tau linearly). Returns the lead target + whether
    the throw is within arm range for this arc.
    """
    v_max = max_ball_speed(throw_power)

    def residual(tau: float):
        future = simulate_endroute(wr_state, attrs, end_route, progress_ticks, tau)
        d = math.hypot(future.x - qb_x, future.y - qb_y)
        sol = solve_arc(d, arc, target_z)
        if sol is None:
            return None, future, d, None
        return sol[0] - tau, future, d, sol[1]  # (flight - tau, future_state, dist, launch_speed)

    lo, hi = 0.05, 6.0
    flo = residual(lo)[0]
    fhi = residual(hi)[0]
    if flo is None or fhi is None or (flo > 0) == (fhi > 0):
        # No clean crossing (arc can't reach his line in range). Best-effort: report position at a
        # nominal 1.0s lead and mark infeasible.
        _, fut, d, spd = residual(1.0)
        return {
            "target": [round(fut.x, 1), round(fut.y, 1)],
            "tau": 1.0, "arrival_t": round(t_now + 1.0, 2),
            "dist": round(d, 1), "feasible": False,
        }
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        fm = residual(mid)[0]
        if fm is None:
            hi = mid
            continue
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    tau = 0.5 * (lo + hi)
    _, fut, d, spd = residual(tau)
    feasible = spd is not None and spd <= v_max
    return {
        "target": [round(fut.x, 1), round(fut.y, 1)],
        "tau": round(tau, 2),
        "arrival_t": round(t_now + tau, 2),
        "dist": round(d, 1),
        "feasible": feasible,
    }
