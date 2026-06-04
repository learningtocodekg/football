"""
Scripted (non-LLM) agents for Phase A1.

Route geometries (expected designs — WR improvises exact execution):
  slant    — upfield 2.0s, cut inside at 40°
  post     — upfield 2.5s, cut inside at 45° (toward center/goal post)
  comeback — upfield 2.5s, decelerate and cut back toward QB at 180°
  out      — upfield 1.8s, cut outside toward sideline at 315° (left WR) or 45° mirrored

ScriptedCB — man coverage with 0.3s reaction delay.
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
