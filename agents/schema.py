"""LLM output parsers for the freedom-branch agents. Lenient: extract the first JSON object,
strip <think> blocks and code fences, validate fields, fall back sensibly."""
import json
import re


def _extract_json(raw: str) -> dict | None:
    text = (raw or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(l for l in lines[1:] if l.strip() != "```")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group())
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _throttle(v) -> str:
    s = str(v).strip().lower()
    return s if s in ("accelerate", "coast", "brake") else "accelerate"


def parse_end_route(obj: dict) -> dict | None:
    """Validate an end_route block: {heading, mode, settle_ticks?}."""
    if not isinstance(obj, dict):
        return None
    try:
        heading = float(obj["heading"]) % 360.0
    except (KeyError, TypeError, ValueError):
        return None
    mode = str(obj.get("mode", "run")).strip().lower()
    if mode not in ("run", "settle"):
        mode = "run"
    st = obj.get("settle_ticks")
    settle_ticks = int(st) if isinstance(st, (int, float)) else (8 if mode == "settle" else None)
    return {"heading": heading, "mode": mode, "settle_ticks": settle_ticks}


def parse_wr_free(raw: str) -> dict | None:
    """Free-phase WR: heading, facing, throttle, call_for_ball, end_route (if calling)."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    try:
        heading = float(obj["heading"]) % 360.0
    except (KeyError, TypeError, ValueError):
        return None
    facing = obj.get("facing", heading)
    try:
        facing = float(facing) % 360.0
    except (TypeError, ValueError):
        facing = heading
    call = bool(obj.get("call_for_ball", False))
    end_route = None
    if call:
        end_route = parse_end_route(obj.get("end_route", {}))
        if end_route is None:
            # Calling without a usable end_route → assume "run where I'm going".
            end_route = {"heading": heading, "mode": "run", "settle_ticks": None}
    return {
        "heading": heading,
        "facing": facing,
        "throttle": _throttle(obj.get("throttle", "accelerate")),
        "call_for_ball": call,
        "end_route": end_route,
        "reasoning": str(obj.get("reasoning", "")),
    }


def parse_wr_air(raw: str) -> dict | None:
    """Ball-in-air WR: heading, facing, throttle."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    try:
        heading = float(obj["heading"]) % 360.0
    except (KeyError, TypeError, ValueError):
        return None
    facing = obj.get("facing", heading)
    try:
        facing = float(facing) % 360.0
    except (TypeError, ValueError):
        facing = heading
    return {
        "heading": heading,
        "facing": facing,
        "throttle": _throttle(obj.get("throttle", "accelerate")),
        "reasoning": str(obj.get("reasoning", "")),
    }


def parse_qb(raw: str) -> dict | None:
    """QB: hold, or throw with arc ∈ {bullet, lob}."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    act = str(obj.get("action", "")).strip().lower()
    reasoning = str(obj.get("reasoning", ""))
    if act == "hold":
        return {"action": "hold", "reasoning": reasoning}
    if act == "throw":
        arc = str(obj.get("arc", "bullet")).strip().lower()
        if arc not in ("bullet", "lob"):
            arc = "bullet"
        return {"action": "throw", "arc": arc, "reasoning": reasoning}
    return None


def parse_cb_move(raw: str) -> dict | None:
    """CB movement: a pursuit INTENT — mode (shadow/drive/bail) + a bounded tilt (deg). The engine
    renders this into heading/facing/movement-mode from live geometry (engine/coverage.py)."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    mode = str(obj.get("mode", "shadow")).strip().lower()
    if mode not in ("shadow", "drive", "bail"):
        mode = "shadow"
    try:
        tilt = float(obj.get("tilt", 0.0))
    except (TypeError, ValueError):
        tilt = 0.0
    tilt = max(-25.0, min(25.0, tilt))
    return {"mode": mode, "tilt": tilt, "reasoning": str(obj.get("reasoning", ""))}


def parse_cb_intent(raw: str) -> dict | None:
    """CB ball-in-air intent: play_man or go_for_pick."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    intent = str(obj.get("intent", "")).strip().lower()
    if intent not in ("play_man", "go_for_pick"):
        return None
    return {"intent": intent, "reasoning": str(obj.get("reasoning", ""))}


def parse_cb_pre_snap(raw: str) -> dict | None:
    """CB pre-snap alignment: offset_yards and side."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    try:
        offset = float(obj.get("offset_yards", 5.0))
    except (TypeError, ValueError):
        offset = 5.0
    side = str(obj.get("side", "outside")).strip().lower()
    if side not in ("inside", "outside", "press"):
        side = "outside"
    return {"offset_yards": max(0.0, offset), "side": side,
            "reasoning": str(obj.get("reasoning", ""))}
