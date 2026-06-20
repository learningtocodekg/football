"""WR observation builders (free phase + ball-in-air phase). Lean and factual — no rail, no
pre-chewed verdicts. Give the WR the field; let it decide."""
import math

from engine.physics import PlayerState, PlayerAttrs
from engine.ball import BallState
from agents.scripted import ROUTES, ROUTE_DESCRIPTIONS, SETTLE_ROUTES
from agents.observation_common import (
    FIELD_WIDTH, OOB_WARN_DIST, dist, heading_label, height_label,
    accel_status, body_gap, move_log_table,
)


def _break_depth(route: str) -> float | None:
    """Designed downfield depth (yd) at which the route's FIRST break happens, or None for a
    no-break route (go). Derived from the phase table the route is defined by."""
    phases = ROUTES.get(route)
    if not phases or len(phases) < 2:
        return None
    return phases[0][0] * 5.0  # phase-0 end time * ~5 yd/s burst ≈ stem depth


def _route_shape(route: str) -> str:
    """One-line designed shape of the route from its phase table (info, not a rail)."""
    phases = ROUTES.get(route)
    if not phases:
        return "run the route as called."
    parts = []
    prev_t = 0.0
    for i, (thr, hdg) in enumerate(phases):
        if thr >= 999:
            seg = f"then run {hdg:.0f}° ({heading_label(hdg)})" if i > 0 else f"run {hdg:.0f}° ({heading_label(hdg)})"
        else:
            depth = thr * 5.0
            seg = f"~{depth:.0f}yd at {hdg:.0f}° ({heading_label(hdg)})"
        parts.append(seg)
        prev_t = thr
    tail = "  (STOP route — plant and settle on the final break)" if route in SETTLE_ROUTES else ""
    return " → ".join(parts) + tail


def _break_time(route: str) -> float | None:
    """Designed wall-clock time (s after snap) of the route's first break, or None (go)."""
    phases = ROUTES.get(route)
    if not phases or phases[0][0] >= 999:
        return None
    return phases[0][0]


def _you_cb_lines(wr: PlayerState, wr_attrs: PlayerAttrs, cb: PlayerState | None) -> list[str]:
    """Current self + CB geometry block, shared by the per-step observations."""
    lines = [
        f"YOU: pos=({wr.x:.1f},{wr.y:.1f}) speed={wr.speed:.1f}yd/s heading={wr.heading:.0f}° "
        f"({heading_label(wr.heading)}) facing={wr.facing:.0f}°",
        f"  burst: {accel_status(wr.cut_recovery)}   top speed {wr_attrs.max_speed:.1f}yd/s",
    ]
    if cb is not None:
        sep = dist(wr, cb)
        dx, dy = cb.x - wr.x, cb.y - wr.y
        side = "INSIDE (toward middle)" if dx > 0.3 else ("OUTSIDE (sideline side)" if dx < -0.3 else "inline")
        rel = "UPFIELD of you (cushion)" if dy > 0.5 else ("BEHIND you (beaten)" if dy < -0.5 else "even with you")
        lines += [
            f"CB: pos=({cb.x:.1f},{cb.y:.1f}) speed={cb.speed:.1f}yd/s heading={cb.heading:.0f}° "
            f"facing={cb.facing:.0f}° mode={cb.mode}",
            f"  {sep:.1f}yd away — {side}, {rel}.  body gap {body_gap(sep):.1f}yd.  burst: {accel_status(cb.cut_recovery)}",
        ]
        if cb.cut_recovery >= 2:
            lines.append(f"  CB is hip-committed for {cb.cut_recovery} more steps — it cannot change direction freely.")
    else:
        lines.append("CB: none on the field.")
    return lines


def build_wr_pre_snap_observation(
    wr: PlayerState,
    wr_attrs: PlayerAttrs,
    cb: PlayerState | None,
    route: str,
    wr_start: tuple[float, float] | None = None,
) -> str:
    """Pre-snap: everything the WR needs to AUTHOR its plan — route design, its purpose, the CB's
    alignment, and the field frame. This is the one expensive, full-reasoning call of the play."""
    purpose = ROUTE_DESCRIPTIONS.get(route, {}).get("purpose", "")
    lines = [
        "=== WR PRE-SNAP — author your route plan ===",
        "",
        "FIELD: heading 0°=straight upfield, 90°=inside (toward middle), 180°=back to the QB, "
        "270°=toward your sideline. You line up on the LEFT.",
        "",
        f"ROUTE: {route.upper()} — {_route_shape(route)}",
    ]
    if purpose:
        lines.append(f"  PURPOSE: {purpose}")
    bt = _break_time(route)
    bd = _break_depth(route)
    if bt is not None:
        lines.append(f"DESIGNED BREAK: ~{bt:.1f}s after the snap (~{bd:.0f}yd downfield). "
                     "Anchor your first decision around there.")
    else:
        lines.append("NO break on this route — it is a vertical. Win the stem with a fake, then a pure speed race.")
    lines += [f"YOU: top speed {wr_attrs.max_speed:.1f}yd/s. A hard cut (>35° at speed) sheds speed and "
              "costs recovery steps — plan your fakes, don't spam them."]
    if cb is not None:
        dy = cb.y - wr.y
        dx = cb.x - wr.x
        side = "inside" if dx > 0.3 else ("outside" if dx < -0.3 else "head-up/press")
        lines.append(f"CB ALIGNMENT: ~{dy:.1f}yd off you, leveraged {side}.")
    else:
        lines.append("CB ALIGNMENT: none on the field.")
    return "\n".join(lines)


def build_wr_node_observation(
    t: float,
    wr: PlayerState,
    wr_attrs: PlayerAttrs,
    cb: PlayerState | None,
    qb: PlayerState,
    route: str,
    node: dict,
    node_id: str,
    history: list[dict] | None = None,
    wr_start: tuple[float, float] | None = None,
) -> str:
    """At a decision node: current geometry + the node's authored read + its (pruned) options."""
    depth = (wr.y - wr_start[1]) if wr_start else wr.y
    lines = [
        f"=== WR  t={t:.1f}s — DECISION POINT '{node_id}' ===",
        "",
        f"ROUTE: {route.upper()}.  You are {depth:.1f}yd downfield of the snap.",
        "",
        *_you_cb_lines(wr, wr_attrs, cb),
    ]
    near = min(wr.x, FIELD_WIDTH - wr.x)
    if near < OOB_WARN_DIST:
        lines.append(f"!! {near:.1f}yd from the sideline — stay in bounds.")
    if history:
        lines += ["", *move_log_table(history)]
    read = node.get("read", "")
    lines += ["", "YOUR PRE-SNAP READ FOR THIS MOMENT:", f"  {read or '(none authored)'}", "",
              "YOUR OPTIONS (pick exactly one by index):"]
    for i, b in enumerate(node["branches"]):
        if "call" in b:
            er = b["call"]
            tail = f"settle {er['settle_ticks']} ticks" if er["mode"] == "settle" else "run in stride"
            act = f"CALL FOR THE BALL — break {er['heading']:.0f}° ({heading_label(er['heading'])}), {tail}"
        else:
            act = f"continue the plan → node '{b['goto']}'"
        lines.append(f"  [{i}] {b['cond']}  →  {act}")
    return "\n".join(lines)


def build_wr_free_observation(
    t: float,
    wr: PlayerState,
    wr_attrs: PlayerAttrs,
    cb: PlayerState | None,
    qb: PlayerState,
    route: str,
    history: list[dict] | None = None,
    wr_start: tuple[float, float] | None = None,
) -> str:
    depth = (wr.y - wr_start[1]) if wr_start else wr.y
    purpose = ROUTE_DESCRIPTIONS.get(route, {}).get("purpose", "")

    lines = [
        f"=== WR  t={t:.1f}s ===",
        "",
        f"ROUTE: {route.upper()} — {_route_shape(route)}",
    ]
    if purpose:
        lines.append(f"  PURPOSE: {purpose}")
    if wr_start:
        lines.append(f"SNAP: ({wr_start[0]:.1f}, {wr_start[1]:.1f}) — you are {depth:.1f}yd downfield of it.")
    bd = _break_depth(route)
    if bd is not None:
        gap = bd - depth
        if gap > 0.5:
            lines.append(f"BREAK DEPTH: your break is ~{bd:.0f}yd downfield — {gap:.1f}yd to go. Keep stemming.")
        else:
            lines.append(f"BREAK DEPTH: ~{bd:.0f}yd — you are THERE. Make your one decisive break now and call for the ball.")
    elif cb is not None:
        if wr.y >= cb.y - 0.5:
            lines.append("NO break on this route — and you are EVEN WITH / PAST the CB, running free. "
                         "You're done setting him up: CALL NOW so the throw leads you deep.")
        else:
            lines.append(f"NO break on this route — beat him deep with speed. He is still {cb.y - wr.y:.1f}yd "
                         "upfield of you (his cushion); keep accelerating and CALL the moment you pull even with him.")
    else:
        lines.append("This route has NO break — beat him deep with pure speed; call once you are running free.")
    lines += [
        "",
        f"YOU: pos=({wr.x:.1f},{wr.y:.1f}) speed={wr.speed:.1f}yd/s heading={wr.heading:.0f}° "
        f"({heading_label(wr.heading)}) facing={wr.facing:.0f}°",
        f"  burst: {accel_status(wr.cut_recovery)}   top speed {wr_attrs.max_speed:.1f}yd/s",
    ]
    if cb is not None:
        sep = dist(wr, cb)
        dx, dy = cb.x - wr.x, cb.y - wr.y
        side = "INSIDE (toward middle)" if dx > 0.3 else ("OUTSIDE (sideline side)" if dx < -0.3 else "inline")
        rel = "UPFIELD of you" if dy > 0.5 else ("BEHIND you" if dy < -0.5 else "even with you")
        lines += [
            f"CB: pos=({cb.x:.1f},{cb.y:.1f}) speed={cb.speed:.1f}yd/s heading={cb.heading:.0f}° "
            f"facing={cb.facing:.0f}° mode={cb.mode}",
            f"  {sep:.1f}yd away — {side}, {rel}.  body gap {body_gap(sep):.1f}yd.  burst: {accel_status(cb.cut_recovery)}",
        ]
        if cb.cut_recovery >= 2:
            lines.append(f"  CB is hip-committed for {cb.cut_recovery} more steps — it cannot change direction freely.")
    else:
        lines.append("CB: none on the field.")

    near = min(wr.x, FIELD_WIDTH - wr.x)
    if near < OOB_WARN_DIST:
        lines.append(f"!! {near:.1f}yd from the sideline — stay in bounds.")

    if history:
        lines += ["", *move_log_table(history)]

    return "\n".join(lines)


def build_wr_air_observation(
    t: float,
    wr: PlayerState,
    wr_attrs: PlayerAttrs,
    cb: PlayerState | None,
    qb: PlayerState,
    ball: BallState,
    ball_total_eta: float | None = None,
) -> str:
    dist_to_land = math.hypot(wr.x - ball.landing_x, wr.y - ball.landing_y)
    bearing_to_qb = math.degrees(math.atan2(qb.x - wr.x, qb.y - wr.y)) % 360.0
    lines = [
        f"=== WR (ball in air)  t={t:.1f}s ===",
        "",
        f"You are ALIVE again — adjust to the throw. ETA {ball.eta:.2f}s.",
        f"YOU: pos=({wr.x:.1f},{wr.y:.1f}) speed={wr.speed:.1f}yd/s heading={wr.heading:.0f}° facing={wr.facing:.0f}°",
        f"BALL landing: ({ball.landing_x:.1f},{ball.landing_y:.1f}) at z={ball.landing_z:.1f} "
        f"({height_label(ball.landing_z)})  arc={ball.arc}",
        f"  your distance to the landing spot: {dist_to_land:.1f}yd",
        f"FACING: set facing={bearing_to_qb:.0f}° (bearing to the QB — look the ball in). Do not estimate.",
    ]
    if cb is not None:
        lines.append(f"CB: ({cb.x:.1f},{cb.y:.1f})  {dist(wr, cb):.1f}yd from you, facing {cb.facing:.0f}°.")
    lines.append("Get to the spot and high-point it; the engine clamps you so you can't overrun it.")
    return "\n".join(lines)
