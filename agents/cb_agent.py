"""CB agent (freedom branch). Keeps full per-step autonomy. Intent simplified to play_man (default)
or go_for_pick (INT gamble)."""
from pathlib import Path

from .llm_client import call_llm
from .schema import parse_cb_pre_snap, parse_cb_move, parse_cb_intent
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff

_SYSTEM = (Path(__file__).parent / "prompts" / "cb_system.txt").read_text()
_PRE_SNAP = (Path(__file__).parent / "prompts" / "cb_pre_snap.txt").read_text()
_MOVE = (Path(__file__).parent / "prompts" / "cb_move.txt").read_text()
_INTENT = (Path(__file__).parent / "prompts" / "cb_intent.txt").read_text()


class CBAgent:
    def __init__(self, model="gpt-5-nano", reasoning_effort="low", provider="openai"):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.call_count = 0
        self.parse_errors = 0
        self.last_action = {"heading": 0.0, "facing": 0.0, "mode": "normal", "reasoning": "init"}
        self._intent = "play_man"
        self._intent_locked = False

    def pre_snap(self, observation: str) -> dict:
        self.call_count += 1
        raw = call_llm(_SYSTEM, observation + "\n\n" + _PRE_SNAP,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_cb_pre_snap(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [CB pre-snap parse error] raw={raw[:120]!r}")
            return {"offset_yards": 5.0, "side": "outside", "reasoning": "parse_error"}
        return result

    def decide_move(self, observation: str) -> dict:
        self.call_count += 1
        raw = call_llm(_SYSTEM, observation + "\n\n" + _MOVE,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_cb_move(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [CB move parse error] raw={raw[:120]!r}")
            return {**self.last_action, "reasoning": "parse_error"}
        self.last_action = result
        return result

    def decide_intent(self, observation: str) -> str:
        if self._intent_locked:
            return self._intent
        self.call_count += 1
        raw = call_llm(_SYSTEM, observation + "\n\n" + _INTENT,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_cb_intent(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [CB intent parse error] raw={raw[:120]!r}")
            self._intent = "play_man"
        else:
            self._intent = result["intent"]
            print(f"  CB intent -> {self._intent!r}  | {result['reasoning']}")
        self._intent_locked = True
        return self._intent

    def apply_decision(self, decision: dict, state: PlayerState, attrs: PlayerAttrs,
                       dt: float = 0.1) -> PlayerState:
        """No forced movement — the CB chooses its own heading and facing every step. `backpedal` is
        just a mode: the engine caps its speed at 75% of max, and the CB keeps its eyes on the WR by
        setting facing toward him while it retreats. `brake` sheds speed; `normal` runs full speed."""
        mode = decision.get("mode", "normal")
        target_heading = float(decision.get("heading", state.heading))
        target_facing = float(decision.get("facing", target_heading))
        turn = max(-90.0, min(90.0, angle_diff(target_heading, state.heading)))
        throttle = "brake" if mode == "brake" else "accelerate"
        return apply_action(state, attrs, turn, throttle, dt, new_facing=target_facing, new_mode=mode)
