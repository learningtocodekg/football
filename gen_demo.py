"""
Generate a demo replay without needing an API key.
The mock QB waits for the slant to open, then throws with QB-style reasoning text.
Run: python gen_demo.py [seed]
"""
import sys
import pathlib
import re

# ── Mock LLM before any other import ─────────────────────────────────────────
import agents.llm_client as llm_mod

THROW_T = 2.4   # seconds before QB releases

def mock_llm(system, user, model="x", reasoning_effort=None):
    t_val = 0.0
    for line in user.splitlines():
        if "sack_clock" in line and "t=" in line:
            m = re.search(r"t=(\d+\.\d+)", line)
            if m:
                t_val = float(m.group(1))
            break

    if t_val < 1.0:
        return '{"action":"hold","reasoning":"route still developing, WR releasing off the line"}'
    if t_val < 1.8:
        return '{"action":"hold","reasoning":"CB still in phase, waiting for WR to commit"}'
    if t_val < THROW_T:
        return '{"action":"hold","reasoning":"WR about to break - holding one more beat"}'
    # Throw to slant spot: WR will be around (21-22, 72-74) after the cut
    return (
        '{"action":"throw","target_coord":[21.8,73.5],'
        '"ball_speed_mph":42,'
        '"reasoning":"WR broke inside, CB trailing by a step - zipping it to the numbers"}'
    )

llm_mod.call_llm = mock_llm

# ── Run ───────────────────────────────────────────────────────────────────────
from sim.runner import run_play

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7

out = f"replays/demo_{seed}.json"
outcome, tel = run_play(
    scenario_path="sim/scenarios/a1_basic.yaml",
    roster_path="sim/rosters/default.yaml",
    seed=seed,
    output_path=out,
)

print(f"\nReplay written: {out}")
print(f"Now run:  python -m render.renderer_pygame {out}")
