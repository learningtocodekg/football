import math
from dataclasses import dataclass

BACKPEDAL_SPEED_FRACTION = 0.75  # CB max speed when backpedaling


@dataclass
class PlayerAttrs:
    name: str = ""
    max_speed: float = 8.0       # yd/s
    acceleration: float = 12.0   # yd/s²
    agility: float = 70.0        # 0–99; higher = less speed loss on cuts
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
    heading: float = 0.0   # degrees: 0=upfield(+y), 90=right(+x), clockwise
    facing: float = 0.0    # direction player is facing (may differ from heading when backpedaling)
    mode: str = "normal"   # "normal" | "backpedal" | "brake"


def heading_to_dxdy(heading_deg: float) -> tuple[float, float]:
    """Return (dx, dy) unit vector for the given heading."""
    rad = math.radians(heading_deg)
    return math.sin(rad), math.cos(rad)


def angle_diff(target: float, current: float) -> float:
    """Signed shortest-path difference (target − current), range [−180, 180]."""
    return (target - current + 180.0) % 360.0 - 180.0


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

    # Turn sheds speed: ~95% loss at 90° for agility=50 (baseline)
    agility_factor = attrs.agility / 50.0
    shed = state.speed * (abs(turn_deg) / 90.0) * 0.95 / agility_factor
    shed = min(shed, state.speed)
    speed_post_turn = state.speed - shed

    # Backpedal caps max speed at BACKPEDAL_SPEED_FRACTION of max_speed
    effective_max = (
        attrs.max_speed * BACKPEDAL_SPEED_FRACTION if mode == "backpedal" else attrs.max_speed
    )

    if throttle == "accelerate":
        new_speed = min(effective_max, speed_post_turn + attrs.acceleration * dt)
    elif throttle == "brake":
        new_speed = max(0.0, speed_post_turn - attrs.acceleration * 1.5 * dt)
    else:  # hold
        new_speed = min(effective_max, speed_post_turn)

    dx, dy = heading_to_dxdy(new_heading)
    # facing: use explicitly provided value, else default to heading (for non-CB players)
    facing = new_facing if new_facing is not None else new_heading
    return PlayerState(
        x=state.x + dx * new_speed * dt,
        y=state.y + dy * new_speed * dt,
        speed=new_speed,
        heading=new_heading,
        facing=facing,
        mode=mode,
    )
