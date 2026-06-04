# Left Off
Date: 2026-06-04

## What We Worked On
CB agent diagnostic and prompt/observation fixes. Analyzed play_42.json replays for slant and comeback routes.

## What Got Done

**CB observation — comeback route fix (`agents/observation.py`):**
- `_cb_situation()` had only 3 states, all keyed on `dy` (who is upfield). On a comeback, the WR runs upfield past the CB, then reverses to 180°. When the WR cut back, `dy < -0.5` fired and told the CB to backpedal *further upfield* — 14.17 yd separation, CATCH.
- Added `wr_coming_back` check: if WR heading is 135–225° AND CB is upfield of WR, emit a 4th state: "WR has cut BACK toward QB — flip hips and CHASE downfield. Do NOT backpedal."
- Result after fix: 0.1 yd separation, DROP.

**CB observation — intercept heading (`agents/observation.py`):**
- Added `_intercept_heading()`: projects WR 0.5s forward along current heading/speed, returns bearing from CB to that projected point. Chase actions now give "intercept heading" (leads WR) alongside "bearing directly to WR" (current spot). Helps CB converge faster rather than always chasing where the WR just was.

**CB prompt — stronger copy rule (`agents/prompts/cb_pass1.txt`):**
- Previous: "Do NOT invent headings" (ignored by LLM). New: "Copy the heading and facing numbers EXACTLY from the RECOMMENDED line." Moved rule to top of prompt. Reduces hallucinated headings (the t=1.3 stutter where LLM emitted 129° instead of ~3°).

**CB ball-in-air facing — intent-aware (`agents/observation.py`, `sim/runner.py`):**
- `build_cb_observation()` now accepts `cb_intent` parameter.
- BALL IN AIR block emits a `FACING:` line keyed on intent:
  - `swat`/`go_for_pick`: face the landing zone (bearing_to_zone for both heading and facing)
  - `play_man`: face the WR (bearing_to_wr), heading toward zone
- `cb_pass1.txt` updated: "follow the FACING line in BALL IN AIR exactly."
- Runner wires `cb_intent` into the BALL_IN_AIR movement calls.

**Confirmed: LLM calls are stateless — no compounding context.**
- Each step is a fresh 2-message conversation (system + user). The `wr_history` table (last 10 steps) is embedded in the observation string as plain text — that's all the CB "remembers."

## What's Broken / Open
- t=1.3 heading stutter still appears (LLM emits 129° during backpedal phase on both slant and comeback). Prompt fix helps but doesn't eliminate it. Would need stronger enforcement or a deterministic gate in runner.py to ignore heading changes during backpedal unless a cut is detected.
- CB pre-snap always picks offset=5, side=outside — not varying by situation.
- CB intent is almost always "swat" even when too far; play_man rarely chosen.

## NEXT STEP
Build the WR agent (Phase A3). ScriptedWR exists and runs routes correctly — the LLM WR should replace it with a reactive agent that reads the CB's position and chooses when/how to execute route breaks. Start with observation + prompt design, then wire into runner.
