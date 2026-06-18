"""QB observation (freedom branch). The QB only times the throw and picks bullet vs lob — the engine
leads the WR. The observation shows, per arc, the engine's meeting point, the arrival time, the throw
distance, and whether it's in arm range. No coordinates for the QB to place."""
import math

from engine.physics import PlayerState, PlayerAttrs
from engine.ball import BallState, max_ball_speed, max_range
from agents.observation_common import dist, heading_label, down_str


def build_qb_observation(
    t: float,
    sack_clock: float,
    qb: PlayerState,
    qb_attrs: PlayerAttrs,
    wr: PlayerState,
    wr_attrs: PlayerAttrs,
    cb: PlayerState | None,
    cb_attrs: PlayerAttrs | None,
    ball: BallState,
    lead_options: dict,                 # {"bullet": {...}, "lob": {...}} from solve_lead
    wr_call_t: float | None = None,
    wr_call_heading: float | None = None,
    down: int = 1,
    distance: int = 10,
    history: list[dict] | None = None,
) -> str:
    bullet_max = max_range("bullet", max_ball_speed(qb_attrs.throw_power))
    lines = [
        f"=== QB  t={t:.1f}s  |  sack clock {sack_clock:.1f}s  |  {down_str(down, distance)} ===",
        "",
    ]
    if wr_call_t is not None and wr_call_heading is not None:
        lines.append(
            f"Your WR called for the ball at t={wr_call_t:.1f}s (~0.2s ago) and is now committed to "
            f"heading {wr_call_heading:.0f}° ({heading_label(wr_call_heading)}). His path is locked; "
            f"only his speed changes. Decide whether and how to throw."
        )
        lines.append("")
    lines += [
        f"You (QB): ({qb.x:.1f},{qb.y:.1f})  arm: bullet tops out ~{bullet_max:.0f}yd, a lob reaches farther.",
        f"WR: ({wr.x:.1f},{wr.y:.1f}) heading {wr.heading:.0f}° ({heading_label(wr.heading)}) speed {wr.speed:.1f}yd/s",
    ]
    if cb is not None:
        lines.append(f"CB: ({cb.x:.1f},{cb.y:.1f})  separation now {dist(wr, cb):.1f}yd")
    lines += [
        "",
        "YOUR TWO THROWS (the engine leads the WR for you — you just pick one or hold):",
        f"  {'arc':<8} {'meets WR at':<16} {'arrives in':<11} {'throw dist':<11} {'in range?':<9}",
    ]
    for arc in ("bullet", "lob"):
        o = lead_options.get(arc)
        if not o:
            continue
        tgt = f"({o['target'][0]:.1f},{o['target'][1]:.1f})"
        rng = "yes" if o["feasible"] else "NO (too far)"
        lines.append(f"  {arc:<8} {tgt:<16} +{o['tau']:<9.1f}s {o['dist']:<10.1f}y {rng:<9}")
    lines += [
        "",
        "BULLET: flat and fast — least time for the CB to react, but limited range and a low, "
        "drive-it-in trajectory. Best when the WR is open NOW and within range.",
        "LOB: high and soft — reaches deep and drops over the top, but hangs long enough for the CB to "
        "close. Best for a deep ball where the WR runs onto it.",
        "",
        "Throw only if the WR is (or will be) open at the meeting point. If the matchup is tight, hold "
        "and re-read — but the sack clock is running.",
        "",
        'Output JSON: {"action":"throw","arc":"bullet"|"lob","reasoning":"..."}  or  '
        '{"action":"hold","reasoning":"..."}',
    ]
    return "\n".join(lines)
