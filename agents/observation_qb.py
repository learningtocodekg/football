"""QB observation (freedom branch). The QB only times the throw and picks bullet vs lob — the engine
leads the WR. The observation shows, per arc, the engine's meeting point, the arrival time, the throw
distance, and whether it's in arm range. No coordinates for the QB to place."""
import math

from engine.physics import PlayerState, PlayerAttrs
from engine.ball import BallState, max_ball_speed, max_range, arc_clearance
from engine.resolution import CB_VERTICAL_REACH
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
        f"  {'arc':<8} {'meets WR at':<14} {'hang':<7} {'dist':<7} {'apex z':<7} {'clears the CB at':<22} {'in range?'}",
    ]
    for arc in ("bullet", "lob"):
        o = lead_options.get(arc)
        if not o:
            continue
        tgt = f"({o['target'][0]:.1f},{o['target'][1]:.1f})"
        rng = "yes" if o["feasible"] else "NO (too far)"
        peak = o.get("peak_z")
        apex = f"{peak:.1f}" if peak is not None else "--"
        if cb is not None:
            clr = arc_clearance(qb.x, qb.y, o["target"][0], o["target"][1], arc, cb.x, cb.y)
            if clr is None:
                over = "--"
            else:
                tag = "in his reach" if clr <= CB_VERTICAL_REACH else "OVER his head"
                over = f"z={clr:.1f}yd ({tag})"
        else:
            over = "--"
        lines.append(
            f"  {arc:<8} {tgt:<14} +{o['tau']:<5.1f}s {o['dist']:<6.1f}y {apex:<7} {over:<22} {rng}"
        )
    lines += [
        "",
        f"(The CB can touch a ball up to ~{CB_VERTICAL_REACH:.0f}yd high. 'clears the CB at' is how high "
        "each throw passes over him on its way to the WR.)",
        "",
        "BULLET = low and fast: arrives soonest, least time for the CB to react — but it stays in his "
        "vertical reach through the lane, so a defender in the way can break it up. Drive it in low when "
        "the WR is open NOW.",
        "LOB = high and soft: longer hang, drops over the top BEYOND the CB — but that hang lets him "
        "close. For a deep ball the WR runs onto; don't loft a short throw.",
        "Read the two against where the CB is: deliver it low-and-now, or high-over-the-top-and-later. "
        '"Open" = separation at the MEETING POINT when the ball arrives, not just right now.',
        "",
        "Hold if neither is clean and re-read — but the sack clock is running.",
    ]
    return "\n".join(lines)
