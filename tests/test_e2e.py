"""
End-to-end smoke test with a mock QB (no LLM API call required).
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


def mock_llm(system, user, model="x", reasoning_effort=None):
    global _call_count
    _call_count += 1

    # Parse current t from observation header
    t_val = 0.0
    for line in user.splitlines():
        if "sack_clock" in line and "t=" in line:
            m = re.search(r"t=(\d+\.\d+)", line)
            if m:
                t_val = float(m.group(1))
            break

    # Throw at t >= 2.3 to the slant landing spot
    if t_val >= 2.3:
        return (
            '{"action":"throw","target_coord":[21.5,73.0],'
            '"ball_speed_mph":40,"reasoning":"WR open on slant after cut"}'
        )
    return '{"action":"hold","reasoning":"waiting for WR to cut"}'


llm_mod.call_llm = mock_llm

# ── Now run the play ──────────────────────────────────────────────────────────
from sim.runner import run_play

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

print(f"\n--- PASS ---")
print(f"Outcome:      {outcome}")
print(f"Steps logged: {len(replay['steps'])}")
print(f"QB mock calls:{_call_count}")
print(f"Telemetry:    {tel}")
