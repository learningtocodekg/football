"""Coverage control resolver (freedom branch).

The CB outputs a pursuit INTENT — a `mode` plus a small bounded `tilt` — and this turns it into
concrete movement (heading, facing, movement-mode) from live geometry. The CB owns the decision
(which intent + how much to shade); the engine owns the trig. This is the CB analog of the WR's
semantic directions, and follows the project principle: if a sub-decision is pure physics with a
correct answer, the LLM should not own it.

Why this shape: a raw per-tick heading let stateless noise become physical thrashing (and cut-recovery
penalties). A coarse mode is sticky, and the tilt is clamped INSIDE the cut-recovery angle threshold so
that tilt-wobble can never trigger a recovery penalty — the fine control can't become a new flip-flop."""
import math

from engine.physics import PlayerState

TILT_LIMIT = 25.0  # deg; < CUT_ANGLE_THRESHOLD (35) so a wobbling tilt never triggers cut recovery
MODES = ("shadow", "drive", "bail")


def _bearing(fx: float, fy: float, tx: float, ty: float) -> float:
    """Compass-style bearing from (fx,fy) to (tx,ty): 0°=+y (upfield), 90°=+x."""
    return math.degrees(math.atan2(tx - fx, ty - fy)) % 360.0


def resolve_coverage(mode: str, tilt: float, cb: PlayerState, wr: PlayerState,
                     drive_target: tuple[float, float] | None = None) -> tuple[float, float, str]:
    """(mode, tilt, cb, wr) -> (heading, facing, movement_mode).

    - shadow: mirror the WR's run direction and stay on his hip — retreat the way he is running while
      keeping eyes on him. Backpedal (capped at 75% speed). The default coverage stance.
    - drive:  close on `drive_target` at full speed (defaults to the WR's projected spot 0.5s ahead;
      the runner passes the ball's landing spot once it's in the air). Normal mode, eyes on the target.
    - bail:   open the hips and run WITH him on his heading at full speed — the turn-and-run answer to a
      vertical you can't backpedal with.
    `tilt` shades leverage inside/outside; clamped to +/-TILT_LIMIT."""
    mode = mode if mode in MODES else "shadow"
    tilt = max(-TILT_LIMIT, min(TILT_LIMIT, float(tilt)))

    if mode == "shadow":
        base = wr.heading
        facing = _bearing(cb.x, cb.y, wr.x, wr.y)  # eyes on the WR
        move_mode = "backpedal"
    elif mode == "drive":
        if drive_target is None:
            wr_h = math.radians(wr.heading)
            tx = wr.x + math.sin(wr_h) * wr.speed * 0.5
            ty = wr.y + math.cos(wr_h) * wr.speed * 0.5
        else:
            tx, ty = drive_target
        base = _bearing(cb.x, cb.y, tx, ty)
        facing = base
        move_mode = "normal"
    else:  # bail
        base = wr.heading
        facing = base
        move_mode = "normal"

    heading = (base + tilt) % 360.0
    return heading, facing, move_mode
