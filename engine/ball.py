import math
from dataclasses import dataclass

MPH_TO_YDS = 1.46667  # yards-per-second per mph


@dataclass
class BallState:
    x: float
    y: float
    state: str = "held"    # "held" | "in_air" | "dead"
    vx: float = 0.0        # yd/s
    vy: float = 0.0
    landing_x: float = 0.0
    landing_y: float = 0.0
    speed_yd_s: float = 0.0
    elapsed: float = 0.0
    eta: float = 0.0       # seconds until ball reaches landing spot
    holder_id: str = "QB"


def throw_ball(
    ball: BallState,
    qb_x: float,
    qb_y: float,
    target_x: float,
    target_y: float,
    ball_speed_mph: float,
) -> BallState:
    speed = ball_speed_mph * MPH_TO_YDS
    dx = target_x - qb_x
    dy = target_y - qb_y
    dist = math.hypot(dx, dy) or 1e-6
    eta = dist / speed
    return BallState(
        x=qb_x,
        y=qb_y,
        state="in_air",
        vx=(dx / dist) * speed,
        vy=(dy / dist) * speed,
        landing_x=target_x,
        landing_y=target_y,
        speed_yd_s=speed,
        elapsed=0.0,
        eta=eta,
    )


def advance_ball(ball: BallState, dt: float = 0.1) -> BallState:
    if ball.state != "in_air":
        return ball
    return BallState(
        x=ball.x + ball.vx * dt,
        y=ball.y + ball.vy * dt,
        state=ball.state,
        vx=ball.vx,
        vy=ball.vy,
        landing_x=ball.landing_x,
        landing_y=ball.landing_y,
        speed_yd_s=ball.speed_yd_s,
        elapsed=ball.elapsed + dt,
        eta=max(0.0, ball.eta - dt),
    )
