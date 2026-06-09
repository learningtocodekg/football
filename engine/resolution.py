import math
import random
from .physics import PlayerState, PlayerAttrs, PLAYER_RADIUS

CATCH_RADIUS = 1.3    # yards — ball must land within this of WR
PBU_PROXIMITY = 1.5   # yards — CB must be within this center-to-center for a PBU attempt
PBU_LANE_RANGE = 1.5  # yards — CB within this of the ball's flight path counts as contesting

CB_ARM_REACH = 1.0    # yards — full arm reach for PBU (swat)
CB_HALF_REACH = 0.5   # yards — half arm reach for INT (go_for_pick)
CB_FACING_CONE = 60.0 # degrees — CB must face within this of ball direction for PBU/INT


def _sigmoid(x: float, mid: float = 0.5, k: float = 0.5) -> float:
    return 1.0 / (1.0 + math.exp(-(x - mid) / k))


def _cb_in_passing_lane(
    cb: PlayerState,
    landing_x: float,
    landing_y: float,
    wr: PlayerState,
) -> bool:
    """True if CB is between the WR and the landing spot (on the ball's path) within PBU_LANE_RANGE."""
    vx = wr.x - landing_x
    vy = wr.y - landing_y
    length = math.hypot(vx, vy)
    if length < 0.01:
        return False
    px = cb.x - landing_x
    py = cb.y - landing_y
    t = max(0.0, min(1.0, (px * vx + py * vy) / (length * length)))
    closest_x = landing_x + t * vx
    closest_y = landing_y + t * vy
    dist_to_lane = math.hypot(cb.x - closest_x, cb.y - closest_y)
    return dist_to_lane <= PBU_LANE_RANGE


def _cb_facing_ball(cb: PlayerState, landing_x: float, landing_y: float) -> bool:
    """True if CB is facing within CB_FACING_CONE degrees of the vector toward the landing spot."""
    dx = landing_x - cb.x
    dy = landing_y - cb.y
    if math.hypot(dx, dy) < 0.01:
        return True
    ball_heading = math.degrees(math.atan2(dx, dy)) % 360.0
    diff = abs((ball_heading - cb.facing + 180.0) % 360.0 - 180.0)
    return diff <= CB_FACING_CONE


def _cb_arm_reaches_lane(
    cb: PlayerState,
    landing_x: float,
    landing_y: float,
    wr: PlayerState,
    reach: float,
) -> bool:
    """True if the tip of CB's arm (reach yards in their facing direction) is within PBU_LANE_RANGE
    of the ball path segment from landing spot to WR."""
    arm_x = cb.x + math.sin(math.radians(cb.facing)) * reach
    arm_y = cb.y + math.cos(math.radians(cb.facing)) * reach

    vx = wr.x - landing_x
    vy = wr.y - landing_y
    length = math.hypot(vx, vy)
    if length < 0.01:
        return math.hypot(arm_x - landing_x, arm_y - landing_y) <= PBU_LANE_RANGE
    px = arm_x - landing_x
    py = arm_y - landing_y
    t = max(0.0, min(1.0, (px * vx + py * vy) / (length * length)))
    closest_x = landing_x + t * vx
    closest_y = landing_y + t * vy
    return math.hypot(arm_x - closest_x, arm_y - closest_y) <= PBU_LANE_RANGE


def _wr_facing_multiplier(wr: PlayerState, qb_x: float, qb_y: float) -> float:
    """Catch probability multiplier based on how well WR is facing the incoming ball."""
    dx = qb_x - wr.x
    dy = qb_y - wr.y
    ball_bearing = math.degrees(math.atan2(dx, dy)) % 360.0
    diff = abs((ball_bearing - wr.facing + 180.0) % 360.0 - 180.0)
    if diff <= 30.0:
        return 1.15   # looking right at QB/ball
    elif diff <= 90.0:
        return 1.0    # sideways (normal catch after a cut)
    else:
        return 0.80   # running blind


def resolve(
    wr: PlayerState,
    cb: PlayerState | None,
    wr_attrs: PlayerAttrs,
    cb_attrs: PlayerAttrs | None,
    landing_x: float,
    landing_y: float,
    cb_intent: str,  # "play_man" | "go_for_pick" | "swat"
    rng: random.Random,
    qb_x: float = 0.0,
    qb_y: float = 0.0,
) -> dict:

    ball_offset = math.hypot(landing_x - wr.x, landing_y - wr.y)
    separation = math.hypot(wr.x - cb.x, wr.y - cb.y) if cb is not None else 99.0

    if ball_offset > CATCH_RADIUS:
        return {
            "outcome": "INCOMPLETE",
            "separation": round(separation, 2),
            "ball_offset": round(ball_offset, 2),
            "note": "ball landed out of WR reach",
        }

    cb_can_contest = False
    cb_facing = False
    cb_arm_pbu = False
    cb_arm_int = False
    if cb is not None and cb_attrs is not None:
        cb_close = separation <= PBU_PROXIMITY
        cb_in_lane = _cb_in_passing_lane(cb, landing_x, landing_y, wr)
        cb_can_contest = cb_close or cb_in_lane
        cb_facing = _cb_facing_ball(cb, landing_x, landing_y)
        cb_arm_pbu = cb_facing and _cb_arm_reaches_lane(cb, landing_x, landing_y, wr, CB_ARM_REACH)
        cb_arm_int = cb_facing and _cb_arm_reaches_lane(cb, landing_x, landing_y, wr, CB_HALF_REACH)

    # Base catch probability: smooth sigmoid over separation
    floor_prob = 0.15
    eff_sep = max(0.0, separation - 2 * PLAYER_RADIUS)  # edge-to-edge air gap between bodies
    p_raw = floor_prob + (1 - floor_prob) * _sigmoid(eff_sep)
    catch_factor = wr_attrs.catch / 99.0
    coverage_suppression = (cb_attrs.coverage / 99.0) * 0.30 if (cb_can_contest and cb_attrs) else 0.0
    wr_facing_mult = _wr_facing_multiplier(wr, qb_x, qb_y)
    p_catch = p_raw * catch_factor * (1.0 - coverage_suppression) * wr_facing_mult
    p_catch = max(0.05, min(0.97, p_catch))

    r = rng.random()
    if r < p_catch:
        return {"outcome": "CATCH", "separation": round(separation, 2), "p_catch": round(p_catch, 3)}

    if not cb_can_contest or cb_attrs is None:
        return {"outcome": "DROP", "separation": round(separation, 2)}

    bs = cb_attrs.ball_skills / 99.0
    r2 = rng.random()

    if cb_intent == "go_for_pick":
        if cb_arm_int:
            if r2 < bs * 0.40:
                return {"outcome": "INTERCEPTION", "separation": round(separation, 2)}
            if r2 < bs * 0.70:
                return {"outcome": "PBU", "separation": round(separation, 2)}
        # CB gambled but arm/facing didn't line up — WR gets a bonus catch chance
        if rng.random() < p_catch * 1.25:
            return {"outcome": "CATCH", "separation": round(separation, 2), "note": "CB gamble whiffed"}
        return {"outcome": "DROP", "separation": round(separation, 2)}

    if cb_intent == "swat":
        if cb_arm_pbu:
            if r2 < bs * 0.60:
                return {"outcome": "PBU", "separation": round(separation, 2)}
        return {"outcome": "DROP", "separation": round(separation, 2)}

    # play_man — no facing requirement; closer hit = more likely drop
    hit_bonus = max(0.0, (PBU_PROXIMITY - separation) / PBU_PROXIMITY) * 0.20
    if r2 < bs * 0.30 + hit_bonus:
        return {"outcome": "PBU", "separation": round(separation, 2)}
    return {"outcome": "DROP", "separation": round(separation, 2)}
