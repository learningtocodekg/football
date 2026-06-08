import math
from dataclasses import dataclass, field

BACKPEDAL_SPEED_FRACTION = 0.75  # CB max speed when backpedaling

# A cut >= this angle at speed >= CUT_SPEED_THRESHOLD triggers hip-turn recovery
CUT_ANGLE_THRESHOLD = 35.0   # degrees
CUT_SPEED_THRESHOLD = 3.0    # yd/s — below this speed, small direction changes are cheap

# Steps of reduced acceleration after a hard cut (at full speed, agility=50)
# Scales down with agility and with how slow the player was moving
CUT_RECOVERY_BASE_STEPS = 4   # steps @ 0.1s each = 0.4s base recovery


@dataclass
class PlayerAttrs:
    name: str = ""
    max_speed: float = 8.0       # yd/s
    acceleration: float = 12.0   # yd/s² — peak burst acceleration (from rest)
    agility: float = 70.0        # 0–99; higher = faster cut recovery, less speed shed
    catch: float = 80.0
    catch_in_traffic: float = 70.0
    route_running: float = 80.0
    coverage: float = 80.0
    ball_skills: float = 70.0
    play_recognition: float = 70.0
    throw_power: float = 85.0    # 0–99; caps max ball speed


@dataclass
class PlayerState:
    x: float
    y: float
    speed: float = 0.0
    heading: float = 0.0      # degrees: 0=upfield(+y), 90=right(+x), clockwise
    facing: float = 0.0       # direction player is facing (may differ from heading when backpedaling)
    mode: str = "normal"      # "normal" | "backpedal" | "brake"
    cut_recovery: int = 0     # steps remaining in hip-turn recovery (0 = free to burst)


def heading_to_dxdy(heading_deg: float) -> tuple[float, float]:
    """Return (dx, dy) unit vector for the given heading."""
    rad = math.radians(heading_deg)
    return math.sin(rad), math.cos(rad)


def angle_diff(target: float, current: float) -> float:
    """Signed shortest-path difference (target − current), range [−180, 180]."""
    return (target - current + 180.0) % 360.0 - 180.0


def cut_recovery_steps(turn_deg: float, speed: float, attrs: PlayerAttrs) -> int:
    """
    How many steps of reduced acceleration result from a hard cut.

    A cut is only penalized when:
      - The angle change exceeds CUT_ANGLE_THRESHOLD, AND
      - The player is moving faster than CUT_SPEED_THRESHOLD (hips have momentum)

    Recovery scales with:
      - Turn magnitude (sharper cut = longer recovery)
      - Speed at the moment of cut (more momentum = harder to redirect)
      - Agility (higher agility = shorter recovery)
    """
    if abs(turn_deg) < CUT_ANGLE_THRESHOLD or speed < CUT_SPEED_THRESHOLD:
        return 0
    angle_factor = min(abs(turn_deg) / 90.0, 1.0)      # 0→1 as turn goes 0→90°
    speed_factor = min(speed / 8.0, 1.0)                # 0→1 as speed goes 0→8 yd/s
    agility_factor = attrs.agility / 70.0               # 1.0 at baseline, lower = worse
    raw = CUT_RECOVERY_BASE_STEPS * angle_factor * speed_factor / agility_factor
    return max(1, round(raw))


def apply_action(
    state: PlayerState,
    attrs: PlayerAttrs,
    turn_deg: float,
    throttle: str,  # "accelerate" | "hold" | "brake"
    dt: float = 0.1,
    new_facing: float | None = None,
    new_mode: str | None = None,
) -> PlayerState:
    new_heading = (state.heading + turn_deg) % 360.0
    mode = new_mode if new_mode is not None else state.mode

    # ── Cut detection: does this turn commit the player's hips? ─────────
    recovery_triggered = cut_recovery_steps(turn_deg, state.speed, attrs)
    new_cut_recovery = max(0, state.cut_recovery - 1)  # tick down existing recovery
    if recovery_triggered > 0:
        # New cut resets the counter (whichever is larger wins)
        new_cut_recovery = max(new_cut_recovery, recovery_triggered)

    # ── Speed shed from turning ──────────────────────────────────────────
    # Agility reduces how much speed is lost on a cut.
    # At agility=50 (baseline): 90° cut at full speed loses ~80% of speed.
    # At agility=99: 90° cut loses ~40%. At agility=1: loses nearly all.
    agility_factor = attrs.agility / 50.0
    shed_fraction = (abs(turn_deg) / 90.0) * 0.80 / agility_factor
    shed_fraction = min(shed_fraction, 1.0)
    speed_post_turn = state.speed * (1.0 - shed_fraction)

    # ── Effective max speed given mode ───────────────────────────────────
    effective_max = (
        attrs.max_speed * BACKPEDAL_SPEED_FRACTION if mode == "backpedal" else attrs.max_speed
    )

    # ── Dynamic acceleration: burst scales with remaining headroom ───────
    # From rest: full acceleration available (like a 40-yard-dash explosion).
    # Approaching top speed: acceleration tapers to near-zero.
    # During cut recovery: acceleration is penalized (hips are turned wrong way).
    headroom = max(0.0, effective_max - speed_post_turn) / effective_max
    burst_accel = attrs.acceleration * headroom  # peak accel when far from top speed

    if new_cut_recovery > 0:
        # Hip-turn recovery: player can only access a fraction of their burst
        # The deeper into recovery, the worse. First step after a hard cut is worst.
        recovery_fraction = new_cut_recovery / CUT_RECOVERY_BASE_STEPS
        burst_accel *= max(0.1, 1.0 - recovery_fraction * 0.75)

    if throttle == "accelerate":
        new_speed = min(effective_max, speed_post_turn + burst_accel * dt)
    elif throttle == "brake":
        # Braking uses flat deceleration — you can always slam the brakes
        new_speed = max(0.0, speed_post_turn - attrs.acceleration * 1.5 * dt)
        new_cut_recovery = 0  # braking clears recovery (player is planting)
    else:  # hold / coast
        new_speed = min(effective_max, speed_post_turn)

    dx, dy = heading_to_dxdy(new_heading)
    facing = new_facing if new_facing is not None else new_heading
    return PlayerState(
        x=state.x + dx * new_speed * dt,
        y=state.y + dy * new_speed * dt,
        speed=new_speed,
        heading=new_heading,
        facing=facing,
        mode=mode,
        cut_recovery=new_cut_recovery,
    )
