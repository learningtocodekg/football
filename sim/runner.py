"""Play runner — freedom branch.

LLM WR + LLM QB + LLM CB. The WR runs free, then "calls for the ball" and locks an end_route; the
engine drives him deterministically until the throw, then he comes alive in the air. The QB is gated
on the call and only picks bullet vs lob (the engine leads him). The CB plays man with full autonomy.
Replay output is unchanged — every player's motion is recorded every 0.1s.
"""
import math
from pathlib import Path

import yaml

from engine.physics import PlayerState, PlayerAttrs
from engine.ball import BallState, throw_ball, advance_ball, DEFAULT_TARGET_Z, YD_S_TO_MPH
from engine.endroute import step_endroute, solve_lead
from engine.resolution import resolve
from engine.state_machine import PlayPhase
from replay.recorder import Recorder
from agents.qb_agent import QBAgent
from agents.cb_agent import CBAgent
from agents.wr_agent import WRAgent
from agents.observation_wr import (
    build_wr_pre_snap_observation, build_wr_node_observation, build_wr_air_observation,
)
from agents.observation_qb import build_qb_observation
from agents.observation_cb import (
    build_cb_pre_snap_observation, build_cb_observation, build_cb_intent_observation,
)
from sim.seeds import make_rng

DT = 0.1
SACK_CLOCK = 5.0
MAX_STEPS = 200
CALL_DELAY_STEPS = 2          # QB hears the WR call 0.2s later
CUT_DETECT_THRESHOLD = 30.0   # WR heading change > this = candidate cut (for CB obs only)


def _load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _build_attrs(row: dict) -> PlayerAttrs:
    skip = {"id", "role", "position"}
    return PlayerAttrs(**{k: v for k, v in row.items() if k not in skip})


def _player_snap(pid: str, s: PlayerState, action: dict) -> dict:
    return {
        "id": pid,
        "pos": [round(s.x, 2), round(s.y, 2)],
        "heading": round(s.heading, 1),
        "facing": round(s.facing, 1),
        "speed": round(s.speed, 2),
        "cut_recovery": s.cut_recovery,
        "mode": s.mode,
        "action": action.get("action", ""),
        "reasoning": action.get("reasoning", ""),
    }


def _ball_snap(ball: BallState) -> dict:
    d: dict = {"state": ball.state,
               "pos": [round(ball.x, 2), round(ball.y, 2), round(ball.z, 2)]}
    if ball.state == "in_air":
        d["landing"] = [round(ball.landing_x, 2), round(ball.landing_y, 2), round(ball.landing_z, 2)]
        d["eta"] = round(ball.eta, 3)
        d["arc"] = ball.arc
    else:
        d["holder"] = ball.holder_id
    return d


def _apply_cb_pre_snap(cb: PlayerState, wr: PlayerState, result: dict) -> PlayerState:
    offset = result["offset_yards"]
    side = result["side"]
    field_center_x = 26.65
    if side == "press":
        new_x = wr.x
    elif side == "inside":
        new_x = wr.x + (0.5 if field_center_x > wr.x else -0.5)
    else:
        new_x = wr.x + (-0.5 if field_center_x > wr.x else 0.5)
    return PlayerState(x=new_x, y=wr.y + offset, speed=0.0, heading=180.0, facing=180.0, mode="normal")


def run_play(scenario_path, roster_path, seed, output_path, scenario_overrides=None):
    scenario = _load_yaml(scenario_path)
    if scenario_overrides:
        scenario.update(scenario_overrides)
    roster = _load_yaml(roster_path)
    rng = make_rng(seed)

    states: dict[str, PlayerState] = {}
    attrs: dict[str, PlayerAttrs] = {}
    for row in roster["players"]:
        pid = row["id"]
        pos = row.get("position", [26.65, 50.0])
        states[pid] = PlayerState(x=pos[0], y=pos[1])
        attrs[pid] = _build_attrs(row)

    ball = BallState(x=states["QB"].x, y=states["QB"].y, holder_id="QB")
    has_cb = "CB1" in states

    model = scenario.get("qb_model", "gpt-5-nano")
    r_effort = scenario.get("qb_reasoning_effort")
    provider = scenario.get("qb_provider", "openai")
    route_name = scenario.get("wr_route", "slant")
    down = scenario.get("down", 1)
    distance = scenario.get("distance", 10)

    qb_agent = QBAgent(model=model, reasoning_effort=r_effort, provider=provider,
                       throw_power=attrs["QB"].throw_power)
    wr_agent = WRAgent(model=scenario.get("wr_model", model),
                       reasoning_effort=scenario.get("wr_reasoning_effort", r_effort),
                       provider=scenario.get("wr_provider", provider), route=route_name)
    cb_agent = CBAgent(model=scenario.get("cb_model", model),
                       reasoning_effort=scenario.get("cb_reasoning_effort", r_effort),
                       provider=scenario.get("cb_provider", provider)) if has_cb else None

    print(f"  [freedom] WR({wr_agent.model}) + QB({qb_agent.model})"
          + (f" + CB({cb_agent.model})" if cb_agent else " (no CB)") + f"  route={route_name}")

    # ── CB pre-snap alignment ────────────────────────────────────────────
    if cb_agent is not None:
        psr = cb_agent.pre_snap(build_cb_pre_snap_observation(states["CB1"], attrs["CB1"], states["WR1"]))
        print(f"  CB pre-snap -> offset={psr['offset_yards']:.1f}yd side={psr['side']}  | {psr.get('reasoning','')}")
        states["CB1"] = _apply_cb_pre_snap(states["CB1"], states["WR1"], psr)

    wr_start = (states["WR1"].x, states["WR1"].y)

    # ── WR authors its conditional plan once, pre-snap (the play's one full-reasoning call) ──
    plan = wr_agent.author_plan(build_wr_pre_snap_observation(
        states["WR1"], attrs["WR1"], states.get("CB1"), route_name, wr_start=wr_start))
    print(f"  WR plan: {plan.get('idea','')}  | start='{plan['start']}' nodes={list(plan['nodes'])}")
    wr_node_id = plan["start"]
    wr_node = plan["nodes"][wr_node_id]
    wr_node_entered_t = 0.0

    recorder = Recorder(header={"seed": seed, "scenario": scenario_path, "roster": roster_path,
                                "down": down, "distance": distance})
    phase = PlayPhase.LIVE
    outcome = None
    move_history: list[dict] = []
    telemetry = {
        "max_separation": 0.0, "sep_at_throw": None, "sep_at_catch": None,
        "throw_t": None, "throw_distance": None, "throw_arc": None, "target_z": None,
        "sack": False, "qb_calls": 0, "qb_parse_errors": 0, "wr_calls": 0,
        "wr_parse_errors": 0, "cb_calls": 0, "cb_parse_errors": 0, "cb_intent": "play_man",
        "wr_call_t": None, "detected_cut_t": None,
    }

    actions = {"QB": {"action": "hold", "reasoning": "pre-snap"},
               "WR1": {"action": "run_route", "reasoning": "route running"}}
    if has_cb:
        actions["CB1"] = {"action": "cover", "reasoning": "pre-snap"}

    commit_step: int | None = None     # step the WR called for the ball
    frozen_sack_clock: float | None = None  # sack clock stops once the ball is thrown
    cb_intent = "play_man"
    intent_decided = False
    ball_total_eta: float | None = None

    prev_wr_hdg: float | None = None
    detected_cut_t: float | None = None
    cut_candidate_t: float | None = None
    cut_candidate_from: float | None = None
    vertical_straight_steps = 0          # consecutive steps the WR has run straight + fast
    vertical_committed_t: float | None = None  # stamped once it reads as a pure vertical (no break)

    for step in range(MAX_STEPS):
        t = round(step * DT, 3)
        events: list[dict] = []
        sack_clock = frozen_sack_clock if frozen_sack_clock is not None \
            else round(max(0.0, SACK_CLOCK - t), 3)

        if has_cb:
            sep = math.hypot(states["WR1"].x - states["CB1"].x, states["WR1"].y - states["CB1"].y)
            telemetry["max_separation"] = max(telemetry["max_separation"], sep)

        # ════════════════════════ LIVE ════════════════════════
        if phase == PlayPhase.LIVE:
            if sack_clock <= 0.0:
                outcome = "SACK"
                telemetry["sack"] = True
                events.append({"type": "SACK"})
                recorder.record_step(t, "END", 0.0,
                    [_player_snap(p, states[p], actions[p]) for p in states], _ball_snap(ball), events)
                break

            committed = wr_agent.called_for_ball

            # ── WR (plan-driven: run the current node's action; wake only at decision points) ──
            if not committed:
                decide_t = wr_node_entered_t + wr_node["hold"]
                if t < decide_t - 1e-9:
                    # Between decision nodes: execute the node's durative action, NO LLM call.
                    act = wr_node["action"]
                    actions["WR1"] = {"heading": act["heading"], "facing": act["heading"],
                                      "throttle": act["effort"], "action": "run_route",
                                      "reasoning": f"[plan {wr_node_id}] {act['effort']} hdg {act['heading']:.0f}"}
                    states["WR1"] = wr_agent.apply_decision(actions["WR1"], states["WR1"], attrs["WR1"], DT)
                else:
                    # Decision node: the WR is alive — evaluate its own read, pick a branch.
                    node_obs = build_wr_node_observation(
                        t, states["WR1"], attrs["WR1"], states.get("CB1"), states["QB"],
                        route_name, wr_node, wr_node_id, history=move_history, wr_start=wr_start)
                    sel = wr_agent.decide_node(node_obs, wr_node)
                    branch = wr_node["branches"][sel["choice"]]
                    print(f"  t={t:.1f} WR @{wr_node_id} -> [{sel['choice']}] '{branch['cond']}' | {sel.get('reasoning','')}")
                    if "call" in branch:
                        er = branch["call"]
                        wr_agent.called_for_ball = True
                        wr_agent.call_t = t
                        wr_agent.end_route = er
                        wr_agent.call_heading = er["heading"]
                        commit_step = step
                        telemetry["wr_call_t"] = t
                        events.append({"type": "WR_CALL", "t": t, "end_route": er})
                        print(f"  t={t:.1f} WR called! end_route={er}")
                        actions["WR1"] = {"heading": er["heading"], "facing": er["heading"],
                                          "throttle": "accelerate", "action": "run_route",
                                          "reasoning": f"[plan call] {branch['cond']}"}
                        states["WR1"] = wr_agent.apply_decision(actions["WR1"], states["WR1"], attrs["WR1"], DT)
                    else:
                        goto = branch.get("goto")
                        if goto in plan["nodes"]:
                            wr_node_id, wr_node = goto, plan["nodes"][goto]
                        wr_node_entered_t = t
                        act = wr_node["action"]
                        actions["WR1"] = {"heading": act["heading"], "facing": act["heading"],
                                          "throttle": act["effort"], "action": "run_route",
                                          "reasoning": f"[plan {wr_node_id}] {act['effort']} hdg {act['heading']:.0f}"}
                        states["WR1"] = wr_agent.apply_decision(actions["WR1"], states["WR1"], attrs["WR1"], DT)
            else:
                progress = step - commit_step
                er = wr_agent.end_route
                states["WR1"] = step_endroute(states["WR1"], attrs["WR1"], er, progress, DT)
                actions["WR1"] = {"action": "run_route",
                                  "reasoning": f"end-route {er['mode']} hdg {er['heading']:.0f} (locked)"}

            # ── QB (gated on the call + 0.2s) ──
            qb_engaged = committed and commit_step is not None and step >= commit_step + CALL_DELAY_STEPS
            if not qb_engaged:
                actions["QB"] = {"action": "hold", "reasoning": "waiting for WR to commit"}
            else:
                progress = step - commit_step
                er = wr_agent.end_route
                lead = {
                    arc: solve_lead(states["QB"].x, states["QB"].y, states["WR1"], attrs["WR1"],
                                    er, progress, arc, attrs["QB"].throw_power, t_now=t)
                    for arc in ("bullet", "lob")
                }
                qb_obs = build_qb_observation(
                    t, sack_clock, states["QB"], attrs["QB"], states["WR1"], attrs["WR1"],
                    states.get("CB1"), attrs.get("CB1"), ball, lead,
                    wr_call_t=wr_agent.call_t, wr_call_heading=wr_agent.call_heading,
                    down=down, distance=distance, history=move_history)
                qb_act = qb_agent.decide(qb_obs)
                actions["QB"] = qb_act
                print(f"  t={t:.1f} QB -> {qb_act['action']!r}"
                      + (f" {qb_act.get('arc','')}" if qb_act['action'] == 'throw' else "")
                      + f" | {qb_act.get('reasoning','')}")
                if qb_act["action"] == "throw":
                    arc = qb_act["arc"]
                    tc = lead[arc]["target"]
                    new_ball = throw_ball(ball, states["QB"].x, states["QB"].y, tc[0], tc[1],
                                          arc, attrs["QB"].throw_power, target_z=DEFAULT_TARGET_Z)
                    if new_ball is None:
                        print(f"  t={t:.1f} [THROW IMPOSSIBLE] {arc} to {tc} — holding")
                        events.append({"type": "THROW_IMPOSSIBLE", "target": tc, "arc": arc})
                        actions["QB"] = {"action": "hold", "reasoning": "throw out of range"}
                    else:
                        ball = new_ball
                        ball_total_eta = ball.eta
                        d = math.hypot(tc[0] - states["QB"].x, tc[1] - states["QB"].y)
                        events.append({"type": "THROW", "target": tc, "arc": arc,
                                       "eta": round(ball.eta, 2), "dist": round(d, 1),
                                       "mph": round(ball.speed_yd_s * YD_S_TO_MPH, 1)})
                        telemetry.update(throw_t=t, throw_distance=round(d, 1), throw_arc=arc,
                                         target_z=round(ball.landing_z, 2))
                        if has_cb:
                            telemetry["sep_at_throw"] = round(math.hypot(
                                states["WR1"].x - states["CB1"].x, states["WR1"].y - states["CB1"].y), 2)
                        phase = PlayPhase.BALL_IN_AIR
                        frozen_sack_clock = sack_clock
                        actions["QB"] = {"action": "hold", "reasoning": "ball in air"}

            # ── CB ── (skip step 0: give the CB one tick of WR movement to read first,
            # so it isn't deciding blind at the snap; it holds its pre-snap stance for 0.1s)
            if cb_agent is not None and step >= 1:
                cb_obs = build_cb_observation(t, states["CB1"], attrs["CB1"], states["WR1"], ball,
                                              wr_history=move_history, ball_total_eta=ball_total_eta,
                                              detected_cut_t=detected_cut_t,
                                              vertical_committed=vertical_committed_t is not None)
                cb_dec = cb_agent.decide_move(cb_obs)
                actions["CB1"] = {**cb_dec, "action": "cover"}
                states["CB1"] = cb_agent.apply_decision(actions["CB1"], states["CB1"], attrs["CB1"],
                                                        states["WR1"], DT)
                print(f"  t={t:.1f} CB -> {cb_dec['mode']} tilt={cb_dec.get('tilt',0):.0f} "
                      f"-> hdg={states['CB1'].heading:.0f} | {cb_dec.get('reasoning','')}")

        # ════════════════════════ BALL IN AIR ════════════════════════
        elif phase == PlayPhase.BALL_IN_AIR:
            if cb_agent is not None and not intent_decided:
                cb_intent = cb_agent.decide_intent(build_cb_intent_observation(
                    t, states["CB1"], attrs["CB1"], states["WR1"], ball, ball_total_eta or ball.eta))
                intent_decided = True
                telemetry["cb_intent"] = cb_intent

            if cb_agent is not None:
                cb_obs = build_cb_observation(t, states["CB1"], attrs["CB1"], states["WR1"], ball,
                                              wr_history=move_history, ball_total_eta=ball_total_eta,
                                              cb_intent=cb_intent, detected_cut_t=detected_cut_t)
                cb_dec = cb_agent.decide_move(cb_obs)
                actions["CB1"] = {**cb_dec, "action": "cover"}
                states["CB1"] = cb_agent.apply_decision(
                    actions["CB1"], states["CB1"], attrs["CB1"], states["WR1"], DT,
                    drive_target=(ball.landing_x, ball.landing_y))

            # WR alive — adjust to the ball, clamped against overshoot
            wr_obs = build_wr_air_observation(t, states["WR1"], attrs["WR1"], states.get("CB1"),
                                              states["QB"], ball, ball_total_eta=ball_total_eta)
            wr_dec = wr_agent.decide_air(wr_obs)
            actions["WR1"] = {**wr_dec, "action": "run_route", "throttle": "accelerate"}
            wr_old = states["WR1"]
            new_wr = wr_agent.apply_decision(actions["WR1"], wr_old, attrs["WR1"], DT)
            d_old = math.hypot(wr_old.x - ball.landing_x, wr_old.y - ball.landing_y)
            d_new = math.hypot(new_wr.x - ball.landing_x, new_wr.y - ball.landing_y)
            if d_new > d_old:
                new_wr.x, new_wr.y, new_wr.speed = wr_old.x, wr_old.y, 0.0
            states["WR1"] = new_wr
            print(f"  t={t:.1f} WR(air) -> hdg={wr_dec['heading']:.0f} | {wr_dec.get('reasoning','')}")

            ball = advance_ball(ball, DT)
            if ball.eta <= 0.0:
                result = resolve(states["WR1"], states.get("CB1"), attrs["WR1"], attrs.get("CB1"),
                                 ball.landing_x, ball.landing_y, cb_intent, rng,
                                 qb_x=states["QB"].x, qb_y=states["QB"].y, ball=ball)
                outcome = result["outcome"]
                telemetry["sep_at_catch"] = result.get("separation")
                events.append({"type": "RESOLUTION", **result})
                recorder.record_step(t, "END", sack_clock,
                    [_player_snap(p, states[p], actions[p]) for p in states], _ball_snap(ball), events)
                print(f"\n  t={t:.1f} RESOLUTION -> {outcome}  sep={result.get('separation','?')}yd  z={result.get('landing_z','?')}")
                break

        # ── cut detection (for CB observation only) ──
        new_hdg = states["WR1"].heading
        if detected_cut_t is None:
            if cut_candidate_t is not None:
                snapped = abs(((new_hdg - cut_candidate_from + 180) % 360) - 180) < 20
                if not snapped:
                    detected_cut_t = cut_candidate_t
                    telemetry["detected_cut_t"] = cut_candidate_t
                cut_candidate_t = cut_candidate_from = None
            if detected_cut_t is None and prev_wr_hdg is not None:
                turned = abs((new_hdg - prev_wr_hdg + 180) % 360 - 180) >= CUT_DETECT_THRESHOLD
                # A cut is a deviation AWAY from the upfield stem (0°). Returning toward upfield —
                # e.g. snapping back from an inside fake — is not a cut; flagging it makes the fake's
                # own return register as a phantom "cut to vertical" and lies to the CB.
                dev_new = abs((new_hdg + 180) % 360 - 180)
                dev_prev = abs((prev_wr_hdg + 180) % 360 - 180)
                if turned and dev_new > dev_prev:
                    cut_candidate_t = t
                    cut_candidate_from = prev_wr_hdg
        prev_wr_hdg = new_hdg

        # Vertical-commit detection: a long straight + fast run with no cut = a foot race with no
        # break to guard. Stamped once and injected into the CB obs so the (stateless) CB stops
        # re-deriving "maybe he'll break" every tick and commits to the run.
        if abs((new_hdg + 180) % 360 - 180) <= 20 and states["WR1"].speed >= 0.7 * attrs["WR1"].max_speed:
            vertical_straight_steps += 1
        else:
            vertical_straight_steps = 0
        if vertical_committed_t is None and detected_cut_t is None and vertical_straight_steps >= 10:
            vertical_committed_t = t

        move_history.append({
            "t": t,
            "wr": [round(states["WR1"].x, 1), round(states["WR1"].y, 1)],
            "wr_hdg": round(states["WR1"].heading, 1),
            "wr_spd": round(states["WR1"].speed, 1),
            "wr_cut_rec": states["WR1"].cut_recovery,
            "cb": [round(states["CB1"].x, 1), round(states["CB1"].y, 1)] if has_cb else [0.0, 0.0],
            "cb_hdg": round(states["CB1"].heading, 1) if has_cb else 0.0,
            "cb_spd": round(states["CB1"].speed, 1) if has_cb else 0.0,
            "cb_mode": states["CB1"].mode if has_cb else "",
            "cb_cut_rec": states["CB1"].cut_recovery if has_cb else 0,
        })
        recorder.record_step(t, phase.value, sack_clock,
            [_player_snap(p, states[p], actions[p]) for p in states], _ball_snap(ball), events)

    if outcome is None:
        outcome = "TIMEOUT"

    telemetry["max_separation"] = round(telemetry["max_separation"], 2)
    telemetry["qb_calls"] = qb_agent.call_count
    telemetry["qb_parse_errors"] = qb_agent.parse_errors
    telemetry["wr_calls"] = wr_agent.call_count
    telemetry["wr_parse_errors"] = wr_agent.parse_errors
    if cb_agent is not None:
        telemetry["cb_calls"] = cb_agent.call_count
        telemetry["cb_parse_errors"] = cb_agent.parse_errors

    recorder.record_footer(outcome, telemetry)
    recorder.save(output_path)
    print(f"\n{'='*50}\nOUTCOME : {outcome}\nTelemetry: {telemetry}")
    return outcome, telemetry
