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


def _effort(v) -> str:
    s = str(v).strip().lower()
    return s if s in ("accelerate", "coast", "brake") else "accelerate"


def parse_wr_plan(raw: str) -> dict | None:
    """Self-authored conditional decision tree (the WR's externalized state).

    plan = {idea, start, nodes:{id: node}}
    node = {action:{heading,effort}, hold (s to run the action before deciding), read, branches}
    branch = {cond, goto}  (move to another node)  OR  {cond, call:<end_route>}  (call for the ball)
    """
    obj = _extract_json(raw)
    if obj is None:
        return None
    nodes_in = obj.get("nodes")
    if not isinstance(nodes_in, dict) or not nodes_in:
        return None

    nodes: dict[str, dict] = {}
    for nid, n in nodes_in.items():
        if not isinstance(n, dict):
            continue
        action = n.get("action", {}) if isinstance(n.get("action"), dict) else {}
        try:
            a_hdg = float(action.get("heading", 0.0)) % 360.0
        except (TypeError, ValueError):
            a_hdg = 0.0
        try:
            hold = max(0.0, min(5.0, float(n.get("hold", 0.5))))
        except (TypeError, ValueError):
            hold = 0.5
        branches: list[dict] = []
        for b in (n.get("branches") or []):
            if not isinstance(b, dict):
                continue
            cond = str(b.get("cond", ""))
            if isinstance(b.get("call"), dict):
                er = parse_end_route(b["call"])
                if er is not None:
                    branches.append({"cond": cond, "call": er})
            elif b.get("goto") is not None:
                branches.append({"cond": cond, "goto": str(b["goto"]).strip()})
        if not branches:
            # A node with no usable branch is a dead end → make it commit (run where it's pointing).
            branches = [{"cond": "(default) commit and run",
                         "call": {"heading": a_hdg, "mode": "run", "settle_ticks": None}}]
        nodes[str(nid).strip()] = {
            "action": {"heading": a_hdg, "effort": _effort(action.get("effort", "accelerate"))},
            "hold": hold, "read": str(n.get("read", "")), "branches": branches,
        }

    if not nodes:
        return None
    start = str(obj.get("start", "")).strip()
    if start not in nodes:
        start = next(iter(nodes))
    return {"idea": str(obj.get("idea", "")), "start": start, "nodes": nodes}


def parse_wr_node_choice(raw: str, n_options: int) -> dict | None:
    """At a decision node the WR evaluates its own read and picks one branch by index."""
    obj = _extract_json(raw)
    if obj is None:
        return None
    try:
        choice = int(obj.get("choice"))
    except (TypeError, ValueError):
        return None
    choice = max(0, min(n_options - 1, choice))
    return {"choice": choice, "reasoning": str(obj.get("reasoning", ""))}


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
