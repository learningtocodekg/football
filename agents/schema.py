import json


def parse_qb_action(raw: str) -> dict | None:
    """Parse QB action JSON from LLM response. Returns validated dict or None on failure."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        inner = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(inner)

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(obj, dict):
        return None

    act = obj.get("action")
    reasoning = str(obj.get("reasoning", ""))

    if act == "hold":
        return {"action": "hold", "reasoning": reasoning}

    if act == "throw":
        tc = obj.get("target_coord")
        bs = obj.get("ball_speed_mph")
        if not (isinstance(tc, list) and len(tc) == 2):
            return None
        if not isinstance(bs, (int, float)):
            return None
        return {
            "action": "throw",
            "target_coord": [float(tc[0]), float(tc[1])],
            "ball_speed_mph": float(bs),
            "reasoning": reasoning,
        }

    return None
