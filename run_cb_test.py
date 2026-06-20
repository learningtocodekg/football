"""CB-only test harness (freedom branch).

Isolates the CB: the WR is a DETERMINISTIC scripted route (with predefined jukes baked in) and the throw
is HARDCODED (fixed tick + target). The ONLY live LLM agent is the CB. This removes WR/QB nondeterminism
so the CB's coverage can actually be judged (a chaotic WR otherwise makes the CB look broken at random).

Tests slant / go / comeback, 3 juke variants each (same overall route, different deceptions), seed 42.

Usage:
    python run_cb_test.py                      # all 3 routes x 3 variants
    python run_cb_test.py --routes slant go    # subset
"""
import argparse
import io
import math
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

from engine.physics import apply_action, angle_diff
from engine.ball import BallState, throw_ball, advance_ball, DEFAULT_TARGET_Z
from engine.resolution import resolve
from engine.state_machine import PlayPhase
from replay.recorder import Recorder
from agents.cb_agent import CBAgent
from agents.observation_cb import (
    build_cb_pre_snap_observation, build_cb_observation, build_cb_intent_observation,
)
from sim.seeds import make_rng
from sim.runner import (
    _build_attrs, _player_snap, _ball_snap, _apply_cb_pre_snap, _load_yaml,
    DT, CUT_DETECT_THRESHOLD,
)

ROSTER = "sim/rosters/default.yaml"

# Each variant: segments = [(n_ticks, heading_deg, throttle), ...] (padded with the last heading after),
# throw_tick (loop step the ball is released), lead (ticks ahead of throw to aim the target), arc.
# Headings: 0=upfield, 45=up-inside, 90=inside(middle), 270=outside(sideline), 315=up-outside, 225=back-outside.
ROUTE_TESTS = {
    "slant": [
        {"label": "inside-jab",  "throw_tick": 14, "lead": 3, "arc": "bullet",
         "segments": [(4, 0, "accelerate"), (1, 90, "accelerate"), (5, 0, "accelerate"), (40, 45, "accelerate")]},
        {"label": "outside-jab", "throw_tick": 14, "lead": 3, "arc": "bullet",
         "segments": [(5, 0, "accelerate"), (1, 315, "accelerate"), (4, 0, "accelerate"), (40, 45, "accelerate")]},
        {"label": "double-hesi", "throw_tick": 15, "lead": 3, "arc": "bullet",
         "segments": [(3, 0, "accelerate"), (1, 90, "accelerate"), (2, 0, "accelerate"),
                      (1, 315, "accelerate"), (3, 0, "accelerate"), (40, 45, "accelerate")]},
    ],
    "go": [
        {"label": "inside-jab",  "throw_tick": 22, "lead": 5, "arc": "lob",
         "segments": [(8, 0, "accelerate"), (1, 90, "accelerate"), (40, 0, "accelerate")]},
        {"label": "outside-jab", "throw_tick": 22, "lead": 5, "arc": "lob",
         "segments": [(10, 0, "accelerate"), (1, 270, "accelerate"), (40, 0, "accelerate")]},
        {"label": "stutter",     "throw_tick": 22, "lead": 5, "arc": "lob",
         "segments": [(9, 0, "accelerate"), (1, 0, "brake"), (40, 0, "accelerate")]},
    ],
    "comeback": [
        {"label": "inside-jab",  "throw_tick": 23, "lead": 0, "arc": "bullet",
         "segments": [(6, 0, "accelerate"), (1, 90, "accelerate"), (12, 0, "accelerate"),
                      (2, 225, "accelerate"), (40, 225, "brake")]},
        {"label": "outside-jab", "throw_tick": 23, "lead": 0, "arc": "bullet",
         "segments": [(10, 0, "accelerate"), (1, 315, "accelerate"), (8, 0, "accelerate"),
                      (2, 225, "accelerate"), (40, 225, "brake")]},
        {"label": "double-hesi", "throw_tick": 24, "lead": 0, "arc": "bullet",
         "segments": [(5, 0, "accelerate"), (1, 90, "accelerate"), (4, 0, "accelerate"),
                      (1, 315, "accelerate"), (8, 0, "accelerate"), (2, 225, "accelerate"),
                      (40, 225, "brake")]},
    ],
}

MAX_TICKS = 60


def _expand(segments):
    """Flatten [(n, hdg, thr), ...] into a per-tick [(hdg, thr), ...] timeline."""
    out = []
    for n, hdg, thr in segments:
        out += [(float(hdg), thr)] * n
    return out


def _step_wr(state, attrs, heading, throttle):
    turn = max(-90.0, min(90.0, angle_diff(heading, state.heading)))
    return apply_action(state, attrs, turn, throttle, DT, new_facing=heading)


def _wr_trajectory(timeline, start, attrs, n):
    """traj[i] = WR state after i scripted moves from `start` (traj[0] = start)."""
    traj = [start]
    s = start
    for i in range(n):
        hdg, thr = timeline[i] if i < len(timeline) else timeline[-1]
        s = _step_wr(s, attrs, hdg, thr)
        traj.append(s)
    return traj


def _meeting_target(qb, traj, throw_tick, arc, throw_power):
    """Hardcoded-but-correct throw: aim at where the WR's deterministic path will BE when the ball
    arrives. Find k where flight_time(QB -> traj[throw_tick+k]) ≈ k*0.1s, so the ball meets the moving
    WR instead of landing behind him. Returns (target_xy, eta)."""
    best = None
    for k in range(0, 36):
        cand = traj[min(throw_tick + k, len(traj) - 1)]
        nb = throw_ball(BallState(x=qb.x, y=qb.y, holder_id="QB"), qb.x, qb.y, cand.x, cand.y,
                        arc, throw_power, target_z=DEFAULT_TARGET_Z)
        if nb is None:
            continue
        err = abs(nb.eta - k * DT)
        if best is None or err < best[0]:
            best = (err, (cand.x, cand.y), nb.eta)
    return (best[1], best[2]) if best else ((traj[throw_tick].x, traj[throw_tick].y), None)


def run_one(route, variant, seed, out_path):
    roster = _load_yaml(ROSTER)
    attrs = {row["id"]: _build_attrs(row) for row in roster["players"]}
    pos = {row["id"]: row.get("position", [26.65, 50.0]) for row in roster["players"]}
    from engine.physics import PlayerState
    wr0 = PlayerState(x=pos["WR1"][0], y=pos["WR1"][1])
    cb = PlayerState(x=pos["CB1"][0], y=pos["CB1"][1])
    qb = PlayerState(x=pos["QB"][0], y=pos["QB"][1])

    timeline = _expand(variant["segments"])
    traj = _wr_trajectory(timeline, wr0, attrs["WR1"], MAX_TICKS + 40)
    throw_tick = variant["throw_tick"]
    target, _eta = _meeting_target(qb, traj, throw_tick, variant["arc"], attrs["QB"].throw_power)

    rng = make_rng(seed)
    cb_agent = CBAgent(model="gpt-5-nano", reasoning_effort="low", provider="openai")
    recorder = Recorder(header={"seed": seed, "scenario": f"cb_test:{route}:{variant['label']}",
                                "roster": ROSTER, "down": 1, "distance": 10})

    # CB pre-snap alignment (the CB's own choice — part of what we test)
    psr = cb_agent.pre_snap(build_cb_pre_snap_observation(cb, attrs["CB1"], wr0))
    print(f"  CB pre-snap -> offset={psr['offset_yards']:.1f}yd side={psr['side']} | {psr.get('reasoning','')}")
    cb = _apply_cb_pre_snap(cb, wr0, psr)

    ball = BallState(x=qb.x, y=qb.y, holder_id="QB")
    phase = PlayPhase.LIVE
    move_history, telemetry = [], {"sep_at_throw": None, "sep_at_catch": None, "detected_cut_t": None}
    cb_intent, intent_decided, ball_total_eta = "play_man", False, None
    prev_wr_hdg = detected_cut_t = cut_candidate_t = cut_candidate_from = None
    vertical_steps, vertical_committed_t = 0, None
    outcome = None

    for step in range(MAX_TICKS):
        t = round(step * DT, 3)
        wr = traj[min(step + 1, len(traj) - 1)]   # WR moves first each tick (mirrors the runner)
        events = []

        if phase == PlayPhase.LIVE:
            # hardcoded throw
            if step == throw_tick:
                nb = throw_ball(ball, qb.x, qb.y, target[0], target[1], variant["arc"],
                                attrs["QB"].throw_power, target_z=DEFAULT_TARGET_Z)
                if nb is None:
                    print(f"  [throw infeasible] {variant['arc']} to {target}")
                else:
                    ball = nb
                    ball_total_eta = ball.eta
                    telemetry["sep_at_throw"] = round(math.hypot(wr.x - cb.x, wr.y - cb.y), 2)
                    d = math.hypot(target[0] - qb.x, target[1] - qb.y)
                    events.append({"type": "THROW", "target": list(target), "arc": variant["arc"],
                                   "eta": round(ball.eta, 2), "dist": round(d, 1)})
                    phase = PlayPhase.BALL_IN_AIR
                    print(f"  t={t:.1f} THROW {variant['arc']} -> {tuple(round(v,1) for v in target)} "
                          f"eta={ball.eta:.2f}s sep@throw={telemetry['sep_at_throw']}")

            if phase == PlayPhase.LIVE and step >= 1:
                obs = build_cb_observation(t, cb, attrs["CB1"], wr, ball, wr_history=move_history,
                                           detected_cut_t=detected_cut_t,
                                           vertical_committed=vertical_committed_t is not None)
                dec = cb_agent.decide_move(obs)
                cb = cb_agent.apply_decision({**dec, "action": "cover"}, cb, attrs["CB1"], wr, DT)
                print(f"  t={t:.1f} CB -> {dec['mode']} tilt={dec.get('tilt',0):.0f} "
                      f"-> hdg={cb.heading:.0f} mode={cb.mode} | {dec.get('reasoning','')}")

        if phase == PlayPhase.BALL_IN_AIR:
            if not intent_decided:
                cb_intent = cb_agent.decide_intent(build_cb_intent_observation(
                    t, cb, attrs["CB1"], wr, ball, ball_total_eta or ball.eta))
                intent_decided = True
            obs = build_cb_observation(t, cb, attrs["CB1"], wr, ball, wr_history=move_history,
                                       ball_total_eta=ball_total_eta, cb_intent=cb_intent,
                                       detected_cut_t=detected_cut_t)
            dec = cb_agent.decide_move(obs)
            cb = cb_agent.apply_decision({**dec, "action": "cover"}, cb, attrs["CB1"], wr, DT,
                                         drive_target=(ball.landing_x, ball.landing_y))
            print(f"  t={t:.1f} CB(air) -> {dec['mode']} tilt={dec.get('tilt',0):.0f} -> hdg={cb.heading:.0f}")
            ball = advance_ball(ball, DT)
            if ball.eta <= 0.0:
                result = resolve(wr, cb, attrs["WR1"], attrs["CB1"], ball.landing_x, ball.landing_y,
                                 cb_intent, rng, qb_x=qb.x, qb_y=qb.y, ball=ball)
                outcome = result["outcome"]
                telemetry["sep_at_catch"] = result.get("separation")
                events.append({"type": "RESOLUTION", **result})
                actions = {"WR1": {"action": "route"}, "CB1": {"action": "cover"}, "QB": {"action": "hold"}}
                recorder.record_step(t, "END", 0.0,
                    [_player_snap(p, {"WR1": wr, "CB1": cb, "QB": qb}[p], actions[p]) for p in ("WR1", "CB1", "QB")],
                    _ball_snap(ball), events)
                print(f"  t={t:.1f} RESOLUTION -> {outcome} sep={result.get('separation','?')}yd")
                break

        # cut detection (mirrors the runner — feeds the CB obs)
        new_hdg = wr.heading
        if detected_cut_t is None:
            if cut_candidate_t is not None:
                snapped = abs(((new_hdg - cut_candidate_from + 180) % 360) - 180) < 20
                if not snapped:
                    detected_cut_t = cut_candidate_t
                cut_candidate_t = cut_candidate_from = None
            if detected_cut_t is None and prev_wr_hdg is not None:
                turned = abs((new_hdg - prev_wr_hdg + 180) % 360 - 180) >= CUT_DETECT_THRESHOLD
                dev_new = abs((new_hdg + 180) % 360 - 180)
                dev_prev = abs((prev_wr_hdg + 180) % 360 - 180)
                if turned and dev_new > dev_prev:
                    cut_candidate_t, cut_candidate_from = t, prev_wr_hdg
        prev_wr_hdg = new_hdg
        if abs((new_hdg + 180) % 360 - 180) <= 20 and wr.speed >= 0.7 * attrs["WR1"].max_speed:
            vertical_steps += 1
        else:
            vertical_steps = 0
        if vertical_committed_t is None and detected_cut_t is None and vertical_steps >= 10:
            vertical_committed_t = t

        sep = math.hypot(wr.x - cb.x, wr.y - cb.y)
        move_history.append({
            "t": t, "wr": [round(wr.x, 1), round(wr.y, 1)], "wr_hdg": round(wr.heading, 1),
            "wr_spd": round(wr.speed, 1), "wr_cut_rec": wr.cut_recovery,
            "cb": [round(cb.x, 1), round(cb.y, 1)], "cb_hdg": round(cb.heading, 1),
            "cb_spd": round(cb.speed, 1), "cb_mode": cb.mode, "cb_cut_rec": cb.cut_recovery,
        })
        actions = {"WR1": {"action": "route"}, "CB1": {"action": "cover"}, "QB": {"action": "hold"}}
        recorder.record_step(t, phase.value, 0.0,
            [_player_snap(p, {"WR1": wr, "CB1": cb, "QB": qb}[p], actions[p]) for p in ("WR1", "CB1", "QB")],
            _ball_snap(ball), events)

    recorder.save(out_path)
    if outcome is None:
        outcome = "NO_THROW_RESOLVED"
    telemetry["detected_cut_t"] = detected_cut_t
    return outcome, telemetry


def main():
    p = argparse.ArgumentParser(description="CB-only test: scripted WR + hardcoded throw.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--routes", nargs="+", choices=list(ROUTE_TESTS), default=None)
    args = p.parse_args()
    routes = args.routes or list(ROUTE_TESTS)
    Path("replays").mkdir(exist_ok=True)

    results = []
    for route in routes:
        for variant in ROUTE_TESTS[route]:
            out = f"replays/cb_{route}_{variant['label']}_{args.seed}.json"
            print(f"\n{'='*64}\nCB TEST: {route} / {variant['label']}  ->  {out}\n{'='*64}")
            try:
                outcome, tel = run_one(route, variant, args.seed, out)
            except Exception as e:
                import traceback; traceback.print_exc()
                outcome, tel = f"ERROR:{e}", {}
            results.append((route, variant["label"], outcome, tel))

    print(f"\n{'='*64}\nSUMMARY\n{'='*64}")
    for route, label, outcome, tel in results:
        print(f"  {route:<10} {label:<12} {outcome:<22} "
              f"sep@throw={tel.get('sep_at_throw')} -> sep@catch={tel.get('sep_at_catch')} "
              f"cut@={tel.get('detected_cut_t')}")


if __name__ == "__main__":
    main()
