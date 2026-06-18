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
    desc = ROUTE_DESCRIPTIONS.get(route, {}).get("description", "")

    lines = [
        f"=== WR  t={t:.1f}s ===",
        "",
        f"ROUTE: {route.upper()} — {_route_shape(route)}",
    ]
    if desc:
        lines.append(f"  WHY: {desc}")
    if wr_start:
        lines.append(f"SNAP: ({wr_start[0]:.1f}, {wr_start[1]:.1f}) — you are {depth:.1f}yd downfield of it.")
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
