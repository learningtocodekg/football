import math
import random
from .physics import PlayerState, PlayerAttrs
from .ball import BallState, ball_z_at_xy, DEFAULT_TARGET_Z

CATCH_RADIUS = 1.3    # yards — ball must land within this of WR
PBU_PROXIMITY = 1.5   # yards — CB must be within this center-to-center for a PBU attempt
PBU_LANE_RANGE = 1.5  # yards — CB within this of the ball's flight path counts as contesting

CB_ARM_REACH = 1.0    # yards — full arm reach for PBU (swat)
CB_HALF_REACH = 0.5   # yards — half arm reach for INT (go_for_pick)
CB_FACING_CONE = 60.0 # degrees — CB must face within this of ball direction for PBU/INT

# ── Vertical reach (static model — no jump action; reach includes a routine hop) ──
WR_VERTICAL_REACH = 3.0  # yards — max ball height the WR can catch
CB_VERTICAL_REACH = 3.0  # yards — max ball height the CB can touch
HIGH_BALL_Z = 2.4        # above this, the ball is a high-point throw: harder catch,
                         # and the CB can only swat/pick at full extension (reduced odds)

# ── Three-zone catch resolution thresholds (separation-at-arrival, yards) ──
# Anchored to empirical data: sep >= 1.8yd at arrival = catch.
OPEN_SEP = 1.8   # separation >= this: WR won the rep -> deterministic CATCH
TIGHT_SEP = 1.0  # separation <= this: bodies on top of each other -> deterministic CB win


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


def _catch_height_multiplier(z: float) -> float:
    """Catch probability multiplier by arrival height. Chest-high is easiest."""
    if z < 0.9:
        return 0.85   # low scoop at the shoelaces
    if z <= 2.0:
        return 1.0    # breadbasket
    if z <= HIGH_BALL_Z:
        return 0.92   # above the shoulders
    return 0.78       # high point at full extension


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
    ball: BallState | None = None,
) -> dict:

    landing_z = ball.landing_z if ball is not None else DEFAULT_TARGET_Z
    ball_offset = math.hypot(landing_x - wr.x, landing_y - wr.y)
    separation = math.hypot(wr.x - cb.x, wr.y - cb.y) if cb is not None else 99.0

    if ball_offset > CATCH_RADIUS:
        return {
            "outcome": "INCOMPLETE",
            "separation": round(separation, 2),
            "ball_offset": round(ball_offset, 2),
            "landing_z": round(landing_z, 2),
            "note": "ball landed out of WR reach",
        }

    if landing_z > WR_VERTICAL_REACH:
        return {
            "outcome": "INCOMPLETE",
            "separation": round(separation, 2),
            "landing_z": round(landing_z, 2),
            "note": "ball arrived above WR vertical reach",
        }

    cb_can_contest = False
    cb_facing = False
    cb_arm_pbu = False
    cb_arm_int = False
    if cb is not None and cb_attrs is not None:
        # In 3D the CB can only touch the ball if it is within vertical reach
        # where it passes him. At the catch point that is the landing height.
        z_at_cb = ball_z_at_xy(ball, cb.x, cb.y) if ball is not None else landing_z
        cb_vertical_ok = (z_at_cb is None) or (z_at_cb <= CB_VERTICAL_REACH)
        cb_close = separation <= PBU_PROXIMITY and landing_z <= CB_VERTICAL_REACH
        cb_in_lane = cb_vertical_ok and _cb_in_passing_lane(cb, landing_x, landing_y, wr)
        cb_can_contest = cb_close or cb_in_lane
        cb_facing = _cb_facing_ball(cb, landing_x, landing_y)
        cb_arm_pbu = cb_facing and _cb_arm_reaches_lane(cb, landing_x, landing_y, wr, CB_ARM_REACH)
        cb_arm_int = cb_facing and _cb_arm_reaches_lane(cb, landing_x, landing_y, wr, CB_HALF_REACH)

    go_for_pick = cb_intent == "go_for_pick"
    high_ball = landing_z > HIGH_BALL_Z
    # On a high ball the CB can only pick at full extension; gate the gamble off.
    int_ok = cb_arm_int and cb_facing and not high_ball

    # ── Three-zone resolver keyed on separation-at-arrival ──
    # 1. CB not in position to touch the ball -> deterministic CATCH.
    if not cb_can_contest or cb_attrs is None:
        return {"outcome": "CATCH", "separation": round(separation, 2), "landing_z": round(landing_z, 2)}

    # 2. WR created real separation, CB present but beaten -> deterministic CATCH.
    if separation >= OPEN_SEP:
        return {"outcome": "CATCH", "separation": round(separation, 2), "landing_z": round(landing_z, 2)}

    # 3. Bodies in contact -> deterministic CB win; type by intent + geometry.
    if separation <= TIGHT_SEP:
        if go_for_pick and int_ok:
            return {"outcome": "INTERCEPTION", "separation": round(separation, 2),
                    "landing_z": round(landing_z, 2)}
        return {"outcome": "PBU", "separation": round(separation, 2), "landing_z": round(landing_z, 2)}

    # 4. Contested band — the only place a die is thrown.
    frac = (separation - TIGHT_SEP) / (OPEN_SEP - TIGHT_SEP)
    catch_factor = wr_attrs.catch / 99.0
    coverage_suppression = (cb_attrs.coverage / 99.0) * 0.30
    wr_facing_mult = _wr_facing_multiplier(wr, qb_x, qb_y)
    height_mult = _catch_height_multiplier(landing_z)
    p_catch = frac * catch_factor * (1.0 - coverage_suppression) * wr_facing_mult * height_mult
    p_catch = max(0.05, min(0.95, p_catch))

    if rng.random() < p_catch:
        return {"outcome": "CATCH", "separation": round(separation, 2), "p_catch": round(p_catch, 3),
                "landing_z": round(landing_z, 2)}

    # CB wins; type by intent (single deterministic branch, no extra roll).
    if go_for_pick:
        if int_ok:
            return {"outcome": "INTERCEPTION", "separation": round(separation, 2),
                    "p_catch": round(p_catch, 3), "landing_z": round(landing_z, 2)}
        return {"outcome": "PBU", "separation": round(separation, 2),
                "p_catch": round(p_catch, 3), "landing_z": round(landing_z, 2)}

    if cb_intent == "swat":
        if cb_arm_pbu:
            return {"outcome": "PBU", "separation": round(separation, 2),
                    "p_catch": round(p_catch, 3), "landing_z": round(landing_z, 2)}
        return {"outcome": "DROP", "separation": round(separation, 2),
                "p_catch": round(p_catch, 3), "landing_z": round(landing_z, 2)}

    # play_man
    return {"outcome": "PBU", "separation": round(separation, 2),
            "p_catch": round(p_catch, 3), "landing_z": round(landing_z, 2)}
