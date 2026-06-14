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
            "This is a STOP route. Drive the CB deep into a backpedal, then plant and break "
            "back toward your sideline - but only 1-2 yards, then STOP. Brake hard out of the "
            "cut and settle in place, squaring up to face the QB; the ball comes back to YOU, "
            "you do not keep running through the break. The CB's deep momentum can't reverse "
            "in time - that gap is your window. Plant and call, then brake to settle (do not "
            "keep sprinting back) so the QB can put a bullet on you where you stop."
        ),
    },
    "go": {
        "description": (
            "The first ~10 yards are the stem; the break is just to keep running straight. Win with pure speed. "
            "Once you are past 10 yards and feel your pace is about to break the cushion, call for the ball so the "
            "throw leads you deep — don't call on the pre-snap cushion. A fake break during the stem (sell a cut, "
            "then keep sprinting straight) turns the CB's hips and buys you the step."
        ),
    },
    "double_move": {
        "description": (
            "The inside fake (90°) must look real enough to move the CB's hips inside. "
            "A weak drift won't commit him — sell it to ~90° and hold until his rec shows. "
            "Then snap back upfield (0°) and go deep."
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
            "The inside jab (90°) must hold long enough to move the CB's hips inside. "
            "A shallow drift does nothing. Hold the jab until CB rec appears, then snap out to the sideline (270°)."
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


# ── Soft route rail ────────────────────────────────────────────────────────────
# A safety net (NOT a cage) that guarantees the WR runs the called route's SHAPE,
# while leaving juke / break-timing / call entirely free. Each tick govern() may
# correct the WR's heading or throttle as a backstop; status() narrates that backstop
# for the observation so the WR knows the deadline and can act earlier on its own.
LEASH_DISTANCE = 2.0        # yd the WR may stray off his route LINE before being steered back
LEASH_BACK_TOL = 0.75       # yd the WR may move BACKWARD along the leg (wrong way) before steered back
LEASH_LOOKAHEAD = 3.0       # yd ahead on the route line to aim for when recovering
STEM_CONE = 25.0            # deg the WR may feint off a non-final leg's heading. Kept small: a hard
                            # turn sheds ~40% of speed (engine physics), so continuous wide weaving
                            # kills the stem and the route arrives late. Designed cuts/fakes are full
                            # angle regardless — the cone is measured around the CURRENT leg's heading.
EARLY_BREAK_WINDOW = 0.6    # s before the scheduled cut the WR may trigger the break early (a read)
BREAK_COMMIT_TOL = 45.0     # deg: outputting within this of the next cut heading = committing the break


def _burst_distance(seconds: float, v_max: float = 9.5, accel: float = 14.0) -> float:
    """Yards covered from rest over `seconds` under the burst-accel model (same model the
    route cut-times were derived from). Used to turn the stem's duration into a DEPTH."""
    if accel <= 0 or v_max <= 0:
        return v_max * seconds
    k = accel / v_max
    return v_max * seconds - (v_max / k) * (1.0 - math.exp(-k * seconds))


class RouteRail:
    """Per-play soft rail for one WR running `route`. Owns the leg-progression state.

    Off-route is measured POSITIONALLY (how far off the current leg's line the WR has
    strayed), not per-tick heading — so a brief juke is free but a sustained bail is
    pulled back. The STEM break is DEPTH-gated (the WR must reach the route's designed
    depth before breaking, even if he dawdles/jukes); intermediate fakes are duration-
    gated (they must hold their deception time).
    """

    def __init__(self, route: str):
        self.route = route
        phases = ROUTES.get(route, ROUTES["slant"])
        # Expand phases into legs with explicit [start, end) times.
        self.legs: list[dict] = []
        prev = 0.0
        for thr, hdg in phases:
            self.legs.append({"hdg": hdg, "start": prev, "end": thr})
            prev = thr
        self.settle = route in SETTLE_ROUTES
        # The depth (yd downfield from the snap) the stem must reach before breaking.
        self.stem_depth = _burst_distance(self.legs[0]["end"]) if len(self.legs) > 1 else 0.0
        # play state
        self.leg_i = 0
        self.leg_origin: tuple[float, float] | None = None  # WR pos where the current leg began
        self.leg_enter_t = 0.0
        self.settle_origin: tuple[float, float] | None = None
        self.settled = False
        self.pending_call = False  # WR asked to call before the route was ready; fire it when it is

    def _is_settle_leg(self) -> bool:
        return self.settle and self.leg_i == len(self.legs) - 1

    def _call_allowed(self) -> bool:
        """A call is only legal once the route's FINAL break is made (stem finished) — the
        WR is on the last leg. For a settle route that means AS HE STARTS the break back
        (the ball should arrive as he hooks and the CB's deep momentum carries him past,
        not after he has sat and the CB has driven back down)."""
        return self.leg_i == len(self.legs) - 1

    def _enter_leg(self, i: int, wr: PlayerState, t: float) -> None:
        self.leg_i = i
        self.leg_origin = (wr.x, wr.y)
        self.leg_enter_t = t

    def _along_perp(self, wr: PlayerState) -> tuple[float, float, float, float]:
        """Decompose WR's offset from the leg line into (along, perp, ux, uy)."""
        ox, oy = self.leg_origin
        ux, uy = heading_to_dxdy(self.legs[self.leg_i]["hdg"])
        rx, ry = wr.x - ox, wr.y - oy
        along = rx * ux + ry * uy
        perp = math.hypot(rx - along * ux, ry - along * uy)
        return along, perp, ux, uy

    def _recover_heading(self, wr: PlayerState) -> float:
        """Heading that curves the WR back onto the leg line (aim a bit ahead)."""
        along, _, ux, uy = self._along_perp(wr)
        ox, oy = self.leg_origin
        tx = ox + (along + LEASH_LOOKAHEAD) * ux
        ty = oy + (along + LEASH_LOOKAHEAD) * uy
        return math.degrees(math.atan2(tx - wr.x, ty - wr.y)) % 360.0

    def govern(self, t: float, wr: PlayerState, decision: dict) -> dict:
        """Return a possibly-corrected decision and advance the rail state."""
        if self.leg_origin is None:
            self.leg_origin = (wr.x, wr.y)
        intended = float(decision.get("heading", wr.heading))

        # 1. Leg progression.
        #    STEM (leg 0): DEPTH-gated — the WR breaks only once he has run the route's
        #      designed depth (so a dawdling/juking stem still reaches full depth). He may
        #      trigger the break a touch early (a read) once past 70% depth.
        #    FAKE (intermediate leg): DURATION-gated — it must hold its deception time.
        auto_broke = False
        if self.leg_i + 1 < len(self.legs):
            nxt = self.legs[self.leg_i + 1]
            if self.leg_i == 0:
                depth = wr.y - self.leg_origin[1]  # stem runs upfield (heading 0)
                if depth >= self.stem_depth:
                    self._enter_leg(1, wr, t)
                    auto_broke = True
                elif (depth >= 0.7 * self.stem_depth
                        and abs(angle_diff(intended, nxt["hdg"])) <= BREAK_COMMIT_TOL):
                    self._enter_leg(1, wr, t)
            else:
                dur = self.legs[self.leg_i]["end"] - self.legs[self.leg_i]["start"]
                if t - self.leg_enter_t >= dur:
                    self._enter_leg(self.leg_i + 1, wr, t)
                    auto_broke = True

        expected = self.legs[self.leg_i]["hdg"]

        # 2. Settle detection: on the settle leg, mark planted once past the settle distance.
        on_settle = self._is_settle_leg()
        if on_settle:
            if self.settle_origin is None:
                self.settle_origin = (wr.x, wr.y)
            dist = math.hypot(wr.x - self.settle_origin[0], wr.y - self.settle_origin[1])
            if self.settled or dist >= SETTLE_DISTANCE:
                self.settled = True

        # 3. CALL GATE: the WR can only call once the route's FINAL break is made (the
        #    stem is finished). A call before that is HELD and auto-fires the moment the
        #    route is ready — the WR still decides to call; the rail only times it.
        want_call = bool(decision.get("call_for_ball"))
        if self._call_allowed():
            if want_call or self.pending_call:
                self.pending_call = False
                decision = {**decision, "call_for_ball": True}
        elif want_call:
            self.pending_call = True
            decision = {**decision, "call_for_ball": False}
        calling = bool(decision.get("call_for_ball"))

        # 4. Movement override.
        # Settle leg: run the break heading to the settle spot, then plant and stop.
        if on_settle:
            if self.settled:
                return {**decision, "heading": wr.heading, "throttle": "brake"}
            return {**decision, "heading": expected}
        # A CALL commits the WR to his route LINE — the QB throws to the real route,
        # never a transient juke heading.
        if calling:
            return {**decision, "heading": expected}

        is_final_leg = self.leg_i == len(self.legs) - 1

        # NON-FINAL leg (the stem, or an intermediate fake): the WR must actually RUN it,
        # so he keeps accelerating and may juke only within a CONE of the leg heading (no
        # reversing out of it). If he drifts too far off the line laterally, steer him back.
        # The full break freedom is saved for the final leg below.
        if not is_final_leg:
            _, perp, _, _ = self._along_perp(wr)
            if perp > LEASH_DISTANCE:
                return {**decision, "heading": self._recover_heading(wr), "throttle": "accelerate"}
            dev = max(-STEM_CONE, min(STEM_CONE, angle_diff(intended, expected)))
            return {**decision, "heading": (expected + dev) % 360.0, "throttle": "accelerate"}

        # Final leg. Auto-break forces the break heading the moment the deadline passes.
        if auto_broke:
            return {**decision, "heading": expected}
        # Positional leash: free to juke until the WR strays more than LEASH_DISTANCE off
        # his route line OR runs LEASH_BACK_TOL backward along it, then steer him back.
        along, perp, _, _ = self._along_perp(wr)
        if perp > LEASH_DISTANCE or along < -LEASH_BACK_TOL:
            return {**decision, "heading": self._recover_heading(wr)}
        return decision

    def status(self, t: float, wr: PlayerState) -> str:
        """One-line backstop narration for the WR observation."""
        leg = self.legs[self.leg_i]
        if self._is_settle_leg():
            if self.settled:
                return ("ROUTE STATUS: SETTLED — you are planted. CALL NOW and square to the QB; "
                        "the ball is coming back to you.")
            if self.settle_origin is not None:
                dist = math.hypot(wr.x - self.settle_origin[0], wr.y - self.settle_origin[1])
                left = max(0.0, SETTLE_DISTANCE - dist)
                return (f"ROUTE STATUS: breaking back at {leg['hdg']:.0f}° — CALL NOW as you hook; you PLANT "
                        f"& SIT in ~{left:.1f}yd. The ball should arrive as you settle, before the CB drives down.")
            return (f"ROUTE STATUS: break back at {leg['hdg']:.0f}° and CALL as you hook; you SIT ~{SETTLE_DISTANCE:.0f}yd back.")
        off = ""
        if self.leg_origin is not None:
            _, perp, _, _ = self._along_perp(wr)
            if perp > LEASH_DISTANCE * 0.6:
                off = f"  [{perp:.1f}yd off your route line — drift further and you're steered back.]"
        if self.leg_i + 1 < len(self.legs):
            nxt = self.legs[self.leg_i + 1]
            to_break = max(0.0, nxt["start"] - t)
            head = (f"ROUTE STATUS: on the STEM at {leg['hdg']:.0f}°. "
                    f"Auto-break to {nxt['hdg']:.0f}° in {to_break:.1f}s")
            if t >= nxt["start"] - EARLY_BREAK_WINDOW:
                head += " — or BREAK NOW (cut to that heading) if the CB has committed."
            else:
                head += ". Juke freely to move the CB; you'll be steered back if you stray off your line."
            last = " (this is your FINAL break)" if self.leg_i + 1 == len(self.legs) - 1 else " (a fake — more route after it)"
            return head + last + "  You CANNOT call yet — not until your final break." + off
        return (f"ROUTE STATUS: final leg — run {leg['hdg']:.0f}°"
                + (" (a go has NO break — run and beat him deep, then call)." if len(self.legs) == 1
                   else " — your final break is made; CALL when you have real separation.")
                + " Sustained drift off this line is auto-corrected." + off)


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
