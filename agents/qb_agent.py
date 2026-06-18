"""QB agent (freedom branch). One decision per step once engaged: hold, or throw bullet/lob. The
engine computes the lead and places the ball — the QB only times it and picks the arc."""
from pathlib import Path

from .llm_client import call_llm
from .schema import parse_qb

_SYSTEM = (Path(__file__).parent / "prompts" / "qb_system.txt").read_text()
_DECIDE = (Path(__file__).parent / "prompts" / "qb_decide.txt").read_text()


class QBAgent:
    def __init__(self, model="gpt-5-nano", reasoning_effort="low", provider="openai", throw_power=85.0):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.throw_power = throw_power
        self.call_count = 0
        self.parse_errors = 0
        self.last_action = {"action": "hold", "reasoning": "init"}

    def decide(self, observation: str) -> dict:
        self.call_count += 1
        raw = call_llm(_SYSTEM, observation + "\n\n" + _DECIDE,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_qb(raw)
        if result is None:
            self.parse_errors += 1
            print(f"  [QB parse error] raw={raw[:120]!r}")
            return {"action": "hold", "reasoning": "parse_error"}
        self.last_action = result
        return result
