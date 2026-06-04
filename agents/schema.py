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
