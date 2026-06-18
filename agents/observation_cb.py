"""CB observation builders. The CB keeps full autonomy — raw geometry, no option labels or
pre-selected answers. Intent is just play_man (default) or go_for_pick (gamble for the INT)."""
import math

from engine.physics import PlayerState, PlayerAttrs, BACKPEDAL_SPEED_FRACTION
from engine.ball import BallState
from engine.resolution import CB_VERTICAL_REACH, HIGH_BALL_Z
from agents.observation_common import (
    dist, heading_label, height_label, accel_status, body_gap, move_log_table,
)

ZONE_FUZZ_MAX = 4.0
ZONE_FUZZ_MIN = 0.25


def build_cb_pre_snap_observation(cb: PlayerState, cb_attrs: PlayerAttrs, wr: PlayerState) -> str:
    sep = dist(cb, wr)
    bp = cb_attrs.max_speed * BACKPEDAL_SPEED_FRACTION
    return "\n".join([
        "=== CB PRE-SNAP ===",
        "",
        f"WR start: ({wr.x:.1f},{wr.y:.1f})   YOU: ({cb.x:.1f},{cb.y:.1f})   separation {sep:.1f}yd",
        f"Your speed: forward {cb_attrs.max_speed:.1f}yd/s, backpedal {bp:.1f}yd/s.  coverage {cb_attrs.coverage:.0f}/99.",
        "",
        "Pick your alignment:",
        "  offset_yards: cushion off the WR (0=press, ~5=off, 8+=deep)",
        "  side: 'inside' (shade middle), 'outside' (shade sideline), 'press' (head up)",
        'Output JSON: {"offset_yards": <n>, "side": "...", "reasoning": "..."}',
    ])


def build_cb_observation(
    t: float,
    cb: PlayerState,
    cb_attrs: PlayerAttrs,
    wr: PlayerState,
    ball: BallState,
    wr_history: list[dict] | None = None,
    ball_total_eta: float | None = None,
    cb_intent: str = "play_man",
    detected_cut_t: float | None = None,
) -> str:
    sep = dist(cb, wr)
    bearing_to_wr = math.degrees(math.atan2(wr.x - cb.x, wr.y - cb.y)) % 360.0
    # WR projected 0.5s ahead on current heading/speed — the lead point you must cover.
    wr_hdg = math.radians(wr.heading)
    proj_x = wr.x + math.sin(wr_hdg) * wr.speed * 0.5
    proj_y = wr.y + math.cos(wr_hdg) * wr.speed * 0.5
    intercept = math.degrees(math.atan2(proj_x - cb.x, proj_y - cb.y)) % 360.0

    lines = [
        f"=== CB  t={t:.1f}s ===",
        "",
        f"YOU: ({cb.x:.1f},{cb.y:.1f}) speed={cb.speed:.1f}yd/s heading={cb.heading:.0f}° "
        f"facing={cb.facing:.0f}° mode={cb.mode}",
        f"  burst: {accel_status(cb.cut_recovery)}",
        f"WR: ({wr.x:.1f},{wr.y:.1f}) speed={wr.speed:.1f}yd/s heading={wr.heading:.0f}° "
        f"({heading_label(wr.heading)}) facing={wr.facing:.0f}°",
        f"  burst: {accel_status(wr.cut_recovery)}",
        "",
        "GEOMETRY:",
        f"  separation {sep:.1f}yd (body gap {body_gap(sep):.1f}yd)  |  bearing you→WR {bearing_to_wr:.0f}°",
        f"  WR projected in 0.5s: ({proj_x:.1f},{proj_y:.1f})  |  heading to that point: {intercept:.0f}°",
        f"  your speeds: forward {cb_attrs.max_speed:.1f}, backpedal {cb_attrs.max_speed*BACKPEDAL_SPEED_FRACTION:.1f} yd/s",
    ]
    if wr.cut_recovery >= 2:
        lines.append(f"  !! WR is hip-committed for {wr.cut_recovery} steps — close hard now.")

    if ball.state == "in_air":
        if ball_total_eta and ball_total_eta > 0:
            fuzz = max(ZONE_FUZZ_MIN, ZONE_FUZZ_MAX * (ball.eta / ball_total_eta))
        else:
            fuzz = ZONE_FUZZ_MAX
        dist_to_zone = math.hypot(cb.x - ball.landing_x, cb.y - ball.landing_y)
        bearing_to_zone = math.degrees(math.atan2(ball.landing_x - cb.x, ball.landing_y - cb.y)) % 360.0
        lines += [
            "",
            f"BALL IN AIR (your intent: {cb_intent}):  ETA {ball.eta:.2f}s",
            f"  landing ({ball.landing_x:.1f},{ball.landing_y:.1f}) ±{fuzz:.1f}yd at z={ball.landing_z:.1f} "
            f"({height_label(ball.landing_z)}); your vertical reach {CB_VERTICAL_REACH:.1f}yd.",
            f"  your distance to landing {dist_to_zone:.1f}yd; heading to it {bearing_to_zone:.0f}°.",
        ]
        if cb_intent == "play_man":
            lines.append(f"  play_man: stay on the WR — heading {bearing_to_zone:.0f}° to the spot, "
                         f"facing {bearing_to_wr:.0f}° (the WR), and hit him at the catch.")
        else:
            lines.append(f"  go_for_pick: attack the ball — heading AND facing {bearing_to_zone:.0f}° to the spot.")
        if ball.landing_z > HIGH_BALL_Z:
            lines.append(f"  HIGH BALL (z={ball.landing_z:.1f}) — you can only reach at full extension.")

    if wr_history:
        lines += ["", *move_log_table(wr_history)]
    if detected_cut_t is not None:
        lines += ["", f"CUT CONFIRMED: WR made a real cut at t={detected_cut_t:.1f}s — established, don't re-derive it."]
    return "\n".join(lines)


def build_cb_intent_observation(
    t: float,
    cb: PlayerState,
    cb_attrs: PlayerAttrs,
    wr: PlayerState,
    ball: BallState,
    ball_total_eta: float,
) -> str:
    sep = dist(cb, wr)
    dist_to_zone = math.hypot(cb.x - ball.landing_x, cb.y - ball.landing_y)
    bearing_to_ball = math.degrees(math.atan2(ball.landing_x - cb.x, ball.landing_y - cb.y)) % 360.0
    facing_diff = abs((bearing_to_ball - cb.facing + 180.0) % 360.0 - 180.0)
    sprint_time = dist_to_zone / max(cb_attrs.max_speed, 0.1)
    return "\n".join([
        f"=== CB INTENT  t={t:.1f}s  ETA={ball.eta:.2f}s ===",
        "",
        f"ball landing ({ball.landing_x:.1f},{ball.landing_y:.1f}) at z={ball.landing_z:.1f} ({height_label(ball.landing_z)}).",
        f"you ({cb.x:.1f},{cb.y:.1f}) facing {cb.facing:.0f}°; separation from WR {sep:.2f}yd.",
        f"distance to landing {dist_to_zone:.1f}yd → sprint time {sprint_time:.2f}s vs ball ETA {ball.eta:.2f}s.",
        f"bearing to ball {bearing_to_ball:.0f}°, your facing off by {facing_diff:.0f}°.",
        "",
        "CHOOSE your play on the ball:",
        "  play_man   — stay glued to the WR and hit him as it arrives; a PBU is the natural result of "
        "tight man coverage. Safe, reliable disruption. (default)",
        "  go_for_pick — leave the WR to attack the ball for an INT: only worth it if you can get there "
        "(sprint time < ETA) and are facing it; otherwise you give up a clean catch.",
        'Output JSON: {"intent": "play_man" | "go_for_pick", "reasoning": "..."}',
    ])
