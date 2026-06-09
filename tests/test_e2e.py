"""
End-to-end smoke test with mock QB and CB (no LLM API call required).
Run: python tests/test_e2e.py
"""
import json
import pathlib
import re
import sys
import os

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# ── Monkey-patch the LLM client before importing anything else ────────────────
import agents.llm_client as llm_mod

_call_count = 0


def mock_llm(system, user, model="x", reasoning_effort=None, provider="openai"):
    global _call_count
    _call_count += 1

    # ── CB calls — identified by system prompt marker ────────────────────
    if "cornerback" in system.lower():
        # Pre-snap: contains "PRE-SNAP OBSERVATION"
        if "PRE-SNAP OBSERVATION" in user:
            return '{"offset_yards": 5, "side": "outside", "reasoning": "standard off coverage"}'

        # Intent decision: contains "INTENT DECISION"
        if "INTENT DECISION" in user:
            return '{"intent": "play_man", "reasoning": "close to WR, play the body"}'

        # Movement: default to backpedaling upfield while watching WR
        return '{"heading": 0, "facing": 0, "mode": "normal", "reasoning": "closing on WR"}'

    # ── QB calls ─────────────────────────────────────────────────────────
    # Parse current t from observation header
    t_val = 0.0
    for line in user.splitlines():
        if "sack_clock" in line and "t=" in line:
            m = re.search(r"t=(\d+\.\d+)", line)
            if m:
                t_val = float(m.group(1))
            break

    # Pass 2 is identified by the commit prompt header / options table markers
    is_pass2 = "STEP 2 OF 2" in user or "CATCHABLE" in user or "MISS by" in user

    if is_pass2:
        if t_val >= 2.3:
            return (
                '{"action":"throw","option":"bullet","target_z":1.5,'
                '"reasoning":"WR open on slant after cut"}'
            )
        return '{"action":"hold","reasoning":"waiting for WR to cut"}'

    # Pass 1
    if t_val >= 2.0:
        return (
            '{"action":"thinking","target_area":[21.5,73.0],'
            '"reasoning":"WR approaching cut point, targeting slant"}'
        )
    return '{"action":"hold","reasoning":"waiting for WR to cut"}'


llm_mod.call_llm = mock_llm

# ── Now run the play ──────────────────────────────────────────────────────────
from sim.runner import run_play

os.makedirs("replays", exist_ok=True)

outcome, tel = run_play(
    scenario_path="sim/scenarios/a1_basic.yaml",
    roster_path="sim/rosters/default.yaml",
    seed=42,
    output_path="replays/test_mock.json",
)

# ── Validate the replay file ──────────────────────────────────────────────────
replay = json.loads(pathlib.Path("replays/test_mock.json").read_text())

assert len(replay["steps"]) > 0, "No steps recorded"
assert replay["footer"]["outcome"] in {
    "CATCH", "DROP", "PBU", "INTERCEPTION", "INCOMPLETE", "SACK", "TIMEOUT"
}, f"Unexpected outcome: {replay['footer']['outcome']}"

# Spot-check replay schema
step0 = replay["steps"][0]
assert "t" in step0
assert "players" in step0
assert "ball" in step0
assert len(step0["players"]) == 3

# CB telemetry present
assert "cb_calls" in replay["footer"]["telemetry"]
assert "cb_intent" in replay["footer"]["telemetry"]

# 3D ball: pos has z, and z rises then falls during flight
air_zs = [s["ball"]["pos"][2] for s in replay["steps"]
          if s["ball"]["state"] == "in_air" and len(s["ball"]["pos"]) > 2]
throw_events = [ev for s in replay["steps"] for ev in s.get("events", [])
                if ev.get("type") == "THROW"]
if throw_events:
    assert "arc" in throw_events[0], "THROW event missing arc"
    assert len(air_zs) > 0, "no in-air ball snapshots with z"
    assert max(air_zs) > 2.2, f"ball never rose above release height: max z={max(air_zs)}"

print(f"\n--- PASS ---")
print(f"Outcome:       {outcome}")
print(f"Steps logged:  {len(replay['steps'])}")
print(f"Total mock calls: {_call_count}")
print(f"Telemetry:     {tel}")
