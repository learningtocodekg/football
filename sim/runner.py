"""
Phase A1 play runner.
QB = LLM agent. WR1 / CB1 = scripted.
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
from agents.scripted import ScriptedWR, ScriptedCB
from agents.observation import build_qb_observation
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
        "speed": round(state.speed, 2),
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
    model = scenario.get("qb_model", "gpt-4o-mini")
    r_effort = scenario.get("qb_reasoning_effort")  # None disables the param
    provider = scenario.get("qb_provider", "openai")
    qb_agent = QBAgent(model=model, reasoning_effort=r_effort, provider=provider)
    wr_agent = ScriptedWR()
    wr_agent.CUT_TIME = scenario.get("wr_cut_time", 2.0)
    wr_agent.CUT_HEADING = scenario.get("wr_cut_heading", 40.0)
    cb_agent = ScriptedCB()

    recorder = Recorder(header={"seed": seed, "scenario": scenario_path, "roster": roster_path})

    phase = PlayPhase.LIVE
    outcome: str | None = None
    telemetry: dict = {
        "max_separation": 0.0,
        "throw_t": None,
        "throw_distance": None,
        "sack": False,
        "qb_calls": 0,
        "qb_parse_errors": 0,
    }

    # Action labels for the replay (updated each step)
    actions: dict[str, dict] = {
        "QB": {"action": "hold", "reasoning": "pre-snap"},
        "WR1": {"action": "run_route", "reasoning": "running scripted slant"},
        "CB1": {"action": "cover", "reasoning": "scripted man coverage"},
    }

    sack_clock = SACK_CLOCK

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

            # QB decides
            obs = build_qb_observation(
                t, sack_clock,
                states["QB"], attrs["QB"],
                states["WR1"], attrs["WR1"],
                states["CB1"], attrs["CB1"],
                ball,
            )
            qb_action = qb_agent.decide(obs)
            actions["QB"] = qb_action
            print(f"  t={t:.1f}  QB -> {qb_action['action']!r:8}  | {qb_action['reasoning'][:70]}")

            if qb_action["action"] == "throw":
                tc = qb_action["target_coord"]
                mph = qb_action["ball_speed_mph"]
                # Clamp to throw-power ceiling
                max_mph = MIN_BALL_MPH + (attrs["QB"].throw_power / 99.0) * (MAX_BALL_MPH - MIN_BALL_MPH)
                mph = max(MIN_BALL_MPH, min(max_mph, mph))
                ball = throw_ball(ball, states["QB"].x, states["QB"].y, tc[0], tc[1], mph)
                dist = math.hypot(tc[0] - states["QB"].x, tc[1] - states["QB"].y)
                events.append({"type": "THROW", "target": tc, "mph": round(mph, 1),
                                "eta": round(ball.eta, 2), "dist": round(dist, 1)})
                telemetry["throw_t"] = t
                telemetry["throw_distance"] = round(dist, 1)
                phase = PlayPhase.BALL_IN_AIR

        # ── BALL_IN_AIR phase ────────────────────────────────────────────
        elif phase == PlayPhase.BALL_IN_AIR:
            ball = advance_ball(ball, DT)
            if ball.eta <= 0.0:
                result = resolve(
                    states["WR1"], states["CB1"],
                    attrs["WR1"], attrs["CB1"],
                    ball.landing_x, ball.landing_y,
                    "play_man",
                    rng,
                )
                outcome = result["outcome"]
                events.append({"type": "RESOLUTION", **result})
                # Snap final state before breaking
                recorder.record_step(t, "END", sack_clock,
                    [_player_snap(p, states[p], actions[p]) for p in states],
                    _ball_snap(ball), events)
                print(f"\n  t={t:.1f}  RESOLUTION -> {outcome}  sep={result.get('separation', '?')}yd")
                break

        # ── Move all players ─────────────────────────────────────────────
        cb_agent.record_wr(t, states["WR1"])
        states["WR1"] = wr_agent.move(t, states["WR1"], attrs["WR1"], DT)
        states["CB1"] = cb_agent.move(t, states["CB1"], attrs["CB1"], states["WR1"], DT)

        # Record step
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

    recorder.record_footer(outcome, telemetry)
    recorder.save(output_path)

    print(f"\n{'='*50}")
    print(f"OUTCOME : {outcome}")
    print(f"Telemetry: {telemetry}")
    return outcome, telemetry
