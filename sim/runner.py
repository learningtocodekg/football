"""
Play runner — supports A2 (LLM QB + LLM CB + scripted WR)
                      and A3 (LLM QB + LLM WR, no CB).
"""
import math
from pathlib import Path

import yaml

from engine.physics import PlayerState, PlayerAttrs, apply_action, angle_diff
from engine.ball import BallState, throw_ball, advance_ball
from engine.resolution import resolve
from engine.state_machine import PlayPhase
from replay.recorder import Recorder
from agents.qb_agent import QBAgent
from agents.cb_agent import CBAgent
from agents.wr_agent import WRAgent
from agents.scripted import ScriptedWR, ScriptedQB, ROUTES, ROUTE_META
from agents.observation import (
    build_qb_observation,
    build_cb_pre_snap_observation,
    build_cb_observation,
    build_cb_intent_observation,
    build_wr_pre_snap_observation,
    build_wr_observation,
    FIELD_WIDTH,
    OOB_WARN_DIST,
)
from sim.seeds import make_rng

DT = 0.1           # seconds per timestep
SACK_CLOCK = 5.0   # seconds QB has before sack
MAX_STEPS = 200    # safety cap (~20 s)

MIN_BALL_MPH = 20.0
MAX_BALL_MPH = 60.0

# WR heading change > this in one step → detected cut
CUT_DETECT_THRESHOLD = 30.0

# WR within this many yards of sideline AND heading toward it → broken play
OOB_TRIGGER_DIST = 2.0


def _load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _build_attrs(row: dict) -> PlayerAttrs:
    skip = {"id", "role", "position"}
    return PlayerAttrs(**{k: v for k, v in row.items() if k not in skip})


def _player_snap(pid: str, state: PlayerState, action: dict) -> dict:
    return {
        "id": pid,
        "pos": [round(state.x, 2), round(state.y, 2)],
        "heading": round(state.heading, 1),
        "facing": round(state.facing, 1),
        "speed": round(state.speed, 2),
        "mode": state.mode,
        "action": action.get("action", ""),
        "reasoning": action.get("reasoning", ""),
    }


def _ball_snap(ball: BallState) -> dict:
    d: dict = {"state": ball.state, "pos": [round(ball.x, 2), round(ball.y, 2)]}
    if ball.state == "in_air":
        d["landing"] = [round(ball.landing_x, 2), round(ball.landing_y, 2)]
        d["eta"] = round(ball.eta, 3)
    else:
        d["holder"] = ball.holder_id
    return d


def _apply_cb_pre_snap(cb_state: PlayerState, wr_state: PlayerState, result: dict) -> PlayerState:
    offset = result["offset_yards"]
    side = result["side"]
    field_center_x = 26.65
    if side == "press":
        new_x = wr_state.x
    elif side == "inside":
        toward_center = 1.0 if field_center_x > wr_state.x else -1.0
        new_x = wr_state.x + toward_center * 0.5
    else:
        away_from_center = -1.0 if field_center_x > wr_state.x else 1.0
        new_x = wr_state.x + away_from_center * 0.5
    new_y = wr_state.y + offset
    return PlayerState(x=new_x, y=new_y, speed=0.0, heading=180.0, facing=180.0, mode="normal")


def _heading_toward_sideline(wr: PlayerState) -> bool:
    """True if WR is within OOB_TRIGGER_DIST of a sideline AND heading toward it."""
    hdg_rad = math.radians(wr.heading)
    dx = math.sin(hdg_rad)  # positive = moving right
    near_left = wr.x < OOB_TRIGGER_DIST and dx < -0.1
    near_right = (FIELD_WIDTH - wr.x) < OOB_TRIGGER_DIST and dx > 0.1
    return near_left or near_right


def _detect_cut(prev_heading: float | None, new_heading: float) -> bool:
    if prev_heading is None:
        return False
    diff = abs((new_heading - prev_heading + 180.0) % 360.0 - 180.0)
    return diff >= CUT_DETECT_THRESHOLD


def run_play(
    scenario_path: str,
    roster_path: str,
    seed: int,
    output_path: str,
    scenario_overrides: dict | None = None,
) -> tuple[str, dict]:
    scenario = _load_yaml(scenario_path)
    if scenario_overrides:
        scenario.update(scenario_overrides)
    roster = _load_yaml(roster_path)
    rng = make_rng(seed)

    # ── Build player states & attrs ─────────────────────────────────────
    states: dict[str, PlayerState] = {}
    attrs: dict[str, PlayerAttrs] = {}
    for row in roster["players"]:
        pid = row["id"]
        pos = row.get("position", [26.65, 50.0])
        states[pid] = PlayerState(x=pos[0], y=pos[1])
        attrs[pid] = _build_attrs(row)

    ball = BallState(x=states["QB"].x, y=states["QB"].y, holder_id="QB")

    # ── Mode flags ───────────────────────────────────────────────────────
    # a3_mode: LLM WR + LLM QB, no CB (isolated WR dev)
    # a4_mode: LLM WR + LLM QB + LLM CB (full field)
    # default (neither): scripted WR, LLM CB (A2)
    a3_mode = scenario.get("a3_mode", False)
    a4_mode = scenario.get("a4_mode", False)
    llm_wr = a3_mode or a4_mode
    llm_cb = a4_mode or (not a3_mode)

    # ── Agents ───────────────────────────────────────────────────────────
    model = scenario.get("qb_model", "gpt-5-nano")
    r_effort = scenario.get("qb_reasoning_effort")
    provider = scenario.get("qb_provider", "openai")

    qb_throw_power = next(
        (r["throw_power"] for r in roster["players"] if r["id"] == "QB"), 85.0
    )
    qb_max_mph = MIN_BALL_MPH + (qb_throw_power / 99.0) * (MAX_BALL_MPH - MIN_BALL_MPH)

    if scenario.get("qb_scripted"):
        qb_agent = ScriptedQB(
            throw_t=float(scenario.get("qb_throw_t", 2.3)),
            ball_speed_mph=float(scenario.get("qb_throw_mph", 45.0)),
        )
        print(f"  [ScriptedQB] throw at t={qb_agent.throw_t}s @ {qb_agent.ball_speed_mph}mph")
    else:
        qb_agent = QBAgent(model=model, reasoning_effort=r_effort, provider=provider,
                           min_mph=MIN_BALL_MPH, max_mph=qb_max_mph)

    route_name = scenario.get("wr_route", "slant")
    route_phases = ROUTES.get(route_name, ROUTES["slant"])
    # For multi-phase routes, cut_time = time of the LAST real cut; cut_heading = final heading.
    if len(route_phases) >= 2:
        cut_time = route_phases[-2][0]
        cut_heading = route_phases[-1][1]
    else:
        cut_time = 999.0    # go route — no cut
        cut_heading = route_phases[0][1]
    upfield_yards = cut_time * 5.0 if cut_time < 9.0 else 10.0

    route_meta = ROUTE_META.get(route_name, {})
    call_tolerance = route_meta.get("call_tolerance", 45.0)
    multi_phase = len(route_phases) >= 3

    if llm_wr:
        wr_model = scenario.get("wr_model", model)
        wr_r_effort = scenario.get("wr_reasoning_effort", r_effort)
        wr_provider = scenario.get("wr_provider", provider)
        wr_agent = WRAgent(
            model=wr_model, reasoning_effort=wr_r_effort, provider=wr_provider,
            route=route_name, cut_time=cut_time, cut_heading=cut_heading,
            upfield_yards=upfield_yards, call_tolerance=call_tolerance,
        )
    else:
        wr_agent = ScriptedWR(route=route_name)

    if llm_cb and not a3_mode:
        cb_model = scenario.get("cb_model", model)
        cb_r_effort = scenario.get("cb_reasoning_effort", r_effort)
        cb_provider = scenario.get("cb_provider", provider)
        cb_agent = CBAgent(model=cb_model, reasoning_effort=cb_r_effort, provider=cb_provider)
    else:
        cb_agent = None

    if a4_mode:
        print(f"  [A4 mode] LLM WR ({wr_agent.model}) + LLM QB + LLM CB ({cb_agent.model})")
    elif a3_mode:
        print(f"  [A3 mode] LLM WR ({wr_agent.model}) + LLM QB — no CB")
    else:
        print(f"  [A2 mode] scripted WR + LLM QB + LLM CB ({cb_agent.model})")

    # ScriptedQB needs WR agent for look-ahead simulation
    if isinstance(qb_agent, ScriptedQB):
        if isinstance(wr_agent, ScriptedWR):
            qb_agent.wr_agent = wr_agent
            qb_agent.wr_attrs = attrs["WR1"]
        # ScriptedQB + LLM WR: ScriptedQB falls back to current WR position (no look-ahead)

    down = scenario.get("down", 1)
    distance = scenario.get("distance", 10)
    expected_open_t = scenario.get("expected_open_t", cut_time + 0.3)

    # ── CB pre-snap (A2 + A4) ───────────────────────────────────────────
    if cb_agent is not None and "CB1" in states:
        pre_snap_obs = build_cb_pre_snap_observation(states["CB1"], attrs["CB1"], states["WR1"])
        pre_snap_result = cb_agent.pre_snap(pre_snap_obs)
        r = pre_snap_result.get("reasoning", "").encode("ascii", "replace").decode("ascii")
        print(f"  CB pre-snap -> offset={pre_snap_result['offset_yards']:.1f}yd  side={pre_snap_result['side']}  | {r}")
        states["CB1"] = _apply_cb_pre_snap(states["CB1"], states["WR1"], pre_snap_result)

    # ── WR pre-snap ──────────────────────────────────────────────────────
    if isinstance(wr_agent, WRAgent):
        cb_state_for_wr = states.get("CB1")
        wr_pre_obs = build_wr_pre_snap_observation(
            states["WR1"], attrs["WR1"], cb_state_for_wr,
            route_name, cut_time, cut_heading, upfield_yards,
            route_phases=route_phases if multi_phase else None,
        )
        wr_pre_result = wr_agent.pre_snap(wr_pre_obs)
        r = wr_pre_result.get("reasoning", "").encode("ascii", "replace").decode("ascii")
        plan = wr_pre_result['plan'][:80].encode("ascii", "replace").decode("ascii")
        print(f"  WR pre-snap plan: {plan}  | {r}")

    recorder = Recorder(header={"seed": seed, "scenario": scenario_path, "roster": roster_path,
                                "down": down, "distance": distance})

    phase = PlayPhase.LIVE
    outcome: str | None = None
    move_history: list[dict] = []
    telemetry: dict = {
        "max_separation": 0.0,
        "throw_t": None,
        "throw_distance": None,
        "sack": False,
        "qb_calls": 0,
        "qb_parse_errors": 0,
        "wr_calls": 0,
        "wr_parse_errors": 0,
        "cb_calls": 0,
        "cb_parse_errors": 0,
        "cb_intent": "play_man",
        "wr_call_t": None,
        "broken_play": False,
        "detected_cut_t": None,
    }

    actions: dict[str, dict] = {
        "QB": {"action": "hold", "reasoning": "pre-snap"},
        "WR1": {"action": "run_route", "reasoning": "route running"},
    }
    if "CB1" in states:
        actions["CB1"] = {"action": "cover", "reasoning": "pre-snap alignment done"}

    sack_clock = SACK_CLOCK
    ball_total_eta: float | None = None
    cb_intent: str = "play_man"
    intent_decided: bool = False

    # WR call-for-ball state (delayed one step to QB)
    wr_call_pending: bool = False     # WR just called this step — QB sees it next step
    wr_call_visible: bool = False     # QB can see the call
    wr_call_t_pending: float | None = None
    wr_call_heading_pending: float | None = None

    prev_wr_heading: float | None = None
    detected_cut_t: float | None = None
    cut_candidate_t: float | None = None       # N1: heading changed last step — awaiting confirmation
    cut_candidate_from_hdg: float | None = None  # heading before the candidate change

    for step in range(MAX_STEPS):
        t = round(step * DT, 3)
        events: list[dict] = []
        sack_clock = round(max(0.0, SACK_CLOCK - t), 3)

        ball_in_air = (phase == PlayPhase.BALL_IN_AIR)

        # ── Promote pending WR call to visible (one step delay) ──────────
        if wr_call_pending:
            wr_call_visible = True
            wr_call_pending = False

        # ── OOB check (before WR decision) ──────────────────────────────
        if isinstance(wr_agent, WRAgent) and not wr_agent.broken_play and not ball_in_air:
            if _heading_toward_sideline(states["WR1"]):
                wr_agent.trigger_broken_play()
                telemetry["broken_play"] = True
                events.append({"type": "BROKEN_PLAY", "reason": "heading_out_of_bounds"})

        # ── WR separation tracking ───────────────────────────────────────
        if "CB1" in states:
            sep = math.hypot(states["WR1"].x - states["CB1"].x,
                             states["WR1"].y - states["CB1"].y)
            telemetry["max_separation"] = max(telemetry["max_separation"], sep)

        # ── LIVE phase ───────────────────────────────────────────────────
        if phase == PlayPhase.LIVE:
            if sack_clock <= 0.0:
                outcome = "SACK"
                events.append({"type": "SACK", "reason": "clock_expired"})
                recorder.record_step(t, "END", 0.0,
                    [_player_snap(p, states[p], actions[p]) for p in states],
                    _ball_snap(ball), events)
                break

            # ── WR decision ──────────────────────────────────────────────
            if isinstance(wr_agent, WRAgent):
                cb_state = states.get("CB1")
                wr_obs = build_wr_observation(
                    t, states["WR1"], attrs["WR1"], cb_state, states["QB"],
                    ball, route_name, cut_time, cut_heading,
                    wr_agent.called_for_ball, wr_agent.call_t, wr_agent.broken_play,
                    wr_history=move_history, ball_total_eta=ball_total_eta,
                    detected_cut_t=detected_cut_t,
                    route_phases=route_phases if multi_phase else None,
                )
                wr_decision = wr_agent.decide(wr_obs, ball_in_air=False, t=t)
                r = wr_decision.get("reasoning", "").encode("ascii", "replace").decode("ascii")
                call_flag = " [CALL FOR BALL]" if wr_decision.get("call_for_ball") else ""
                print(f"  t={t:.1f}  WR move   -> hdg={wr_decision['heading']:.0f}° "
                      f"facing={wr_decision['facing']:.0f}° throttle={wr_decision['throttle']}"
                      f"{call_flag}  | {r}")
                actions["WR1"] = {**wr_decision, "action": "run_route"}

                # Handle call for ball — only on the step it first happens
                if wr_decision.get("call_for_ball") and not wr_call_visible and not wr_call_pending:
                    wr_call_pending = True
                    wr_call_t_pending = wr_agent.call_t
                    wr_call_heading_pending = wr_agent.call_heading
                    telemetry["wr_call_t"] = wr_agent.call_t
                    events.append({"type": "WR_CALL_FOR_BALL", "t": wr_agent.call_t, "heading": wr_agent.call_heading})
                    print(f"  t={t:.1f}  WR called for the ball! heading={wr_agent.call_heading:.0f}°")

            # ── QB decision ──────────────────────────────────────────────
            if t < 0.5:
                actions["QB"] = {"action": "hold", "reasoning": "route developing"}
                print(f"  t={t:.1f}  QB -> 'hold'    | route developing")
            else:
                cb_state = states.get("CB1")
                cb_attrs_val = attrs.get("CB1")
                obs = build_qb_observation(
                    t, sack_clock,
                    states["QB"], attrs["QB"],
                    states["WR1"], attrs["WR1"],
                    cb_state, cb_attrs_val,
                    ball,
                    down=down, distance=distance,
                    history=move_history,
                    expected_open_t=expected_open_t,
                    route_phases=route_phases,
                    wr_called_for_ball=wr_call_visible,
                    wr_call_t=wr_call_t_pending,
                    wr_call_heading=wr_call_heading_pending,
                    broken_play=wr_agent.broken_play if isinstance(wr_agent, WRAgent) else False,
                    detected_cut_t=detected_cut_t,
                )
                if isinstance(qb_agent, ScriptedQB):
                    qb_action = qb_agent.decide(
                        obs, states["QB"].x, states["QB"].y,
                        wr_x=states["WR1"].x, wr_y=states["WR1"].y,
                        wr_heading=states["WR1"].heading, wr_speed=states["WR1"].speed,
                        t=t,
                    )
                else:
                    qb_action = qb_agent.decide(
                        obs, states["QB"].x, states["QB"].y,
                        wr_x=states["WR1"].x, wr_y=states["WR1"].y,
                        wr_heading=states["WR1"].heading, wr_speed=states["WR1"].speed,
                    )
                actions["QB"] = qb_action
                p1 = qb_action.get("pass1")
                if p1 and p1["action"] == "thinking":
                    r = p1["reasoning"].encode("ascii", "replace").decode("ascii")
                    print(f"  t={t:.1f}  QB pass1  -> thinking target={p1['target_area']} | {r}")
                r = qb_action["reasoning"].encode("ascii", "replace").decode("ascii")
                print(f"  t={t:.1f}  QB pass2  -> {qb_action['action']!r:8}  | {r}")

                if qb_action["action"] == "throw":
                    tc = qb_action["target_coord"]
                    mph = qb_action["ball_speed_mph"]
                    max_mph = MIN_BALL_MPH + (attrs["QB"].throw_power / 99.0) * (MAX_BALL_MPH - MIN_BALL_MPH)
                    mph = max(MIN_BALL_MPH, min(max_mph, mph))
                    ball = throw_ball(ball, states["QB"].x, states["QB"].y, tc[0], tc[1], mph)
                    ball_total_eta = ball.eta
                    dist = math.hypot(tc[0] - states["QB"].x, tc[1] - states["QB"].y)
                    events.append({"type": "THROW", "target": tc, "mph": round(mph, 1),
                                   "eta": round(ball.eta, 2), "dist": round(dist, 1)})
                    telemetry["throw_t"] = t
                    telemetry["throw_distance"] = round(dist, 1)
                    phase = PlayPhase.BALL_IN_AIR

            # ── CB movement (A2 mode) ────────────────────────────────────
            if cb_agent is not None and "CB1" in states and t >= 0.3:
                cb_obs = build_cb_observation(
                    t, states["CB1"], attrs["CB1"], states["WR1"], ball,
                    wr_history=move_history, ball_total_eta=ball_total_eta,
                )
                cb_move = cb_agent.decide_movement(cb_obs)
                r = cb_move.get("reasoning", "").encode("ascii", "replace").decode("ascii")
                print(f"  t={t:.1f}  CB move   -> hdg={cb_move['heading']:.0f}° facing={cb_move['facing']:.0f}° mode={cb_move['mode']}  | {r}")
                actions["CB1"] = {**cb_move, "action": "cover"}

        # ── BALL_IN_AIR phase ────────────────────────────────────────────
        elif phase == PlayPhase.BALL_IN_AIR:
            # CB intent (A2 mode)
            if cb_agent is not None and "CB1" in states and not intent_decided:
                intent_obs = build_cb_intent_observation(
                    t, states["CB1"], attrs["CB1"], states["WR1"], ball,
                    ball_total_eta or ball.eta, cb_intent,
                )
                cb_intent = cb_agent.decide_intent(intent_obs)
                intent_decided = True
                telemetry["cb_intent"] = cb_intent

            # CB movement (A2 mode)
            if cb_agent is not None and "CB1" in states:
                cb_obs = build_cb_observation(
                    t, states["CB1"], attrs["CB1"], states["WR1"], ball,
                    wr_history=move_history, ball_total_eta=ball_total_eta,
                    cb_intent=cb_intent,
                )
                cb_move = cb_agent.decide_movement(cb_obs)
                r = cb_move.get("reasoning", "").encode("ascii", "replace").decode("ascii")
                print(f"  t={t:.1f}  CB move   -> hdg={cb_move['heading']:.0f}° facing={cb_move['facing']:.0f}° mode={cb_move['mode']}  | {r}")
                actions["CB1"] = {**cb_move, "action": "cover"}

            # WR movement in air — free to adjust heading
            if isinstance(wr_agent, WRAgent):
                cb_state = states.get("CB1")
                wr_obs = build_wr_observation(
                    t, states["WR1"], attrs["WR1"], cb_state, states["QB"],
                    ball, route_name, cut_time, cut_heading,
                    wr_agent.called_for_ball, wr_agent.call_t, wr_agent.broken_play,
                    wr_history=move_history, ball_total_eta=ball_total_eta,
                    detected_cut_t=detected_cut_t,
                    route_phases=route_phases if multi_phase else None,
                )
                wr_decision = wr_agent.decide(wr_obs, ball_in_air=True, t=t)
                r = wr_decision.get("reasoning", "").encode("ascii", "replace").decode("ascii")
                print(f"  t={t:.1f}  WR (air)  -> hdg={wr_decision['heading']:.0f}° facing={wr_decision['facing']:.0f}° throttle={wr_decision['throttle']}  | {r}")
                actions["WR1"] = {**wr_decision, "action": "run_route"}

            ball = advance_ball(ball, DT)
            if ball.eta <= 0.0:
                cb_state = states.get("CB1")
                cb_attrs_val = attrs.get("CB1")
                result = resolve(
                    states["WR1"], cb_state,
                    attrs["WR1"], cb_attrs_val,
                    ball.landing_x, ball.landing_y,
                    cb_intent,
                    rng,
                    qb_x=states["QB"].x,
                    qb_y=states["QB"].y,
                )
                outcome = result["outcome"]
                events.append({"type": "RESOLUTION", **result})
                recorder.record_step(t, "END", sack_clock,
                    [_player_snap(p, states[p], actions[p]) for p in states],
                    _ball_snap(ball), events)
                print(f"\n  t={t:.1f}  RESOLUTION -> {outcome}  sep={result.get('separation', '?')}yd")
                break

        # ── Move all players ─────────────────────────────────────────────
        if isinstance(wr_agent, WRAgent):
            wr_decision_this_step = actions.get("WR1", {})
            states["WR1"] = wr_agent.apply_decision(
                wr_decision_this_step, states["WR1"], attrs["WR1"], DT,
                ball_in_air=ball_in_air,
            )
        else:
            states["WR1"] = wr_agent.move(t, states["WR1"], attrs["WR1"], DT)

        # Detect WR cut via 2-step heading persistence:
        # A jab snaps back in 1 step; a real cut holds for 2+ steps.
        new_wr_hdg = states["WR1"].heading
        if detected_cut_t is None:
            if cut_candidate_t is not None:
                snapped_back = abs(((new_wr_hdg - cut_candidate_from_hdg + 180) % 360) - 180) < 20
                if not snapped_back:
                    detected_cut_t = cut_candidate_t
                    telemetry["detected_cut_t"] = cut_candidate_t
                    print(f"  t={cut_candidate_t:.1f}  [WR cut confirmed] heading held at {new_wr_hdg:.0f}°")
                cut_candidate_t = None
                cut_candidate_from_hdg = None
            if detected_cut_t is None and prev_wr_heading is not None:
                diff = abs((new_wr_hdg - prev_wr_heading + 180) % 360 - 180)
                if diff >= CUT_DETECT_THRESHOLD:
                    cut_candidate_t = t
                    cut_candidate_from_hdg = prev_wr_heading
        prev_wr_heading = new_wr_hdg

        # CB movement (A2 mode)
        if cb_agent is not None and "CB1" in states and "heading" in actions.get("CB1", {}):
            states["CB1"] = cb_agent.apply_decision(actions["CB1"], states["CB1"], attrs["CB1"], DT)

        move_history.append({
            "t": t,
            "wr": [round(states["WR1"].x, 1), round(states["WR1"].y, 1)],
            "wr_hdg": round(states["WR1"].heading, 1),
            "wr_spd": round(states["WR1"].speed, 1),
            "wr_throttle": actions.get("WR1", {}).get("throttle", ""),
            "cb": [round(states["CB1"].x, 1), round(states["CB1"].y, 1)] if "CB1" in states else [0.0, 0.0],
            "cb_hdg": round(states["CB1"].heading, 1) if "CB1" in states else 0.0,
            "cb_mode": states["CB1"].mode if "CB1" in states else "",
        })

        recorder.record_step(
            t, phase.value, sack_clock,
            [_player_snap(p, states[p], actions[p]) for p in states],
            _ball_snap(ball),
            events,
        )

    if outcome is None:
        outcome = "TIMEOUT"

    telemetry["max_separation"] = round(telemetry["max_separation"], 2)
    telemetry["qb_calls"] = qb_agent.call_count
    telemetry["qb_parse_errors"] = qb_agent.parse_errors
    if isinstance(wr_agent, WRAgent):
        telemetry["wr_calls"] = wr_agent.call_count
        telemetry["wr_parse_errors"] = wr_agent.parse_errors
    if cb_agent is not None:
        telemetry["cb_calls"] = cb_agent.call_count
        telemetry["cb_parse_errors"] = cb_agent.parse_errors

    recorder.record_footer(outcome, telemetry)
    recorder.save(output_path)

    print(f"\n{'='*50}")
    print(f"OUTCOME : {outcome}")
    print(f"Telemetry: {telemetry}")
    return outcome, telemetry
