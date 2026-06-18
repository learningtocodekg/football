"""Shared observation helpers used by the WR / QB / CB observation builders."""
import math

from engine.physics import PlayerState, CUT_RECOVERY_BASE_STEPS, PLAYER_RADIUS
from engine.resolution import HIGH_BALL_Z

FIELD_WIDTH = 53.3   # yards sideline to sideline
OOB_WARN_DIST = 3.0  # yards from sideline to warn the WR


def dist(a: PlayerState, b: PlayerState) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def heading_label(deg: float) -> str:
    """Human-readable direction. 0=upfield, 90=right, 180=back to QB, 270=left.
    WR1 is on the LEFT, so 90 = inside (toward middle), 270 = his sideline."""
    deg = deg % 360
    if deg <= 22 or deg >= 338:
        return "straight upfield"
    elif deg <= 67:
        return "diagonal upfield-inside"
    elif deg <= 112:
        return "inside (toward middle)"
    elif deg <= 157:
        return "back-inside (toward QB)"
    elif deg <= 202:
        return "straight back toward QB"
    elif deg <= 247:
        return "back-outside (toward QB, sideline side)"
    elif deg <= 292:
        return "outside (toward left sideline)"
    else:
        return "diagonal upfield-outside (toward sideline)"


def height_label(z: float) -> str:
    if z < 0.9:
        return "low (at the knees)"
    if z <= 2.0:
        return "chest-high"
    if z <= HIGH_BALL_Z:
        return "above the shoulders"
    return "high point (full extension)"


def accel_status(cut_recovery: int) -> str:
    """Burst-acceleration status from cut_recovery steps remaining."""
    if cut_recovery == 0:
        return "FULL burst available"
    frac = cut_recovery / CUT_RECOVERY_BASE_STEPS
    pct = int((1 - frac * 0.75) * 100)
    return f"RECOVERING from a cut — {cut_recovery} steps left, burst ~{pct}% (hips committed)"


def body_gap(sep: float) -> float:
    """Edge-to-edge gap between two 0.5yd-radius bodies."""
    return max(0.0, sep - 2 * PLAYER_RADIUS)


def down_str(down: int, distance: int) -> str:
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    return f"{down}{suffixes.get(down, 'th')} & {distance}"


def move_log_table(history: list[dict], window: int = 12) -> list[str]:
    """Side-by-side WR/CB move log with cut-recovery and CB heading-delta (deception feedback)."""
    if not history:
        return []
    recent = history[-window:]
    lines = [
        "MOVE LOG (every 0.1s) — your moves vs the CB's reaction:",
        f"  {'t':>5}  {'WR hdg':>7}  {'WR spd':>6}  {'WR rec':>6}  {'CB hdg':>7}  {'CB spd':>6}  {'CB rec':>6}  {'CB Δhdg':>8}",
    ]
    prev_cb = None
    for h in recent:
        cb_hdg = h.get("cb_hdg")
        wr_rec = h.get("wr_cut_rec", 0)
        cb_rec = h.get("cb_cut_rec", 0)
        if cb_hdg is not None and prev_cb is not None:
            d = abs((cb_hdg - prev_cb + 180) % 360 - 180)
            delta = f"+{d:.0f}" if d >= 1 else "0"
        else:
            delta = "--"
        cb_hdg_s = f"{cb_hdg:.0f}" if cb_hdg is not None else "--"
        lines.append(
            f"  {h['t']:>5.1f}  {h['wr_hdg']:>6.0f}°  {h.get('wr_spd', 0.0):>6.1f}"
            f"  {(str(wr_rec)+'rec' if wr_rec else 'free'):>6}"
            f"  {cb_hdg_s:>6}°  {h.get('cb_spd', 0.0):>6.1f}"
            f"  {(str(cb_rec)+'rec' if cb_rec else 'free'):>6}  {delta:>8}"
        )
        if cb_hdg is not None:
            prev_cb = cb_hdg
    return lines
