import json
import re
from typing import Literal

from pydantic import BaseModel


class WRStep(BaseModel):
    """One 0.1s WR action, tagged with its absolute time t."""
    t: float
    heading: float
    throttle: Literal["accelerate", "coast", "brake"]
    facing: float
    call_for_ball: bool
    reasoning: str


class WRPlan(BaseModel):
    """A timestamped WR plan (1-4 steps) for the LIVE-free phase."""
    plan: list[WRStep]
    wr_note: str


def wr_plan_steps(plan: WRPlan) -> list[dict] | None:
    """Convert a validated WRPlan into the per-step dicts the runner consumes.

    Clamps to 4 steps (keep the WR reactive) and tags each step's reasoning with
    its absolute time t.
    """
    steps: list[dict] = []
    for s in plan.plan[:4]:
        steps.append({
            "heading": s.heading % 360.0,
            "facing": s.facing % 360.0,
            "throttle": s.throttle,
            "call_for_ball": s.call_for_ball,
            "reasoning": f"t={s.t:.1f} {s.reasoning}".strip(),
            "wr_note": plan.wr_note,
        })
    return steps or None


def _extract_json(raw: str) -> dict | None:
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(l for l in lines[1:] if l.strip() != "```")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group())
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def parse_qb_pass1(raw: str) -> dict | None:
    """Parse pass-1 response: hold or thinking."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    act = obj.get("action")
    reasoning = str(obj.get("reasoning", ""))
    if act == "hold":
        return {"action": "hold", "reasoning": reasoning}
    if act in ("thinking", "throw", "window", "go"):
        ow = obj.get("open_window")
        if not (isinstance(ow, list) and len(ow) == 2):
            return None
        try:
            window = (float(ow[0]), float(ow[1]))
        except (TypeError, ValueError):
            return None
        return {"action": "thinking", "open_window": window, "reasoning": reasoning}
    return None


def parse_cb_pre_snap(raw: str) -> dict | None:
    """Parse CB pre-snap alignment: offset_yards and side."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    try:
        offset = float(obj.get("offset_yards", 5.0))
        side = str(obj.get("side", "outside")).strip().lower()
        if side not in ("inside", "outside", "press"):
            side = "outside"
        return {"offset_yards": max(0.0, offset), "side": side,
                "reasoning": str(obj.get("reasoning", ""))}
    except (TypeError, ValueError):
        return None


def parse_cb_pass1(raw: str) -> dict | None:
    """Parse CB movement decision: heading, facing, mode."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    try:
        heading = float(obj["heading"]) % 360.0
        facing = float(obj.get("facing", heading)) % 360.0
        mode = str(obj.get("mode", "normal")).strip().lower()
        if mode not in ("normal", "backpedal", "brake"):
            mode = "normal"
        return {"heading": heading, "facing": facing, "mode": mode,
                "reasoning": str(obj.get("reasoning", ""))}
    except (KeyError, TypeError, ValueError):
        return None


def parse_cb_pass2(raw: str) -> dict | None:
    """Parse CB intent decision: play_man, swat, or go_for_pick."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    intent = str(obj.get("intent", "")).strip().lower()
    if intent not in ("play_man", "swat", "go_for_pick"):
        return None
    return {"intent": intent, "reasoning": str(obj.get("reasoning", ""))}


def parse_wr_pre_snap(raw: str) -> dict | None:
    """Parse WR pre-snap plan: just a plan string."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    return {
        "plan": str(obj.get("plan", "")),
        "reasoning": str(obj.get("reasoning", "")),
    }


def parse_wr_live(raw: str) -> dict | None:
    """Parse WR live movement: heading, facing, throttle, call_for_ball."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    try:
        heading = float(obj["heading"]) % 360.0
        facing = float(obj.get("facing", heading)) % 360.0
        throttle = str(obj.get("throttle", "accelerate")).strip().lower()
        if throttle not in ("accelerate", "coast", "brake"):
            throttle = "accelerate"
        call_for_ball = bool(obj.get("call_for_ball", False))
        return {
            "heading": heading,
            "facing": facing,
            "throttle": throttle,
            "call_for_ball": call_for_ball,
            "reasoning": str(obj.get("reasoning", "")),
            "wr_note": str(obj.get("wr_note", "")),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _normalize_wr_step(obj: dict) -> dict | None:
    """Normalize one WR step like parse_wr_live (without reasoning/wr_note)."""
    try:
        heading = float(obj["heading"]) % 360.0
        facing = float(obj.get("facing", heading)) % 360.0
        throttle = str(obj.get("throttle", "accelerate")).strip().lower()
        if throttle not in ("accelerate", "coast", "brake"):
            throttle = "accelerate"
        call_for_ball = bool(obj.get("call_for_ball", False))
        return {
            "heading": heading,
            "facing": facing,
            "throttle": throttle,
            "call_for_ball": call_for_ball,
        }
    except (KeyError, TypeError, ValueError):
        return None


def parse_wr_plan(raw: str) -> list[dict] | None:
    """Parse a WR plan: an ordered list of 1-10 per-step actions.

    Expects {"plan": [{heading, throttle, facing?, call_for_ball?}, ...],
             "wr_note": "...", "reasoning": "..."}.
    A top-level heading (no plan key) is treated as a 1-step plan.
    """
    obj = _extract_json(raw)
    if obj is None:
        return None

    raw_plan = obj.get("plan")
    if not isinstance(raw_plan, list):
        # No plan key — treat the object itself as a single step if it has heading.
        raw_plan = [obj] if "heading" in obj else []

    raw_plan = raw_plan[:4]  # clamp to 1-4 (truncate) — keep the WR reactive for deception
    reasoning = str(obj.get("reasoning", ""))
    wr_note = str(obj.get("wr_note", ""))

    steps: list[dict] = []
    n = len(raw_plan)
    for i, raw_step in enumerate(raw_plan):
        if not isinstance(raw_step, dict):
            continue
        step = _normalize_wr_step(raw_step)
        if step is None:
            continue
        # Per-step reasoning if the model gave one; else fall back to the plan-level string.
        step_reasoning = str(raw_step.get("reasoning", "")).strip() or reasoning
        # Tag with the step's own absolute time t if present (forces the model to face the clock).
        step_t = raw_step.get("t")
        if isinstance(step_t, (int, float)):
            tag = f"t={float(step_t):.1f}"
        else:
            tag = f"[plan {i + 1}/{n}]"
        step["reasoning"] = f"{tag} {step_reasoning}".strip()
        step["wr_note"] = wr_note
        steps.append(step)

    return steps or None


def parse_qb_pass2(raw: str, options: list[dict]) -> dict | None:
    """Parse pass-2 response: hold or throw (arc name + target_coord + optional target_z)."""
    from engine.ball import DEFAULT_TARGET_Z, MIN_TARGET_Z, MAX_TARGET_Z

    obj = _extract_json(raw)
    if obj is None:
        return None
    act = obj.get("action")
    reasoning = str(obj.get("reasoning", ""))
    if act == "hold":
        return {"action": "hold", "reasoning": reasoning}
    if act == "throw":
        if not options:
            return None
        try:
            target_z = float(obj.get("target_z", DEFAULT_TARGET_Z))
        except (TypeError, ValueError):
            target_z = DEFAULT_TARGET_Z
        target_z = max(MIN_TARGET_Z, min(MAX_TARGET_Z, target_z))

        # Arc: accept "arc" (new) or "option" (legacy label). Fall back to the flattest feasible.
        arc = str(obj.get("arc", obj.get("option", ""))).strip().lower()
        valid_arcs = {o["arc"] for o in options}
        if arc not in valid_arcs:
            arc = options[0]["arc"]

        # Landing spot: prefer the QB's explicit target_coord; else the arc's reference target.
        tc = obj.get("target_coord")
        if isinstance(tc, list) and len(tc) == 2:
            try:
                target_coord = [float(tc[0]), float(tc[1])]
            except (TypeError, ValueError):
                target_coord = next(o["target"] for o in options if o["arc"] == arc)
        else:
            target_coord = next(o["target"] for o in options if o["arc"] == arc)

        return {
            "action": "throw",
            "target_coord": target_coord,
            "arc": arc,
            "target_z": target_z,
            "reasoning": reasoning,
        }
    return None
