"""
Scripted (non-LLM) agents for Phase A1.

ScriptedWR  — slant route: sprint upfield for 2 s, then cut inside (heading 40°).
ScriptedCB  — man coverage: mirror WR movement with a 0.3 s reaction delay.
"""
import math
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff


class ScriptedWR:
    """Runs a slant: upfield (heading 0°) until t=2.0 s, then cuts inside (heading 40°)."""

    CUT_TIME = 2.0     # seconds into play when WR breaks
    CUT_HEADING = 40.0  # degrees (slightly right of upfield = inside slant)

    def move(self, t: float, state: PlayerState, attrs: PlayerAttrs, dt: float = 0.1) -> PlayerState:
        target = 0.0 if t < self.CUT_TIME else self.CUT_HEADING
        diff = angle_diff(target, state.heading)
        turn = max(-90.0, min(90.0, diff))
        return apply_action(state, attrs, turn, "accelerate", dt)


class ScriptedCB:
    """
    Man coverage with reaction delay.
    Records WR state history; uses the state from REACTION_DELAY seconds ago
    to determine the current movement target.
    """

    REACTION_DELAY = 0.3  # seconds

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
        wr_ref = self._delayed_wr(t) or wr_current

        # Aim at WR's position plus a small upfield cushion
        tx = wr_ref.x
        ty = wr_ref.y + 1.5  # stay slightly upfield of WR

        dx = tx - cb.x
        dy = ty - cb.y
        target_heading = math.degrees(math.atan2(dx, dy)) % 360.0

        diff = angle_diff(target_heading, cb.heading)
        turn = max(-90.0, min(90.0, diff))
        return apply_action(cb, cb_attrs, turn, "accelerate", dt)
