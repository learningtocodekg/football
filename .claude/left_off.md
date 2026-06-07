# Left Off
Date: 2026-06-07

## What We Worked On
- Analyzed all 10 replay JSONs from Run 5 (seed=42, gpt-5-nano, A4 prompts, post P-NEW + angle blacklist + ball-in-air-lock + QB judgment fixes)
- Consolidated problems.md (merged from problems.md + problems2.md + problems3.md + new Run 5 findings), deleted problems2.md and problems3.md
- Redesigned the CB observation to remove prescriptive option labels and give raw field geometry instead

## What Got Done

### problems.md consolidated
- Single problems.md now contains: Run 5 results table, 6-dimension analysis (WR deception, QB timing, WR anticipation, CB determinism, LLM freedom, overall quality), full problem tracking table with statuses from Rounds 1–3 (P/N/O series) + new Run 5 findings (A1–A4)
- problems2.md and problems3.md deleted

### CB observation redesign (the main work)
Three files changed:

**`agents/observation.py` — `_cb_situation()` rewritten (~55 → ~12 lines):**
- Removed: all three labeled options ("backpedal / intercept / mirror"), tradeoff descriptions, `wr_motion` prose ("Backpedaling widens the gap"), `y_rel`/`x_rel` prescriptive prose, `wr_coming_back`/`wr_going_lateral` flags
- New output: lean `GEOMETRY:` block — separation, bearing to WR, WR projected position in 0.5s, bearing to intercept that projection
- Philosophy: raw geometry only, no pre-selected answer

**`agents/prompts/cb_system.txt`:**
- Replaced `THE SITUATION BLOCK:` paragraph (which mentioned option labels/tradeoffs) with `YOUR OBSERVATION:` paragraph describing raw data, no option framing

**`agents/prompts/cb_pass1.txt`:**
- Instruction line no longer references "SITUATION block" or "options with tradeoffs"
- Example JSON changed from `{"heading": 5, "facing": 185, "mode": "backpedal", "reasoning": "WR is still approaching and I want to keep cushion..."}` to `{"heading": 95, "facing": 95, "mode": "normal", "reasoning": "WR cut right and accelerated — closing to cut off the angle"}`
- New example anchors the model on forward/lateral movement with observed-action reasoning, not cushion-maintenance

### Run 6 slant_42 result (first test after CB redesign)
- **Outcome: PBU, separation=1.24** (vs Run 5 DROP, separation=4.83)
- CB heading varied across the entire play: 190°, 139°, 147°, 60°, 69°, 355°, 59°, 149°, 59°, 0°, 36°, 35°, 38°, 39°, 45°, 60°, 50°, 342° — genuinely tracking the WR
- CB switched to `mode=normal` at t=1.1 and ran laterally at 36°–39° for 5 consecutive steps, matching the WR's 40° slant
- CB intent=swat, closed to 1.24 yd at resolution — a legitimate PBU
- Previous run: CB was pure backpedal heading=5° the entire play

## What's Open / Known Issues

### CB issues (mostly improved)
- CB still uses `mode=backpedal` on some steps while heading laterally (e.g., heading 60° mode=backpedal at t=0.6) — incoherent but minor; physics apply backpedal speed cap unnecessarily
- Only one route tested so far — need full 10-route run to assess overall improvement

### WR issues (unchanged from Run 5)
- **A1 / P-NEW**: In-route WR still calls pre-cut at heading=0° → INTERCEPTION. The "anticipate future position" prompt fix didn't prevent it.
- **A3 / Go route**: QB still freelances without WR call
- **R5-3 / O1**: Curl WR still changes heading during ball flight (called mid-rotation at 270°, then drifted to 150°)
- **R5-4 / O4**: Slant WR cuts to 40° (shallow right) not ~315° (true crossing slant)
- **detected_cut_t**: Still misfires on jabs (fires at 0.1–0.8 on most routes)

## NEXT STEP
**Run all 10 routes with seed=42 (Run 6) after CB redesign** and compare to Run 5 (4C/2D/3PBU/1INT → 4 catches). Primary questions:
1. Does CB now contest horizontal routes it was ignoring before (drag, in, zig)?
2. Does CB's fake-reading improve on post_corner (which held a 5-step fake that had zero effect in Run 5)?
3. Does PBU/INT rate increase meaningfully, or does the LLM regress to a different template?
4. Run: `.venv\Scripts\python run_all_routes.py` then check all 10 replay JSONs
