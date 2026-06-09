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
    # Slant: ~14 yd upfield stem (2.0s), then diagonal inside cut at 45°
    "slant":       [(2.0, 0.0), (999, 45.0)],
    # Post: ~31 yd upfield stem (4.0s), then diagonal toward goalpost at 30°
    "post":        [(4.0, 0.0), (999, 30.0)],
    # Comeback: ~19 yd upfield stem (2.5s), then turn back toward QB at 180°
    "comeback":    [(2.5, 0.0), (999, 180.0)],
    # Out: upfield stem, then cut hard to the sideline
    "out":         [(1.8, 0.0), (999, 315.0)],
    # Go: straight vertical fly route, no cuts
    "go":          [(999, 0.0)],
    # Double move: stem upfield, fake right (outside), snap back upfield
    "double_move": [(1.5, 0.0), (2.2, 90.0), (999, 0.0)],
    # Curl: ~19 yd upfield stem (2.5s), then hook back toward QB at 180°
    "curl":        [(2.5, 0.0), (999, 180.0)],
    # Zig: ~6 yd upfield (1.0s), jab left at 270° for ~4 yd (0.5s), snap right at 90°
    "zig":         [(1.0, 0.0), (1.5, 270.0), (999, 90.0)],
    # Drag: ~6 yd upfield stem (1.0s), then flat cross at 90°
    "drag":        [(1.0, 0.0), (999, 90.0)],
    # Corner: ~19 yd upfield stem (2.5s), then diagonal to corner of end zone at 290°
    "corner":      [(2.5, 0.0), (999, 290.0)],
    # Post-corner: stem up, fake post inside at 45°, flip to corner outside at 315°
    "post_corner": [(2.0, 0.0), (2.4, 45.0), (999, 315.0)],
    # In (dig): ~14 yd upfield stem (2.0s), then hard inside cut at 90°
    "in":          [(2.0, 0.0), (999, 90.0)],
}

# Per-route metadata for agents and observers.
# call_tolerance: how many degrees from cut_heading the WR heading can be when calling for ball.
#   Default 45°. Set higher for routes where the call happens before the final cut direction.
ROUTE_META: dict[str, dict] = {
    # Curl: WR should call at ~270° (beginning of turn, one step before full 180°).
    # Raise tolerance to 135° so calling at 270° (135° off from 180°) is permitted.
    "curl": {"call_tolerance": 135.0},
}

# Plain-English route descriptions shown to the WR every step.
# description: what the route looks like and the purpose of each phase.
# phase_labels: short label for each phase (matches ROUTES phase order).
ROUTE_DESCRIPTIONS: dict[str, dict] = {
    "slant": {
        "description": (
            "The upfield stem pushes the CB into a backward lean. When you cut inside, "
            "the CB must reverse his momentum — that reversal is your window. "
            "Accelerate hard through the cut."
        ),
    },
    "comeback": {
        "description": (
            "Drive the CB deep into a backpedal. The more backward momentum he builds, "
            "the harder it is for him to reverse when you stop and come back. "
            "Call as soon as you've turned."
        ),
    },
    "go": {
        "description": (
            "Speed only — no cuts. Win by outrunning the CB vertically. "
            "Call when you feel you have a step on him."
        ),
    },
    "double_move": {
        "description": (
            "The outside fake must look real enough to move the CB's hips toward the sideline. "
            "A weak drift won't commit him — go deep to ~90° and hold until his rec shows. "
            "Then snap back upfield and go."
        ),
    },
    "curl": {
        "description": (
            "The upfield push IS the deception — the CB backtracks and creates space underneath. "
            "Do not add sideways fakes during the stem; they add recovery cost that kills your hook. "
            "Hook back at 180° and call immediately."
        ),
    },
    "zig": {
        "description": (
            "The leftward jab must reach ~270° and hold long enough to move the CB's hips left. "
            "A shallow drift does nothing. Hold the jab until CB rec appears, then snap right."
        ),
    },
    "drag": {
        "description": (
            "The brief upfield stem makes the CB think vertical and step back. "
            "Your flat cross runs into the space he just vacated. Stay low and call when across."
        ),
    },
    "corner": {
        "description": (
            "The long stem pushes the CB deep into a backpedal. "
            "Your diagonal break to the corner forces him to change both direction and depth — "
            "that transition is your window."
        ),
    },
    "post_corner": {
        "description": (
            "The inside fake at 45° must look real enough to move the CB inside. "
            "Then flip outside to 315°. If the CB doesn't bite on the inside fake, "
            "you won't have a window on the outside break."
        ),
    },
    "in": {
        "description": (
            "The upfield stem pulls the CB backward. When you cut across at 90°, "
            "the CB must change from backpedaling to closing sideways — that transition is your window. "
            "Don't flatten out early or the CB stays in position."
        ),
    },
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
