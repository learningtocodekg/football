"""WR agent (freedom branch). Free phase: per-step heading/throttle/juke + a call_for_ball that
locks an end_route. Ball-in-air: comes alive to adjust to the throw. No rail — the route shape is
context in the prompt, not an enforced cage."""
from pathlib import Path

from .llm_client import call_llm
from .schema import parse_wr_free, parse_wr_air
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff

_SYSTEM = (Path(__file__).parent / "prompts" / "wr_system.txt").read_text()
_FREE = (Path(__file__).parent / "prompts" / "wr_free.txt").read_text()
_AIR = (Path(__file__).parent / "prompts" / "wr_air.txt").read_text()

_THROTTLE_TO_ENGINE = {"accelerate": "accelerate", "coast": "hold", "brake": "brake"}


class WRAgent:
    def __init__(self, model="gpt-5-nano", reasoning_effort="low", provider="openai", route="slant"):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.route = route
        self.call_count = 0
        self.parse_errors = 0
        self.called_for_ball = False
        self.call_t: float | None = None
        self.call_heading: float | None = None
        self.end_route: dict | None = None

    def decide_free(self, observation: str, t: float = 0.0) -> dict:
        self.call_count += 1
        raw = call_llm(_SYSTEM, observation + "\n\n" + _FREE,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_wr_free(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [WR free parse error] raw={raw[:120]!r}")
            return {"heading": 0.0, "facing": 0.0, "throttle": "accelerate",
                    "call_for_ball": False, "end_route": None, "reasoning": "parse_error"}
        if result["call_for_ball"] and not self.called_for_ball:
            self.called_for_ball = True
            self.call_t = t
            self.call_heading = result["end_route"]["heading"]
            self.end_route = result["end_route"]
        return result

    def decide_air(self, observation: str) -> dict:
        self.call_count += 1
        raw = call_llm(_SYSTEM, observation + "\n\n" + _AIR,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_wr_air(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [WR air parse error] raw={raw[:120]!r}")
            return {"heading": 0.0, "facing": 0.0, "throttle": "accelerate", "reasoning": "parse_error"}
        return result

    def apply_decision(self, decision: dict, state: PlayerState, attrs: PlayerAttrs,
                       dt: float = 0.1) -> PlayerState:
        target_heading = float(decision.get("heading", state.heading))
        target_facing = float(decision.get("facing", target_heading))
        throttle = _THROTTLE_TO_ENGINE.get(decision.get("throttle", "accelerate"), "accelerate")
        turn = max(-90.0, min(90.0, angle_diff(target_heading, state.heading)))
        return apply_action(state, attrs, turn, throttle, dt, new_facing=target_facing)
