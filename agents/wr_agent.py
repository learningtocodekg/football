"""WR agent (freedom branch). Free phase: per-step heading/throttle/juke + a call_for_ball that
locks an end_route. Ball-in-air: comes alive to adjust to the throw. No rail — the route shape is
context in the prompt, not an enforced cage."""
from pathlib import Path

from .llm_client import call_llm
from .schema import parse_wr_free, parse_wr_air, parse_wr_plan, parse_wr_node_choice
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff

_SYSTEM = (Path(__file__).parent / "prompts" / "wr_system.txt").read_text()
_FREE = (Path(__file__).parent / "prompts" / "wr_free.txt").read_text()
_PLAN = (Path(__file__).parent / "prompts" / "wr_plan.txt").read_text()
_NODE = (Path(__file__).parent / "prompts" / "wr_node.txt").read_text()
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
        self.plan: dict | None = None

    def author_plan(self, observation: str) -> dict:
        """One-time pre-snap call with full reasoning budget: author the conditional decision tree
        that becomes the WR's externalized state for the whole play."""
        self.call_count += 1
        raw = call_llm(_SYSTEM, observation + "\n\n" + _PLAN,
                       self.model, self.reasoning_effort, self.provider)
        plan = parse_wr_plan(raw)
        if plan is None:
            self.parse_errors += 1
            print(f"  [WR plan parse error] raw={raw[:160]!r}")
            plan = self._fallback_plan()
        self.plan = plan
        return plan

    def decide_node(self, observation: str, node: dict) -> dict:
        """At a decision node: evaluate the node's authored read against the field NOW and pick one
        of that node's branches (pruned — only this node's options are shown)."""
        self.call_count += 1
        raw = call_llm(_SYSTEM, observation + "\n\n" + _NODE,
                       self.model, self.reasoning_effort, self.provider)
        result = parse_wr_node_choice(raw, len(node["branches"]))
        if result is None:
            self.parse_errors += 1
            print(f"  [WR node parse error] raw={raw[:120]!r}")
            return {"choice": 0, "reasoning": "parse_error"}
        return result

    def _fallback_plan(self) -> dict:
        """Parse-failure backstop: stem to the route's designed break, then break + call. Keeps the
        play runnable; not meant to be good."""
        from agents.scripted import ROUTES, SETTLE_ROUTES
        phases = ROUTES.get(self.route, [(1.5, 0.0), (999, 0.0)])
        final_hdg = phases[-1][1] if phases else 0.0
        break_t = phases[0][0] if phases and phases[0][0] < 999 else 1.5
        mode = "settle" if self.route in SETTLE_ROUTES else "run"
        return {"idea": "fallback: stem then break", "start": "n0", "nodes": {"n0": {
            "action": {"heading": 0.0, "effort": "accelerate"}, "hold": break_t, "read": "",
            "branches": [{"cond": "(default) break and call", "call": {
                "heading": final_hdg, "mode": mode,
                "settle_ticks": (8 if mode == "settle" else None)}}]}}}

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
