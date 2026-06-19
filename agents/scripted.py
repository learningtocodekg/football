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

# Times are derived from the WR run physics (max_speed 9.5, accel 14): from rest,
# 5yd≈1.0s, 7yd≈1.3s, 10yd≈1.6s, 12yd≈1.9s. Routes that sell a fake carry a small
# (+~0.2s) deception cushion on the break. WR1 lines up on the LEFT (x=16), so
# 90°=inside (toward middle), 270°=toward his sideline.
ROUTES: dict[str, list[tuple[float, float]]] = {
    # Slant: 5yd stem (1.0s), then break inside at 45°
    "slant":       [(1.0, 0.0), (999, 45.0)],
    # Post: 10yd stem (1.8s incl. fake), then break inside toward the goalpost at 30°
    "post":        [(1.8, 0.0), (999, 30.0)],
    # Comeback: 12yd stem (1.9s), then plant and break back to the sideline at 225°
    "comeback":    [(1.9, 0.0), (999, 225.0)],
    # Out: 10yd stem (1.6s), then break flat to the sideline at 270°
    "out":         [(1.6, 0.0), (999, 270.0)],
    # Go: straight vertical fly route, no cuts (10yd stem then keep running)
    "go":          [(999, 0.0)],
    # Double move: 8yd stem (1.4s), fake inside at 90° (~0.5s), snap back upfield at 0°
    "double_move": [(1.4, 0.0), (1.9, 90.0), (999, 0.0)],
    # Curl: 10yd stem (1.8s), then hook back toward QB at 180° (settle ~2yd back)
    "curl":        [(1.8, 0.0), (999, 180.0)],
    # Zig: 5yd stem (1.0s), jab inside at 90° (~0.4s), snap out to the sideline at 270°
    "zig":         [(1.0, 0.0), (1.4, 90.0), (999, 270.0)],
    # Drag: 4yd stem (0.9s), then flat shallow cross inside at 90°
    "drag":        [(0.9, 0.0), (999, 90.0)],
    # Corner: 10yd stem (1.8s incl. fake), then break to the deep sideline corner at 315°
    "corner":      [(1.8, 0.0), (999, 315.0)],
    # Post-corner: 10yd stem (1.8s), fake post inside at 45° (~0.4s), flip to corner at 315°
    "post_corner": [(1.8, 0.0), (2.2, 45.0), (999, 315.0)],
    # In (dig): 10yd stem (1.6s), then hard inside cut across at 90°
    "in":          [(1.6, 0.0), (999, 90.0)],
}

# Routes whose final leg is a STOP: the WR breaks back a short distance, then plants
# and sits in place (the ball comes back to him). The rail and the QB solver both use
# these so the WR's stop and the QB's target spot agree.
SETTLE_ROUTES: set[str] = {"comeback", "curl"}
SETTLE_DISTANCE: float = 1.5  # yd the WR travels past the break before he plants

# One-line PURPOSE per route, shown to the WR every step (vague intent + deception feel, not exact
# angles — the WR figures out the execution). Only consumer: observation_wr.py.
ROUTE_DESCRIPTIONS: dict[str, dict] = {
    "slant": {
        "purpose": (
            "Sell that you're running vertical, then break inside underneath and accelerate away "
            "before he can flip his hips to drive on it."
        ),
    },
    "post": {
        "purpose": (
            "Push upfield like a go to put him on his heels, then once he's committed to the "
            "vertical break inside toward the deep middle."
        ),
    },
    "comeback": {
        "purpose": (
            "Drive him deep into his backpedal, then plant and come back to the ball — his deep "
            "momentum can't recover in time. Settle facing the QB; don't keep running."
        ),
    },
    "out": {
        "purpose": (
            "Threaten him deep to get his weight sinking, then snap off flat toward the sideline "
            "where his depth leaves him."
        ),
    },
    "go": {
        "purpose": (
            "Near the end of the stem convince the CB you are about to cut left or right; once he "
            "commits, beat him straight up the field in a pure speed race."
        ),
    },
    "double_move": {
        "purpose": (
            "Sell a real inside cut to turn his hips and get him to bite, then once he does snap "
            "back upfield and run past him."
        ),
    },
    "curl": {
        "purpose": (
            "Push hard upfield so he turns and runs with you, then hook back underneath into the "
            "space he vacated. Settle facing the QB."
        ),
    },
    "zig": {
        "purpose": (
            "Jab hard one way to lean his hips, then snap back the other way the moment he commits."
        ),
    },
    "drag": {
        "purpose": (
            "Threaten vertical just long enough to freeze his feet, then cross flat underneath into "
            "the space he gave up."
        ),
    },
    "corner": {
        "purpose": (
            "Stem deep to stack him on your hip, then break off toward the sideline corner where he "
            "can't follow both your direction and your depth."
        ),
    },
    "post_corner": {
        "purpose": (
            "Sell a post inside to pull him toward the middle, then once he leans inside flip back "
            "outside to the corner."
        ),
    },
    "in": {
        "purpose": (
            "Press him vertical to keep him backpedaling, then cut hard across the middle while he's "
            "still moving the wrong way."
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
    ball's flight time (from the 3D arc physics), then throws to that position.
    Uses the same physics as the real game loop so the target is always accurate.

    throw_t:  seconds after snap to release
    wr_agent: the ScriptedWR instance (set by runner after construction)
    wr_attrs: the WR's PlayerAttrs (set by runner after construction)
    arc:      arc profile for the throw ("bullet" | "drive" | "touch" | "loft")
    """

    SIM_DT = 0.05  # step size for WR position simulation (small = accurate)

    def __init__(self, throw_t: float, arc: str = "bullet"):
        self.throw_t = throw_t
        self.arc = arc
        self.wr_agent: ScriptedWR | None = None
        self.wr_attrs = None
        self.target: list[float] | None = None
        self.last_action: dict = {"action": "hold", "reasoning": "scripted QB"}
        self.call_count = 0
        self.parse_errors = 0

    def _flight_time(self, dist: float) -> float:
        from engine.ball import solve_arc
        sol = solve_arc(dist, self.arc)
        return sol[0] if sol else 0.0

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
        eta = self._flight_time(dist0)

        if self.wr_agent and self.wr_attrs:
            future = simulate_wr(wr_state, eta)
            # Second pass: refine eta with the lead distance
            dist1 = math.hypot(future.x - qb_x, future.y - qb_y)
            eta2 = self._flight_time(dist1)
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
            "arc": self.arc,
            "reasoning": f"scripted {self.arc} throw at t={self.throw_t} to WR future pos eta~{eta2:.2f}s",
        }
        self.last_action = action
        return action
