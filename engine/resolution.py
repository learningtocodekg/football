import math
import random
from .physics import PlayerState, PlayerAttrs

CATCH_RADIUS = 1.3   # yards — ball must land within this of WR
PBU_PROXIMITY = 1.0  # yards — CB must be this close to WR for a PBU to be possible
# A PBU also triggers if the CB is between the QB and WR (ball path) within this range
PBU_LANE_RANGE = 1.5  # yards — CB within this of the ball's flight path counts as contesting


def _sigmoid(x: float, mid: float = 2.5, k: float = 1.2) -> float:
    return 1.0 / (1.0 + math.exp(-(x - mid) / k))


def _cb_in_passing_lane(
    cb: PlayerState,
    landing_x: float,
    landing_y: float,
    wr: PlayerState,
) -> bool:
    """True if CB is between the WR and the landing spot (on the ball's path) within PBU_LANE_RANGE."""
    # Vector from landing spot to WR
    vx = wr.x - landing_x
    vy = wr.y - landing_y
    length = math.hypot(vx, vy)
    if length < 0.01:
        return False
    # Project CB onto that segment
    px = cb.x - landing_x
    py = cb.y - landing_y
    t = max(0.0, min(1.0, (px * vx + py * vy) / (length * length)))
    closest_x = landing_x + t * vx
    closest_y = landing_y + t * vy
    dist_to_lane = math.hypot(cb.x - closest_x, cb.y - closest_y)
    return dist_to_lane <= PBU_LANE_RANGE


def resolve(
    wr: PlayerState,
    cb: PlayerState,
    wr_attrs: PlayerAttrs,
    cb_attrs: PlayerAttrs,
    landing_x: float,
    landing_y: float,
    cb_intent: str,  # "play_man" | "go_for_pick" | "swat"
    rng: random.Random,
) -> dict:

    ball_offset = math.hypot(landing_x - wr.x, landing_y - wr.y)
    separation = math.hypot(wr.x - cb.x, wr.y - cb.y)

    if ball_offset > CATCH_RADIUS:
        return {
            "outcome": "INCOMPLETE",
            "separation": round(separation, 2),
            "ball_offset": round(ball_offset, 2),
            "note": "ball landed out of WR reach",
        }

    # CB can only contest (PBU/INT) if they are close enough to the WR at arrival,
    # or are sitting in the passing lane between ball and WR.
    cb_close = separation <= PBU_PROXIMITY
    cb_in_lane = _cb_in_passing_lane(cb, landing_x, landing_y, wr)
    cb_can_contest = cb_close or cb_in_lane

    # Base catch probability: smooth sigmoid over separation
    floor_prob = 0.15
    p_raw = floor_prob + (1 - floor_prob) * _sigmoid(separation)
    catch_factor = wr_attrs.catch / 99.0
    coverage_suppression = (cb_attrs.coverage / 99.0) * 0.30 if cb_can_contest else 0.0
    p_catch = p_raw * catch_factor * (1.0 - coverage_suppression)
    p_catch = max(0.05, min(0.97, p_catch))

    r = rng.random()
    if r < p_catch:
        return {"outcome": "CATCH", "separation": round(separation, 2), "p_catch": round(p_catch, 3)}

    # If CB cannot contest, it's just a drop — no PBU/INT possible from 6 yards away
    if not cb_can_contest:
        return {"outcome": "DROP", "separation": round(separation, 2)}

    # Contested — outcome depends on CB intent
    bs = cb_attrs.ball_skills / 99.0
    r2 = rng.random()

    if cb_intent == "go_for_pick":
        if r2 < bs * 0.40:
            return {"outcome": "INTERCEPTION", "separation": round(separation, 2)}
        if r2 < bs * 0.70:
            return {"outcome": "PBU", "separation": round(separation, 2)}
        # CB gambled and whiffed — WR gets a bonus catch chance
        if rng.random() < p_catch * 1.25:
            return {"outcome": "CATCH", "separation": round(separation, 2), "note": "CB gamble whiffed"}
        return {"outcome": "DROP", "separation": round(separation, 2)}

    if cb_intent == "swat":
        if r2 < bs * 0.60:
            return {"outcome": "PBU", "separation": round(separation, 2)}
        return {"outcome": "DROP", "separation": round(separation, 2)}

    # play_man (default)
    if r2 < bs * 0.30:
        return {"outcome": "PBU", "separation": round(separation, 2)}
    return {"outcome": "DROP", "separation": round(separation, 2)}
