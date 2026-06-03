import math
from dataclasses import dataclass


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
    facing: float = 0.0
    mode: str = "normal"


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
) -> PlayerState:
    new_heading = (state.heading + turn_deg) % 360.0

    # Turn sheds speed: ~95% loss at 90° for agility=50 (baseline)
    agility_factor = attrs.agility / 50.0
    shed = state.speed * (abs(turn_deg) / 90.0) * 0.95 / agility_factor
    shed = min(shed, state.speed)
    speed_post_turn = state.speed - shed

    if throttle == "accelerate":
        new_speed = min(attrs.max_speed, speed_post_turn + attrs.acceleration * dt)
    elif throttle == "brake":
        new_speed = max(0.0, speed_post_turn - attrs.acceleration * 1.5 * dt)
    else:  # hold
        new_speed = speed_post_turn

    dx, dy = heading_to_dxdy(new_heading)
    return PlayerState(
        x=state.x + dx * new_speed * dt,
        y=state.y + dy * new_speed * dt,
        speed=new_speed,
        heading=new_heading,
        facing=new_heading,
        mode=state.mode,
    )
