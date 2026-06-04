import math
from pathlib import Path
from .llm_client import call_llm
from .schema import parse_cb_pre_snap, parse_cb_pass1, parse_cb_pass2
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff, BACKPEDAL_SPEED_FRACTION

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "cb_system.txt").read_text()
_PRE_SNAP_PROMPT = (Path(__file__).parent / "prompts" / "cb_pre_snap.txt").read_text()
_PASS1_PROMPT = (Path(__file__).parent / "prompts" / "cb_pass1.txt").read_text()
_PASS2_PROMPT = (Path(__file__).parent / "prompts" / "cb_pass2.txt").read_text()


class CBAgent:
    def __init__(
        self,
        model: str = "gpt-5-nano",
        reasoning_effort: str | None = "low",
        provider: str = "openai",
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.last_action: dict = {"action": "hold", "reasoning": "initializing"}
        self.call_count = 0
        self.parse_errors = 0
        # Intent locked in once ball is in air — persists until resolution
        self._ball_intent: str = "play_man"
        self._intent_locked: bool = False

    def pre_snap(self, observation: str) -> dict:
        """One-time call before the play. Returns alignment offset."""
        self.call_count += 1
        raw = call_llm(_SYSTEM_PROMPT, observation + "\n\n" + _PRE_SNAP_PROMPT,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_cb_pre_snap(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [CB pre-snap parse error] raw={raw[:120]!r}")
            return {"offset_yards": 5.0, "side": "outside", "reasoning": "parse_error"}
        return result

    def decide_movement(self, observation: str) -> dict:
        """Called each LIVE step. Returns heading, facing, mode."""
        self.call_count += 1
        raw = call_llm(_SYSTEM_PROMPT, observation + "\n\n" + _PASS1_PROMPT,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_cb_pass1(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [CB pass1 parse error] raw={raw[:120]!r}")
            return {"heading": self.last_action.get("heading", 0.0),
                    "facing": self.last_action.get("facing", 0.0),
                    "mode": "normal", "reasoning": "parse_error"}
        self.last_action = result
        return result

    def decide_intent(self, observation: str) -> str:
        """Called once when ball enters air. Returns cb_intent string."""
        if self._intent_locked:
            return self._ball_intent
        self.call_count += 1
        raw = call_llm(_SYSTEM_PROMPT, observation + "\n\n" + _PASS2_PROMPT,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_cb_pass2(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [CB pass2 parse error] raw={raw[:120]!r}")
            self._ball_intent = "play_man"
        else:
            self._ball_intent = result["intent"]
            r = result["reasoning"].encode("ascii", "replace").decode("ascii")
            print(f"  CB intent -> {self._ball_intent!r}  | {r}")
        self._intent_locked = True
        return self._ball_intent

    def apply_decision(
        self,
        decision: dict,
        state: PlayerState,
        attrs: PlayerAttrs,
        dt: float = 0.1,
    ) -> PlayerState:
        """Convert a CB movement decision into a new PlayerState via physics."""
        target_heading = float(decision.get("heading", state.heading))
        target_facing = float(decision.get("facing", target_heading))
        mode = decision.get("mode", "normal")

        turn = angle_diff(target_heading, state.heading)
        turn = max(-90.0, min(90.0, turn))

        throttle = "brake" if mode == "brake" else "accelerate"

        return apply_action(
            state, attrs, turn, throttle, dt,
            new_facing=target_facing,
            new_mode=mode,
        )
