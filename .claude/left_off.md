# Left Off
Date: 2026-06-06

## What We Worked On
Three rounds of A4 analysis across two LLM providers (Ollama qwen3:8b, OpenAI gpt-5-nano). Applied N1/N3/N7 fixes, freed the CB from prescriptive SITUATION block, gave the WR a side-by-side MOVE LOG, and ran problems through three rounds of replay analysis.

## What Got Done

### A4 Round 1 — Initial fixes (P1–P10)
- P1: `_can_call()` returns True for go routes (cut_time >= 9.0). No hardcoded "YOU ARE OPEN."
- P3: Deception coaching rewritten with richer taxonomy (jab, hold fake, speed fake, double fake; no same move twice). Removed "AT MOST ONE jab" limit.
- P5: corner cut_heading 315° → 290°.
- P6: REVERTED — WR abandoning routes is valid AI behavior, not a bug.
- P7: CB SITUATION block detects `wr_going_lateral` and emits lateral intercept context.
- P10: drag stem 0.3 → 0.7s; curl call_tolerance 90° → 135°.
- run_all_routes.py: `--ollama` / `--model` flags.

### A4 Round 2 — N1/N3/N7 fixes (from Ollama qwen3:8b run)
**N1 — 2-step cut persistence (sim/runner.py):**
- Jabs at exactly t=0.5 were being detected as cuts.
- New: heading change ≥30° creates a candidate. Next step: snaps back within 20° → discard (jab). Holds → confirm as cut.
- Variables: `cut_candidate_t`, `cut_candidate_from_hdg`.

**N3 — LEAD HINT y-direction labels (agents/observation.py):**
- QB was throwing upfield on comebacks because heading 180° was ambiguous.
- LEAD HINT now explicitly labels y as DECREASING/INCREASING with current and projected values.

**N7 — Self-action history for both agents (agents/observation.py):**
- CB gets "YOUR RECENT ACTIONS" showing own heading + mode per step.
- WR history table updated with throttle column.

### A5 — CB freed, WR gets MOVE LOG
**CB freed from prescriptive SITUATION block:**
- Root cause: `_cb_situation()` always emitted `RECOMMENDED: backpedal` when `dy < -0.5` AND WR heading outside 45–135°/225–315° (WR jabs at 330°/30° fall in this gap). `cb_pass1.txt` then said "copy the heading numbers EXACTLY."
- `_cb_situation()` now shows `YOUR OPTIONS:` (backpedal/intercept/mirror) with tradeoffs — no RECOMMENDED.
- `cb_pass1.txt`: removed "copy heading numbers EXACTLY." CB decides.
- `cb_system.txt`: removed hardcoded PHASE TRANSITIONS. One paragraph: use SITUATION BLOCK as context.

**WR side-by-side MOVE LOG (agents/observation.py, sim/runner.py):**
- Replaced WR-only history table with MOVE LOG: WR hdg/spd + CB hdg/mode/Δhdg per step.
- WR can now see whether its jabs actually changed what the CB did.
- `runner.py` move_history now includes `cb_mode`.
- WR current CB snapshot includes `mode={cb.mode}`.

### A4 Round 3 — OpenAI gpt-5-nano run (problems3.md)
Results: 2 CATCH (comeback ✓, in ✓), 1 PBU (double_move), 1 INT (go), 6 DROP

New problems O1–O8 documented in problems3.md:
- **O1 (HIGH)**: Ball-in-air heading abandonment — WR changes body heading during flight (curl, zig, drag all DROP).
- **O2 (MEDIUM)**: Corner WR abandons real break, returns to stem after executing it.
- **O3 (MEDIUM)**: Go — QB threw behind CB → INTERCEPTION (CB position not checked).
- **O4 (MEDIUM)**: Slant WR cut to 40° instead of ~315°.
- **O5 (MEDIUM)**: Double move WR ran east physically during fake phase → CB followed → PBU not CATCH.
- **O6 (MEDIUM)**: Post_corner 0.7s call delay after real break → CB recovered → swat.
- **O7 (HIGH)**: N2 cookie-cutter 330°/30° jabs STILL on all 10 routes. MOVE LOG and self-history haven't broken it.
- **O8 (MEDIUM)**: QB lead direction wrong for lateral-heading WR (drag).

## What's Open / Known Issues
- **O1/N5** — most impactful: explicit heading-lock instruction in ball-in-air prompt. Affects 3 routes.
- **O7/N2** — widespread: live angle blacklist per step ("do NOT use 330° or 30° again this play").
- **O2** — corner: mark real break as terminal once held 2+ steps.
- **O3** — go route QB: check CB y-position before throwing, target must clear CB.
- **O8/N6** — QB lead: route-type-aware throw speed/direction.
- detected_cut_t fires on first jab, not real break.
- CB pre-snap alignment not varying by route type.
- CB intent is almost always "swat."

## NEXT STEP
Priority order:
1. **O1** — heading-lock in ball-in-air prompt. Clear fix, 3 routes affected, no ambiguity.
2. **O7/N2** — live angle blacklist: per-step "do NOT reuse these jab angles: [list seen so far]."
3. **O2** — post-corner/corner: terminal cut marker once WR has held real break heading 2+ steps.
4. **O3** — go route: QB observation should include CB y-position check before committing throw.

Re-run all 10 routes after O1 fix to check improvement. Compare vs run_log_42.txt baseline.
