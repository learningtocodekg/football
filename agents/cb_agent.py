"""CB agent (freedom branch). Keeps full per-step autonomy. Intent simplified to play_man (default)
or go_for_pick (INT gamble)."""
from pathlib import Path

from .llm_client import call_llm
from .schema import parse_cb_pre_snap, parse_cb_move, parse_cb_intent
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff
from engine.coverage import resolve_coverage

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
        self.last_action = {"mode": "shadow", "tilt": 0.0, "reasoning": "init"}
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
                       wr: PlayerState, dt: float = 0.1,
                       drive_target: tuple[float, float] | None = None) -> PlayerState:
        """The CB picks a pursuit INTENT (mode + bounded tilt); the engine renders it into the
        physically-correct heading/facing/movement-mode from live geometry (engine/coverage.py). No
        rail — the CB freely chooses the intent each step; the engine just does the trig it's exact at."""
        heading, facing, move_mode = resolve_coverage(
            decision.get("mode", "shadow"), decision.get("tilt", 0.0), state, wr, drive_target)
        turn = max(-90.0, min(90.0, angle_diff(heading, state.heading)))
        return apply_action(state, attrs, turn, "accelerate", dt, new_facing=facing, new_mode=move_mode)
