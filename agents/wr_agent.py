import math
from pathlib import Path
from .llm_client import call_llm
from .schema import parse_wr_pre_snap, parse_wr_live, parse_wr_plan
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "wr_system.txt").read_text()
_PRE_SNAP_PROMPT = (Path(__file__).parent / "prompts" / "wr_pre_snap.txt").read_text()
_LIVE_FREE_PROMPT = (Path(__file__).parent / "prompts" / "wr_live_free.txt").read_text()
_LIVE_COMMITTED_PROMPT = (Path(__file__).parent / "prompts" / "wr_live_committed.txt").read_text()
_LIVE_BROKEN_PROMPT = (Path(__file__).parent / "prompts" / "wr_live_broken.txt").read_text()
_BALL_IN_AIR_PROMPT = (Path(__file__).parent / "prompts" / "wr_ball_in_air.txt").read_text()


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
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.route = route
        self.cut_time = cut_time
        self.cut_heading = cut_heading
        self.upfield_yards = upfield_yards

        self.call_count = 0
        self.parse_errors = 0

        # Play state
        self.called_for_ball: bool = False
        self.call_t: float | None = None
        self.call_heading: float | None = None
        self.locked_heading: float | None = None
        self.broken_play: bool = False
        self.detected_cut_t: float | None = None
        self._pre_snap_plan: str = ""
        self.last_action: dict = {}
        self.wr_note: str = ""  # persistent scratchpad, updated each step
        self._plan: list[dict] = []  # queued LIVE-free steps (no LLM call to consume)

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
        """Per-step decision. Returns heading, facing, throttle, call_for_ball.

        In the LIVE-free phase the WR emits a multi-step PLAN; subsequent steps are
        served from the queue WITHOUT an LLM call. The plan is aborted only when the
        ball is thrown.
        """
        if ball_in_air:
            self._plan = []
            return self._finalize(self._llm_decision(observation, _BALL_IN_AIR_PROMPT), t)

        # LIVE, ball held — serve a queued plan step if one is waiting.
        if self._plan:
            return self._finalize(self._plan.pop(0), t)

        if self.broken_play:
            return self._finalize(self._llm_decision(observation, _LIVE_BROKEN_PROMPT), t)
        if self.called_for_ball:
            return self._finalize(self._llm_decision(observation, _LIVE_COMMITTED_PROMPT), t)

        # Free phase: request a PLAN, queue the tail, return the first step.
        self.call_count += 1
        raw = call_llm(_SYSTEM_PROMPT, observation + "\n\n" + _LIVE_FREE_PROMPT,
                       self.model, self.reasoning_effort, self.provider)
        plan = parse_wr_plan(raw)
        if not plan:
            self.parse_errors += 1
            print(f"  [WR plan parse error] raw={raw[:120]!r}")
            fallback_heading = self.locked_heading if self.locked_heading is not None else 0.0
            return {
                "heading": fallback_heading,
                "facing": fallback_heading,
                "throttle": "accelerate",
                "call_for_ball": False,
                "reasoning": "parse_error",
                "wr_note": self.wr_note,
            }

        self._plan = plan[1:]
        return self._finalize(plan[0], t)

    def _llm_decision(self, observation: str, prompt: str) -> dict | None:
        """Single per-step LLM decision (ball-in-air / broken / committed phases)."""
        self.call_count += 1
        raw = call_llm(_SYSTEM_PROMPT, observation + "\n\n" + prompt,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_wr_live(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [WR live parse error] raw={raw[:120]!r}")
        return result

    def _finalize(self, step: dict | None, t: float) -> dict:
        """Apply call_for_ball, update scratchpad/last_action, return the step."""
        if step is None:
            fallback_heading = self.locked_heading if self.called_for_ball else 0.0
            return {
                "heading": fallback_heading or 0.0,
                "facing": fallback_heading or 0.0,
                "throttle": "accelerate",
                "call_for_ball": False,
                "reasoning": "parse_error",
            }

        if step["call_for_ball"] and not self.called_for_ball:
            self.called_for_ball = True
            self.call_heading = step["heading"]
            self.locked_heading = step["heading"]
            self.call_t = t

        self.wr_note = step.get("wr_note", "") or self.wr_note
        self.last_action = step
        return step

    def apply_decision(
        self,
        decision: dict,
        state: PlayerState,
        attrs: PlayerAttrs,
        dt: float = 0.1,
        ball_in_air: bool = False,
    ) -> PlayerState:
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
