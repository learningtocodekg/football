"""Deterministic unit tests for the WR soft route rail (no LLM).

Verifies the safety-net mechanics independent of model noise:
  - go: a sustained sideways bail is leashed back; a brief juke is free
  - call commits the WR to his route line (no calling mid-juke)
  - call is held until the route's FINAL break (can't call on the stem or a fake)
  - settle routes: the WR plants and STOPS, and the call fires only when planted
  - stem is DEPTH-gated: the WR reaches the route's depth before breaking
  - double_move/zig: both cuts are guaranteed
"""
import math
from agents.scripted import RouteRail, LEASH_DISTANCE, SETTLE_DISTANCE
from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff

ATTRS = PlayerAttrs(max_speed=9.5, acceleration=14.0, agility=70.0)


def _run(route, decisions, dt=0.1):
    """Drive a RouteRail through `decisions` (one dict per tick), applying engine motion.
    Returns (list of (t, state, governed, leg_i), rail)."""
    rail = RouteRail(route)
    state = PlayerState(x=16.0, y=50.0, speed=1.4, heading=0.0)
    out = []
    t = 0.0
    for dec in decisions:
        gov = rail.govern(t, state, dict(dec))
        leg_i = rail.leg_i
        target = float(gov.get("heading", state.heading))
        turn = max(-90.0, min(90.0, angle_diff(target, state.heading)))
        throttle = "brake" if gov.get("throttle") == "brake" else "accelerate"
        state = apply_action(state, ATTRS, turn, throttle, dt)
        out.append((round(t, 1), state, gov, leg_i))
        t += dt
    return out, rail


def test_go_sustained_bail_is_leashed():
    decs = [{"heading": 0}] * 10 + [{"heading": 270}] * 15
    out, _ = _run("go", decs)
    max_drift = max(abs(s.x - 16.0) for _, s, _, _ in out)
    assert max_drift < LEASH_DISTANCE + 2.0, f"WR drifted {max_drift}yd off the go line — leash failed"
    final_hdg = out[-1][2]["heading"]
    assert not (200 < final_hdg < 340), f"rail should have recovered heading, got {final_hdg}"


def test_go_brief_juke_is_allowed():
    decs = [{"heading": 0}] * 6 + [{"heading": 90}, {"heading": 90}] + [{"heading": 0}] * 6
    out, _ = _run("go", decs)
    assert out[6][2]["heading"] == 90 and out[7][2]["heading"] == 90, "brief juke must not be overridden"


def test_call_commits_to_route_line():
    rail = RouteRail("go")
    state = PlayerState(x=15.0, y=53.0, speed=8.0, heading=270.0)
    gov = rail.govern(1.0, state, {"heading": 270, "call_for_ball": True})
    assert gov["heading"] == 0.0, f"call should commit to route heading 0, got {gov['heading']}"


def test_stem_backward_run_is_leashed():
    # WR tries to break BACKWARD (225) from the snap on the comeback stem (leg 0 = 0deg).
    decs = [{"heading": 225}] * 15
    out, _ = _run("comeback", decs)
    min_y = min(s.y for _, s, _, _ in out)
    assert min_y > 48.5, f"WR ran backward past the LOS (min y={min_y}) — backward leash failed"


def test_comeback_reaches_depth_then_settles():
    # Run a real stem (heading 0) to depth, then break back (225). The WR must reach a
    # real comeback depth before breaking, then plant and STOP.
    decs = [{"heading": 0}] * 22 + [{"heading": 225}] * 25
    out, rail = _run("comeback", decs)
    break_idx = next(i for i, (_, _, _, li) in enumerate(out) if li == 1)
    break_depth = out[break_idx][1].y - 50.0
    assert break_depth > 8.0, f"comeback broke too shallow: depth={break_depth}yd"
    assert rail.settled and out[-1][1].speed < 0.5, "comeback should plant and stop"


def test_curl_settles_and_stops():
    decs = [{"heading": 0}] * 20 + [{"heading": 180}] * 25
    out, rail = _run("curl", decs)
    assert rail.settled and out[-1][1].speed < 0.5, "curl WR should plant and stop"


def test_call_held_until_final_break():
    # Call on EVERY step of a slant. No call may fire while still on the stem (leg 0);
    # it fires once on the break leg (leg 1).
    decs = [{"heading": 0, "call_for_ball": True}] * 10 + [{"heading": 45, "call_for_ball": True}] * 10
    out, _ = _run("slant", decs)
    stem_calls = [g.get("call_for_ball") for _, _, g, li in out if li == 0]
    assert not any(stem_calls), "no call may fire on the stem"
    assert any(g.get("call_for_ball") for _, _, g, li in out if li == 1), "call must fire at the break"


def test_double_move_cannot_call_during_fake():
    decs = ([{"heading": 0}] * 16
            + [{"heading": 90, "call_for_ball": True}] * 5
            + [{"heading": 0, "call_for_ball": True}] * 10)
    out, _ = _run("double_move", decs)
    assert not any(g.get("call_for_ball") for _, _, g, li in out if li == 1), "no call during the fake"
    assert any(g.get("call_for_ball") for _, _, g, li in out if li == 2), "call fires on the snap-back"


def test_settle_call_held_through_stem_then_fires_on_break():
    # A call during the stem is held; it fires once the WR starts the break back (on the
    # settle leg) — as he hooks, not after he is fully planted.
    decs = [{"heading": 0, "call_for_ball": True}] * 22 + [{"heading": 225, "call_for_ball": True}] * 20
    out, rail = _run("comeback", decs)
    assert not any(g.get("call_for_ball") for _, _, g, li in out if li == 0), "no call on the stem"
    assert any(g.get("call_for_ball") for _, _, g, li in out if li == 1), "call fires on the break-back leg"


def test_double_move_guarantees_both_cuts():
    decs = [{"heading": 0}] * 30
    out, rail = _run("double_move", decs)
    legs_seen = {li for _, _, _, li in out}
    assert 1 in legs_seen and 2 in legs_seen, f"double_move must hit both cuts, saw legs {legs_seen}"
