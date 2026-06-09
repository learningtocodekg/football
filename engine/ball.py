import math
from dataclasses import dataclass

# ── 3D flight constants ───────────────────────────────────────────────────────
G = 10.7              # gravity, yd/s² (= 9.8 m/s²)
RELEASE_Z = 2.2       # QB release height, yards
DEFAULT_TARGET_Z = 1.5  # chest-high catch point
MIN_TARGET_Z = 0.3
MAX_TARGET_Z = 3.0

# Arc profile = launch angle above horizontal. For a given target distance the
# parabola is then fully determined: flight time, required ball speed, peak height.
ARC_ANGLES: dict[str, float] = {
    "bullet": 15.0,   # flat and fast — shortest flight, stays at reachable height
    "drive":  25.0,   # firm throw with a little air under it
    "touch":  35.0,   # over an underneath defender, moderate hang
    "loft":   45.0,   # high rainbow — max range, longest hang time
}

# Ball speed limits (launch speed along the arc), mapped from throw_power 0-99.
# 20 mph = 9.8 yd/s, 60 mph = 29.3 yd/s.
MIN_BALL_SPEED = 9.8    # yd/s
MAX_BALL_SPEED = 29.3   # yd/s
YD_S_TO_MPH = 2.0455    # 1 yd/s = 2.045 mph


def max_ball_speed(throw_power: float) -> float:
    """Max launch speed (yd/s) for a given throw_power rating."""
    return MIN_BALL_SPEED + (throw_power / 99.0) * (MAX_BALL_SPEED - MIN_BALL_SPEED)


def solve_arc(
    dist_xy: float,
    arc: str,
    target_z: float = DEFAULT_TARGET_Z,
    release_z: float = RELEASE_Z,
) -> tuple[float, float, float] | None:
    """Solve the parabola for a throw of horizontal distance dist_xy on the given arc.

    Returns (t_flight, launch_speed, peak_z), or None if the geometry is impossible
    (target higher than the arc can reach at that angle).
    """
    angle = ARC_ANGLES.get(arc)
    if angle is None or dist_xy <= 0.0:
        return None
    theta = math.radians(angle)
    # z(T) = release_z + dist_xy*tan(theta) - 0.5*G*T²  must equal target_z
    drop = release_z + dist_xy * math.tan(theta) - target_z
    if drop <= 0.0:
        return None
    t_flight = math.sqrt(2.0 * drop / G)
    v_h = dist_xy / t_flight
    speed = v_h / math.cos(theta)
    vz = v_h * math.tan(theta)
    peak_z = release_z + (vz * vz) / (2.0 * G) if vz > 0 else release_z
    return t_flight, speed, peak_z


def max_range(arc: str, launch_speed: float, target_z: float = DEFAULT_TARGET_Z) -> float:
    """Max horizontal distance reachable on this arc at the given launch speed."""
    angle = ARC_ANGLES.get(arc)
    if angle is None:
        return 0.0
    theta = math.radians(angle)
    # G·d² − 2v²·sinθcosθ·d − 2v²·cos²θ·(release_z − target_z) = 0, take positive root
    a = G
    b = -2.0 * launch_speed ** 2 * math.sin(theta) * math.cos(theta)
    c = -2.0 * launch_speed ** 2 * math.cos(theta) ** 2 * (RELEASE_Z - target_z)
    disc = b * b - 4.0 * a * c
    if disc < 0:
        return 0.0
    return (-b + math.sqrt(disc)) / (2.0 * a)


@dataclass
class BallState:
    x: float
    y: float
    z: float = 0.0         # height above ground, yards
    state: str = "held"    # "held" | "in_air" | "dead"
    vx: float = 0.0        # yd/s
    vy: float = 0.0
    vz: float = 0.0
    origin_x: float = 0.0  # release point (for trajectory queries)
    origin_y: float = 0.0
    landing_x: float = 0.0
    landing_y: float = 0.0
    landing_z: float = DEFAULT_TARGET_Z
    arc: str = ""
    speed_yd_s: float = 0.0  # launch speed along the arc
    elapsed: float = 0.0
    eta: float = 0.0       # seconds until ball reaches landing spot
    holder_id: str = "QB"


def throw_ball(
    ball: BallState,
    qb_x: float,
    qb_y: float,
    target_x: float,
    target_y: float,
    arc: str,
    throw_power: float,
    target_z: float = DEFAULT_TARGET_Z,
) -> BallState | None:
    """Launch the ball on the given arc toward (target_x, target_y, target_z).

    Returns the new in-air BallState, or None if the throw is physically impossible
    (requires more launch speed than throw_power allows, or invalid geometry).
    """
    target_z = max(MIN_TARGET_Z, min(MAX_TARGET_Z, target_z))
    dx = target_x - qb_x
    dy = target_y - qb_y
    dist = math.hypot(dx, dy) or 1e-6
    sol = solve_arc(dist, arc, target_z)
    if sol is None:
        return None
    t_flight, speed, _peak = sol
    if speed > max_ball_speed(throw_power):
        return None
    v_h = dist / t_flight
    theta = math.radians(ARC_ANGLES[arc])
    return BallState(
        x=qb_x,
        y=qb_y,
        z=RELEASE_Z,
        state="in_air",
        vx=(dx / dist) * v_h,
        vy=(dy / dist) * v_h,
        vz=v_h * math.tan(theta),
        origin_x=qb_x,
        origin_y=qb_y,
        landing_x=target_x,
        landing_y=target_y,
        landing_z=target_z,
        arc=arc,
        speed_yd_s=speed,
        elapsed=0.0,
        eta=t_flight,
    )


def advance_ball(ball: BallState, dt: float = 0.1) -> BallState:
    if ball.state != "in_air":
        return ball
    new_elapsed = ball.elapsed + dt
    if ball.eta - dt <= 0.0:
        # Final step: snap to the landing point instead of overshooting past it
        new_x, new_y = ball.landing_x, ball.landing_y
        new_z = ball.landing_z
    else:
        new_x = ball.x + ball.vx * dt
        new_y = ball.y + ball.vy * dt
        new_z = max(0.0, RELEASE_Z + ball.vz * new_elapsed - 0.5 * G * new_elapsed ** 2)
    return BallState(
        x=new_x,
        y=new_y,
        z=new_z,
        state=ball.state,
        vx=ball.vx,
        vy=ball.vy,
        vz=ball.vz,
        origin_x=ball.origin_x,
        origin_y=ball.origin_y,
        landing_x=ball.landing_x,
        landing_y=ball.landing_y,
        landing_z=ball.landing_z,
        arc=ball.arc,
        speed_yd_s=ball.speed_yd_s,
        elapsed=new_elapsed,
        eta=max(0.0, ball.eta - dt),
    )


def ball_z_at_xy(ball: BallState, px: float, py: float) -> float | None:
    """Ball height when its flight path passes closest to ground point (px, py).

    Projects (px, py) onto the origin→landing line and evaluates the parabola
    there. Returns None if the ball is not in the air.
    """
    if ball.state != "in_air":
        return None
    vx = ball.landing_x - ball.origin_x
    vy = ball.landing_y - ball.origin_y
    length_sq = vx * vx + vy * vy
    if length_sq < 1e-9:
        return ball.z
    frac = ((px - ball.origin_x) * vx + (py - ball.origin_y) * vy) / length_sq
    frac = max(0.0, min(1.0, frac))
    t_total = ball.elapsed + ball.eta
    t = frac * t_total
    return max(0.0, RELEASE_Z + ball.vz * t - 0.5 * G * t ** 2)
