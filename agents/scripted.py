"""
Scripted (non-LLM) agents for Phase A1/A2.

Route geometries (expected designs — WR improvises exact execution):
  slant    — upfield 2.0s, cut inside at 40°
  post     — upfield 2.5s, cut inside at 45° (toward center/goal post)
  comeback — upfield 2.5s, decelerate and cut back toward QB at 180°
  out      — upfield 1.8s, cut outside toward sideline at 315° (left WR) or 45° mirrored

ScriptedCB — man coverage with 0.3s reaction delay.
ScriptedQB — throws to a fixed target at a fixed time (no LLM, for CB testing).
"""
import math
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff, heading_to_dxdy


# ── Route definitions ─────────────────────────────────────────────────────────
# Each route is: list of (time_threshold, target_heading_degrees)
# The WR uses the heading for the first phase whose threshold is not yet exceeded.
# Heading 0° = straight upfield, 90° = right, 180° = back toward QB, 270° = left.

ROUTES: dict[str, list[tuple[float, float]]] = {
    # Straight upfield, then sharp inside cut
    "slant":    [(2.0, 0.0), (999, 40.0)],
    # Straight upfield longer, then diagonal toward middle of field (post)
    "post":     [(2.5, 0.0), (999, 45.0)],
    # Straight upfield, then turn back toward QB
    "comeback": [(2.5, 0.0), (999, 180.0)],
    # Quick upfield burst, then cut outside toward sideline
    "out":      [(1.8, 0.0), (999, 315.0)],
}


class ScriptedWR:
    """
    Runs a called route. Route name maps to a sequence of (time, heading) phases.
    The WR sprints at full throttle throughout, steering toward the phase heading.
    """

    def __init__(self, route: str = "slant"):
        if route not in ROUTES:
            raise ValueError(f"Unknown route '{route}'. Valid: {list(ROUTES)}")
        self.route = route
        self._phases = ROUTES[route]

    def _target_heading(self, t: float) -> float:
        for threshold, heading in self._phases:
            if t < threshold:
                return heading
        return self._phases[-1][1]

    def move(self, t: float, state: PlayerState, attrs: PlayerAttrs, dt: float = 0.1) -> PlayerState:
        target = self._target_heading(t)
        diff = angle_diff(target, state.heading)
        turn = max(-90.0, min(90.0, diff))
        return apply_action(state, attrs, turn, "accelerate", dt)


class ScriptedCB:
    """
    Man coverage. Stays hip-to-hip with WR for the first LOCKUP_DURATION seconds
    (mirroring the WR's current heading/position), then applies REACTION_DELAY
    so the CB must react to cuts the WR makes after that point.
    """

    REACTION_DELAY = 0.3   # seconds — delay applied after lockup phase
    LOCKUP_DURATION = 2.0  # seconds — CB stays tight with WR before cut reaction kicks in

    def __init__(self):
        self._history: list[tuple[float, PlayerState]] = []

    def record_wr(self, t: float, wr: PlayerState) -> None:
        self._history.append((t, wr))

    def _delayed_wr(self, t: float) -> PlayerState:
        target_t = t - self.REACTION_DELAY
        delayed = None
        for ht, hw in self._history:
            if ht <= target_t:
                delayed = hw
            else:
                break
        return delayed or (self._history[0][1] if self._history else None)

    def move(
        self,
        t: float,
        cb: PlayerState,
        cb_attrs: PlayerAttrs,
        wr_current: PlayerState,
        dt: float = 0.1,
    ) -> PlayerState:
        # During lockup phase, mirror WR's current position with no delay — CB stays
        # on WR's hip. After lockup, apply reaction delay so cuts create separation.
        if t < self.LOCKUP_DURATION:
            wr_ref = wr_current
        else:
            wr_ref = self._delayed_wr(t) or wr_current

        dist_to_wr = math.hypot(cb.x - wr_ref.x, cb.y - wr_ref.y)

        # If CB is still closing (more than 1 yd away), chase WR's position directly.
        # Once within 1 yd, mirror WR's heading to stay on their hip.
        if dist_to_wr > 1.0:
            tx = wr_ref.x
            ty = wr_ref.y
        else:
            dx, dy = heading_to_dxdy(wr_ref.heading)
            tx = cb.x + dx
            ty = cb.y + dy

        dx = tx - cb.x
        dy = ty - cb.y
        target_heading = math.degrees(math.atan2(dx, dy)) % 360.0

        diff = angle_diff(target_heading, cb.heading)
        turn = max(-90.0, min(90.0, diff))
        return apply_action(cb, cb_attrs, turn, "accelerate", dt)


class ScriptedQB:
    """
    Throws to the WR's exact future position at a fixed time. No LLM calls.

    At throw_t, simulates the WR forward along its scripted route for exactly the
    ball's flight time, then throws to that position. Uses the same physics as the
    real game loop so the target is always accurate.

    throw_t:        seconds after snap to release
    wr_agent:       the ScriptedWR instance (set by runner after construction)
    wr_attrs:       the WR's PlayerAttrs (set by runner after construction)
    ball_speed_mph: throw speed
    """

    MPH_TO_YDS_S = 1.46667
    SIM_DT = 0.05  # step size for WR position simulation (small = accurate)

    def __init__(self, throw_t: float, ball_speed_mph: float = 45.0):
        self.throw_t = throw_t
        self.ball_speed_mph = ball_speed_mph
        self.wr_agent: ScriptedWR | None = None
        self.wr_attrs = None
        self.target: list[float] | None = None
        self.last_action: dict = {"action": "hold", "reasoning": "scripted QB"}
        self.call_count = 0
        self.parse_errors = 0

    def decide(self, observation: str, qb_x: float, qb_y: float,
               wr_x: float = 0.0, wr_y: float = 0.0,
               wr_heading: float = 0.0, wr_speed: float = 0.0,
               t: float = 0.0, **kwargs) -> dict:
        t_val = t

        if t_val < self.throw_t:
            self.last_action = {"action": "hold", "reasoning": "scripted QB holding"}
            return self.last_action

        # Simulate WR forward along its scripted route to find where it will be
        # when the ball arrives. Iterate: simulate eta seconds, recompute eta with
        # new distance, repeat once to converge.
        from engine.physics import PlayerState
        wr_state = PlayerState(x=wr_x, y=wr_y, speed=wr_speed, heading=wr_heading,
                               facing=wr_heading, mode="normal")
        speed_yds = self.ball_speed_mph * self.MPH_TO_YDS_S

        def simulate_wr(state, duration):
            t = t_val
            elapsed = 0.0
            while elapsed < duration:
                dt = min(self.SIM_DT, duration - elapsed)
                state = self.wr_agent.move(t + elapsed, state, self.wr_attrs, dt)
                elapsed += dt
            return state

        # First pass: estimate eta from current WR position
        dist0 = math.hypot(wr_x - qb_x, wr_y - qb_y)
        eta = dist0 / speed_yds if dist0 > 0 else 0.0

        if self.wr_agent and self.wr_attrs:
            future = simulate_wr(wr_state, eta)
            # Second pass: refine eta with the lead distance
            dist1 = math.hypot(future.x - qb_x, future.y - qb_y)
            eta2 = dist1 / speed_yds if dist1 > 0 else 0.0
            future = simulate_wr(wr_state, eta2)
            target = [round(future.x, 1), round(future.y, 1)]
        else:
            # Fallback: use current WR position
            target = [round(wr_x, 1), round(wr_y, 1)]
            eta2 = eta

        self.target = target
        action = {
            "action": "throw",
            "target_coord": target,
            "ball_speed_mph": self.ball_speed_mph,
            "reasoning": f"scripted throw at t={self.throw_t} to WR future pos eta≈{eta2:.2f}s",
        }
        self.last_action = action
        return action
