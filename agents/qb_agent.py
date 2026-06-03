from pathlib import Path
from .llm_client import call_llm
from .schema import parse_qb_action

_PROMPT_PATH = Path(__file__).parent / "prompts" / "qb_system.txt"


class QBAgent:
    def __init__(self, model: str = "gpt-4o-mini", reasoning_effort: str | None = "low"):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._system = _PROMPT_PATH.read_text()
        self.last_action: dict = {"action": "hold", "reasoning": "initializing"}
        self.call_count = 0
        self.parse_errors = 0

    def decide(self, observation: str) -> dict:
        self.call_count += 1
        raw = call_llm(self._system, observation, self.model, self.reasoning_effort)
        action = parse_qb_action(raw)
        if action is None:
            self.parse_errors += 1
            print(f"  [QB parse error #{self.parse_errors}] raw={raw[:120]!r}")
            return {"action": "hold", "reasoning": "parse_error"}
        self.last_action = action
        return action
