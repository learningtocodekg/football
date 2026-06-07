# Left Off
Date: 2026-06-06

## What We Worked On
A4 CB/WR scaffolding overhaul: freed the CB from prescriptive SITUATION block, gave the WR a side-by-side MOVE LOG so it can see whether its jabs are actually moving the CB.

## What Got Done

**CB freed from prescriptive SITUATION block (`agents/observation.py`, `agents/prompts/cb_pass1.txt`, `agents/prompts/cb_system.txt`):**
- Root cause found: `_cb_situation()` always emitted `RECOMMENDED: backpedal` when `dy < -0.5` AND WR heading was outside 45–135°/225–315° (WR jabs at 330°/30° fall in this gap). Combined with `cb_pass1.txt` saying "copy the heading numbers EXACTLY from the RECOMMENDED line," the CB was a rule-follower with zero decision-making.
- `_cb_situation()` now shows `YOUR OPTIONS:` with backpedal/intercept/mirror and tradeoffs — no RECOMMENDED action.
- `cb_pass1.txt`: removed "RULE: Copy the heading and facing numbers EXACTLY." CB now decides.
- `cb_system.txt`: removed hardcoded PHASE TRANSITIONS section. Replaced with one paragraph: "THE SITUATION BLOCK: use it as context — read it, weigh the options, decide."

**WR now sees CB reaction in history (`agents/observation.py`, `sim/runner.py`):**
- Replaced WR-only "YOUR RECENT HISTORY" table with side-by-side "MOVE LOG" showing WR hdg/spd + CB hdg/mode/Δhdg per step.
- WR can now observe whether its jabs changed what the CB did — closes the deception feedback loop.
- `runner.py` `move_history.append()` now includes `cb_mode` so the MOVE LOG can display it.
- WR current CB snapshot line now includes `mode={cb.mode}` so WR sees if CB is backpedaling or chasing right now.

## What's Open / Known Issues
- CB changes not yet tested — all 10 routes need a re-run to see how the free CB performs.
- detected_cut_t fires on first jab (any 30°+ heading change), not the real route break.
- CB pre-snap alignment not varying by route type.
- CB intent is almost always "swat."

## NEXT STEP
**Re-run all 10 routes with the freed CB and check two things:**
1. Does the CB now react differently to jabs (any heading change vs. always backpedal)?
2. Does the WR start using the MOVE LOG to adapt its deception — jabbing differently based on what moved the CB?

Run: `python main.py --scenario sim/scenarios/a4_wr_slant.yaml` (and other routes). Compare vs. run_log_42.txt baseline.
