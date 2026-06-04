"""
Phase A2 play runner.
QB = LLM agent. CB = LLM agent. WR = scripted.
"""
import math
from pathlib import Path

import yaml

from engine.physics import PlayerState, PlayerAttrs, apply_action
from engine.ball import BallState, throw_ball, advance_ball
from engine.resolution import resolve
from engine.state_machine import PlayPhase
from replay.recorder import Recorder
from agents.qb_agent import QBAgent
from agents.cb_agent import CBAgent
from agents.scripted import ScriptedWR, ScriptedQB
from agents.observation import (
    build_qb_observation,
    build_cb_pre_snap_observation,
    build_cb_observation,
    build_cb_intent_observation,
)
from sim.seeds import make_rng

DT = 0.1           # seconds per timestep
SACK_CLOCK = 5.0   # seconds QB has before sack
MAX_STEPS = 200    # safety cap (~20 s)

MIN_BALL_MPH = 20.0
MAX_BALL_MPH = 60.0


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
    """Shift CB starting position based on pre-snap alignment decision."""
    offset = result["offset_yards"]
    side = result["side"]

    # WR is typically running upfield (+y). "Inside" = toward field center (x=26.65), "outside" = away.
    field_center_x = 26.65
    if side == "press":
        # Line up directly on WR, no horizontal offset
        new_x = wr_state.x
    elif side == "inside":
        # Shade between WR and field center
        toward_center = 1.0 if field_center_x > wr_state.x else -1.0
        new_x = wr_state.x + toward_center * 0.5
    else:  # outside
        away_from_center = -1.0 if field_center_x > wr_state.x else 1.0
        new_x = wr_state.x + away_from_center * 0.5

    # Place CB offset_yards upfield from WR (CB lines up downfield of WR at snap)
    new_y = wr_state.y + offset

    return PlayerState(x=new_x, y=new_y, speed=0.0, heading=180.0, facing=180.0, mode="normal")


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

    # ── Agents ───────────────────────────────────────────────────────────
    model = scenario.get("qb_model", "gpt-5-nano")
    r_effort = scenario.get("qb_reasoning_effort")
    provider = scenario.get("qb_provider", "openai")
    cb_model = scenario.get("cb_model", model)
    cb_r_effort = scenario.get("cb_reasoning_effort", r_effort)
    cb_provider = scenario.get("cb_provider", provider)

    qb_throw_power = next(
        (r["throw_power"] for r in roster["players"] if r["id"] == "QB"), 85.0
    )
    qb_max_mph = MIN_BALL_MPH + (qb_throw_power / 99.0) * (MAX_BALL_MPH - MIN_BALL_MPH)

    if scenario.get("qb_scripted"):
        qb_agent = ScriptedQB(
            throw_t=float(scenario.get("qb_throw_t", 2.3)),
            ball_speed_mph=float(scenario.get("qb_throw_mph", 45.0)),
        )
        print(f"  [ScriptedQB] will throw at t={qb_agent.throw_t}s @ {qb_agent.ball_speed_mph}mph (leads WR at throw time)")
    else:
        qb_agent = QBAgent(model=model, reasoning_effort=r_effort, provider=provider,
                           min_mph=MIN_BALL_MPH, max_mph=qb_max_mph)
    wr_agent = ScriptedWR(route=scenario.get("wr_route", "slant"))
    cb_agent = CBAgent(model=cb_model, reasoning_effort=cb_r_effort, provider=cb_provider)

    # Give ScriptedQB access to the WR's route so it can simulate forward exactly
    if isinstance(qb_agent, ScriptedQB):
        qb_agent.wr_agent = wr_agent
        qb_agent.wr_attrs = attrs["WR1"]

    down = scenario.get("down", 1)
    distance = scenario.get("distance", 10)
    expected_open_t = scenario.get("expected_open_t")
    route_phases = wr_agent._phases

    # ── CB pre-snap alignment ────────────────────────────────────────────
    pre_snap_obs = build_cb_pre_snap_observation(states["CB1"], attrs["CB1"], states["WR1"])
    pre_snap_result = cb_agent.pre_snap(pre_snap_obs)
    r = pre_snap_result.get("reasoning", "").encode("ascii", "replace").decode("ascii")
    print(f"  CB pre-snap -> offset={pre_snap_result['offset_yards']:.1f}yd  side={pre_snap_result['side']}  | {r}")
    states["CB1"] = _apply_cb_pre_snap(states["CB1"], states["WR1"], pre_snap_result)

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
        "cb_calls": 0,
        "cb_parse_errors": 0,
        "cb_intent": "play_man",
    }

    actions: dict[str, dict] = {
        "QB": {"action": "hold", "reasoning": "pre-snap"},
        "WR1": {"action": "run_route", "reasoning": "running scripted route"},
        "CB1": {"action": "cover", "reasoning": "pre-snap alignment done"},
    }

    sack_clock = SACK_CLOCK
    ball_total_eta: float | None = None
    cb_intent: str = "play_man"
    intent_decided: bool = False

    for step in range(MAX_STEPS):
        t = round(step * DT, 3)
        events: list[dict] = []
        sack_clock = round(max(0.0, SACK_CLOCK - t), 3)

        # ── Track separation for telemetry ───────────────────────────────
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

            if t < 0.5:
                actions["QB"] = {"action": "hold", "reasoning": "route developing"}
                print(f"  t={t:.1f}  QB -> 'hold'    | route developing")
            else:
                # ── QB decision ──────────────────────────────────────────
                obs = build_qb_observation(
                    t, sack_clock,
                    states["QB"], attrs["QB"],
                    states["WR1"], attrs["WR1"],
                    states["CB1"], attrs["CB1"],
                    ball,
                    down=down,
                    distance=distance,
                    history=move_history,
                    expected_open_t=expected_open_t,
                    route_phases=route_phases,
                )
                qb_action = qb_agent.decide(
                    obs, states["QB"].x, states["QB"].y,
                    wr_x=states["WR1"].x, wr_y=states["WR1"].y,
                    wr_heading=states["WR1"].heading, wr_speed=states["WR1"].speed,
                    t=t,
                )
                actions["QB"] = qb_action
                p1 = qb_action.get("pass1")
                if p1 and p1["action"] == "thinking":
                    r = p1['reasoning'].encode('ascii', 'replace').decode('ascii')
                    print(f"  t={t:.1f}  QB pass1 -> thinking target={p1['target_area']} | {r}")
                r = qb_action['reasoning'].encode('ascii', 'replace').decode('ascii')
                print(f"  t={t:.1f}  QB pass2 -> {qb_action['action']!r:8}  | {r}")

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

            # ── CB movement decision (LIVE) ───────────────────────────────
            if t >= 0.3:  # give CB a step to settle from pre-snap
                cb_obs = build_cb_observation(
                    t, states["CB1"], attrs["CB1"], states["WR1"], ball,
                    wr_history=move_history, ball_total_eta=ball_total_eta,
                )
                cb_move = cb_agent.decide_movement(cb_obs)
                r = cb_move.get("reasoning", "").encode("ascii", "replace").decode("ascii")
                print(f"  t={t:.1f}  CB move  -> hdg={cb_move['heading']:.0f}° facing={cb_move['facing']:.0f}° mode={cb_move['mode']}  | {r}")
                actions["CB1"] = {**cb_move, "action": "cover"}

        # ── BALL_IN_AIR phase ────────────────────────────────────────────
        elif phase == PlayPhase.BALL_IN_AIR:
            # First step in air: ask CB for intent
            if not intent_decided:
                intent_obs = build_cb_intent_observation(
                    t, states["CB1"], attrs["CB1"], states["WR1"], ball,
                    ball_total_eta or ball.eta, cb_intent,
                )
                cb_intent = cb_agent.decide_intent(intent_obs)
                intent_decided = True
                telemetry["cb_intent"] = cb_intent

            # CB continues moving toward ball
            cb_obs = build_cb_observation(
                t, states["CB1"], attrs["CB1"], states["WR1"], ball,
                wr_history=move_history, ball_total_eta=ball_total_eta,
                cb_intent=cb_intent,
            )
            cb_move = cb_agent.decide_movement(cb_obs)
            r = cb_move.get("reasoning", "").encode("ascii", "replace").decode("ascii")
            print(f"  t={t:.1f}  CB move  -> hdg={cb_move['heading']:.0f}° facing={cb_move['facing']:.0f}° mode={cb_move['mode']}  | {r}")
            actions["CB1"] = {**cb_move, "action": "cover"}

            ball = advance_ball(ball, DT)
            if ball.eta <= 0.0:
                result = resolve(
                    states["WR1"], states["CB1"],
                    attrs["WR1"], attrs["CB1"],
                    ball.landing_x, ball.landing_y,
                    cb_intent,
                    rng,
                )
                outcome = result["outcome"]
                events.append({"type": "RESOLUTION", **result})
                recorder.record_step(t, "END", sack_clock,
                    [_player_snap(p, states[p], actions[p]) for p in states],
                    _ball_snap(ball), events)
                print(f"\n  t={t:.1f}  RESOLUTION -> {outcome}  sep={result.get('separation', '?')}yd")
                break

        # ── Move all players ─────────────────────────────────────────────
        states["WR1"] = wr_agent.move(t, states["WR1"], attrs["WR1"], DT)

        # Apply CB movement decision if one was made this step
        if "heading" in actions["CB1"]:
            states["CB1"] = cb_agent.apply_decision(actions["CB1"], states["CB1"], attrs["CB1"], DT)

        move_history.append({
            "t": t,
            "wr": [round(states["WR1"].x, 1), round(states["WR1"].y, 1)],
            "wr_hdg": round(states["WR1"].heading, 1),
            "wr_spd": round(states["WR1"].speed, 1),
            "cb": [round(states["CB1"].x, 1), round(states["CB1"].y, 1)],
            "cb_hdg": round(states["CB1"].heading, 1),
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
    telemetry["cb_calls"] = cb_agent.call_count
    telemetry["cb_parse_errors"] = cb_agent.parse_errors

    recorder.record_footer(outcome, telemetry)
    recorder.save(output_path)

    print(f"\n{'='*50}")
    print(f"OUTCOME : {outcome}")
    print(f"Telemetry: {telemetry}")
    return outcome, telemetry
