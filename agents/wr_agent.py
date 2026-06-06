import math
from pathlib import Path
from .llm_client import call_llm
from .schema import parse_wr_pre_snap, parse_wr_live
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "wr_system.txt").read_text()
_PRE_SNAP_PROMPT = (Path(__file__).parent / "prompts" / "wr_pre_snap.txt").read_text()
_LIVE_FREE_PROMPT = (Path(__file__).parent / "prompts" / "wr_live_free.txt").read_text()
_LIVE_COMMITTED_PROMPT = (Path(__file__).parent / "prompts" / "wr_live_committed.txt").read_text()
_LIVE_BROKEN_PROMPT = (Path(__file__).parent / "prompts" / "wr_live_broken.txt").read_text()
_BALL_IN_AIR_PROMPT = (Path(__file__).parent / "prompts" / "wr_ball_in_air.txt").read_text()

# How many degrees of heading change in one step counts as a detected cut
CUT_DETECT_THRESHOLD = 30.0

# ±45° tolerance: WR may only call for ball if heading is within this of prescribed cut heading
CALL_HEADING_TOLERANCE = 45.0


class WRAgent:
    def __init__(
        self,
        model: str = "gpt-5-nano",
        reasoning_effort: str | None = "low",
        provider: str = "openai",
        route: str = "slant",
        cut_time: float = 2.0,
        cut_heading: float = 40.0,
        upfield_yards: float = 5.0,
        call_tolerance: float = 45.0,
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.route = route
        self.cut_time = cut_time
        self.cut_heading = cut_heading
        self.upfield_yards = upfield_yards
        self.call_tolerance = call_tolerance

        self.call_count = 0
        self.parse_errors = 0

        # Play state
        self.called_for_ball: bool = False
        self.call_t: float | None = None
        self.call_heading: float | None = None
        self.locked_heading: float | None = None
        self.broken_play: bool = False
        self.detected_cut_t: float | None = None
        self._prev_heading: float | None = None
        self._pre_snap_plan: str = ""
        self.last_action: dict = {}

    def pre_snap(self, observation: str) -> dict:
        self.call_count += 1
        raw = call_llm(_SYSTEM_PROMPT, observation + "\n\n" + _PRE_SNAP_PROMPT,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_wr_pre_snap(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [WR pre-snap parse error] raw={raw[:120]!r}")
            return {"plan": "run the route", "reasoning": "parse_error"}
        self._pre_snap_plan = result["plan"]
        return result

    def decide(self, observation: str, ball_in_air: bool = False, t: float = 0.0) -> dict:
        """Per-step decision. Returns heading, facing, throttle, call_for_ball."""
        self.call_count += 1

        if ball_in_air:
            prompt = _BALL_IN_AIR_PROMPT
        elif self.broken_play:
            prompt = _LIVE_BROKEN_PROMPT
        elif self.called_for_ball:
            prompt = _LIVE_COMMITTED_PROMPT
        else:
            prompt = _LIVE_FREE_PROMPT

        raw = call_llm(_SYSTEM_PROMPT, observation + "\n\n" + prompt,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_wr_live(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [WR live parse error] raw={raw[:120]!r}")
            fallback_heading = self.locked_heading if self.called_for_ball else 0.0
            return {
                "heading": fallback_heading or 0.0,
                "facing": fallback_heading or 0.0,
                "throttle": "accelerate",
                "call_for_ball": False,
                "reasoning": "parse_error",
            }

        # Validate and apply call_for_ball
        if result["call_for_ball"] and not self.called_for_ball:
            if self._can_call(result["heading"]):
                self.called_for_ball = True
                self.call_heading = result["heading"]
                self.locked_heading = result["heading"]
                self.call_t = t
            else:
                result["call_for_ball"] = False

        self.last_action = result
        return result

    def _can_call(self, heading: float) -> bool:
        """Call is valid if heading is within tolerance of prescribed cut heading, or broken play."""
        if self.broken_play:
            return True
        if self.cut_time >= 9.0:  # go route — no prescribed cut, any heading is valid
            return True
        diff = abs((heading - self.cut_heading + 180.0) % 360.0 - 180.0)
        return diff <= self.call_tolerance

    def record_heading(self, t: float, heading: float) -> None:
        """Call each step to detect cuts from heading history."""
        if self._prev_heading is not None and self.detected_cut_t is None:
            diff = abs((heading - self._prev_heading + 180.0) % 360.0 - 180.0)
            if diff >= CUT_DETECT_THRESHOLD:
                self.detected_cut_t = t
        self._prev_heading = heading

    def apply_decision(
        self,
        decision: dict,
        state: PlayerState,
        attrs: PlayerAttrs,
        dt: float = 0.1,
        ball_in_air: bool = False,
    ) -> PlayerState:
        """Convert WR decision to new PlayerState. If committed (not ball_in_air), lock heading."""
        if self.called_for_ball and not ball_in_air and self.locked_heading is not None:
            target_heading = self.locked_heading
        else:
            target_heading = float(decision.get("heading", state.heading))

        target_facing = float(decision.get("facing", target_heading))
        throttle = decision.get("throttle", "accelerate")
        engine_throttle = "brake" if throttle == "brake" else "accelerate"

        turn = angle_diff(target_heading, state.heading)
        turn = max(-90.0, min(90.0, turn))

        return apply_action(state, attrs, turn, engine_throttle, dt, new_facing=target_facing)

    def trigger_broken_play(self) -> None:
        if not self.broken_play:
            self.broken_play = True
            print("  [WR] BROKEN PLAY triggered")
