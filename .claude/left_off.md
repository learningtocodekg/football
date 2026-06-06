# Left Off
Date: 2026-06-06

## What We Worked On
Round 2 fixes from Ollama qwen3:8b run (10 A4 routes — all 3 LLM agents live). Read problems.md
P1–P10, applied original fixes, re-ran all 10 routes via `--ollama`, spawned subagents to analyze
replay JSONs, wrote N1–N10 into problems.md, then applied code fixes for N1, N3, N7.

## What Got Done

**N1 — 2-step persistence for cut detection (sim/runner.py):**
- `t >= 0.5` gate wasn't enough — WR jabs at exactly t=0.5.
- New logic: heading change ≥30° creates a "candidate." Next step: if WR snaps back within 20° of
  pre-jab heading → discard (jab). If it holds → confirm as cut.
- Variables: `cut_candidate_t`, `cut_candidate_from_hdg` in runner loop.

**N3 — LEAD HINT y-direction labels (agents/observation.py):**
- QB was throwing upfield on comebacks because heading 180° was ambiguous.
- LEAD HINT now explicitly labels: "y is DECREASING toward QB (current y=X.X → projected y=X.X)"
  vs "y is INCREASING upfield".

**N7 — Self-action history in both agent observations (agents/observation.py):**
- WR section renamed to "YOUR RECENT ACTIONS" with throttle column.
- CB now also gets "YOUR RECENT ACTIONS" showing its own heading + mode history per step.
- Both agents can notice their own oscillation patterns without being told what to do.

**Round 1 fixes (P1–P10) also completed this session:**
- P1: `_can_call()` returns True for go routes (cut_time >= 9.0). Observation guides WR to call
  when it judges it's open — no hardcoded "YOU ARE OPEN" directive.
- P3: Deception coaching rewritten with richer taxonomy (jab, hold fake, speed fake, double fake;
  no same move twice). Removed "AT MOST ONE jab" limit.
- P5: corner cut_heading 315° → 290°.
- P6: REVERTED — WR abandoning routes is valid AI behavior, not a bug.
- P7: CB SITUATION block detects `wr_going_lateral` (45–135° or 225–315°) and emits "DRIVE
  LATERALLY to intercept" instead of continuing backpedal.
- P10: drag stem 0.3 → 0.7s; curl call_tolerance 90° → 135°.
- run_all_routes.py: added `--ollama` / `--model` flags.

**Problems.md updated:**
- N2: OPEN (WR deception upgrade TBD). N4/N9: SKIP (AI decisions).
- N5: SKIP (broader ball-in-air question). N6: SKIP (QB throw-speed question).
- N8/N10: CLOSED (expected artifacts, not bugs).

**Memory saved:** `memory/feedback_high_freedom.md` — guide agents with context/tips only; never
enforce. Failures are test data. N4/N5/N6/N9/N10 are intentionally left open.

## What's Open / Known Issues
- **N2**: WR jab is cookie-cutter 330°/30° across all 10 routes despite richer coaching.
  Self-action history may help the WR notice its own pattern; not yet verified.
- **N5**: Curl WR drifts sideways during ball-in-air. Broader design question: how should all
  agents track a ball in flight? Don't patch curl-specifically.
- **N6**: QB throw speed selection (when to bullet vs lob). Fundamental QB reasoning question.
- **N4/N9**: WR exits fake phases early. Intentional — AI decides when to break.

## NEXT STEP
1. Re-run all 10 routes to verify N1/N3/N7 fixes improved outcomes.
2. Discuss N2: how to get WR to vary deception beyond the 330°/30° template.
   - Does self-action history make the WR self-correct?
   - Or do we need explicit per-step callout: "you've jabbed 330° 4 times — stop"?
3. Discuss N5 + N6 when ready.
