import json
import re


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
    if act == "thinking":
        ta = obj.get("target_area")
        if not (isinstance(ta, list) and len(ta) == 2):
            return None
        return {
            "action": "thinking",
            "target_area": [float(ta[0]), float(ta[1])],
            "reasoning": reasoning,
        }
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


def parse_qb_pass2(raw: str, options: list[dict]) -> dict | None:
    """Parse pass-2 response: hold or throw (by option label)."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    act = obj.get("action")
    reasoning = str(obj.get("reasoning", ""))
    if act == "hold":
        return {"action": "hold", "reasoning": reasoning}
    if act == "throw":
        label = obj.get("option", "").strip().lower()
        matched = next((o for o in options if o["label"] == label), None)
        if matched is None:
            return None
        return {
            "action": "throw",
            "target_coord": matched["target"],
            "ball_speed_mph": matched["mph"],
            "reasoning": reasoning,
        }
    return None
