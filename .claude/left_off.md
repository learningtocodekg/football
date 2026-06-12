# Left Off
Date: 2026-06-11

## What We Worked On
Deep-dive analysis of the codebase, then a "realism" branch implementing the top findings,
then iterating WR route behavior (deception + cut timing + break direction). Merged to main.
(Supersedes the prior QB-autonomy handoff — that work lives in commit d376c1e and is referenced
as the key concern below.)

## What Got Done

### Analysis
Deep dive surfaced the core paradox: the sim scaffolds the answer for a weak model, then begs it
to copy it, while outcomes are decided by RNG — worst of both. Concerns: too much uncommanded RNG in
resolution; per-step re-decisioning causes route incoherence; the WR "right-of-way" pushout was faking
a 1.0yd separation floor (not physics); reproducibility-from-logged-prompts was claimed but never built.

### main (housekeeping)
- P4: deleted PRD.md (deprecated).
- P5: removed dead `WRAgent.record_heading`; added `eval/metrics.py` (aggregates outcome/telemetry across a replay dir).

### realism branch (the features) — MERGED TO MAIN
- **P1 — WR plan cadence**: WR emits a PLAN of 1–4 per-step actions (`parse_wr_plan`), consumed without
  re-querying until exhausted; only a thrown ball aborts it. Logic lives in `WRAgent` (runner untouched).
- **P2 — deterministic three-zone catch** (`engine/resolution.py`): sep≥1.8 → CATCH, sep≤1.0 → CB win
  (INT if go_for_pick+arm/facing, else PBU), 1.0–1.8 = the ONLY rolled band. Fixed the catch-rating bug
  that dropped ~22% of wide-open throws. CB swat/pick/play-man autonomy + INT preserved.
- **P3 — removed RNG/artifacts** (`sim/runner.py`): deleted the WR right-of-way pushout (bodies overlap
  honestly now) and the uncommanded mid-flight lane-contest dice.
- **WR prompt work** (`wr_live_free.txt` rewritten 160→~33 lines; `observation.py` CUT TARGET line):
  - Cut-timing tolerance: observation shows expected cut time/depth; WR must hit it within ±0.4s / ±2.5yd,
    or break earlier ONLY on a genuine CB rec>0 commit.
  - Deception balance: explicit STEM (climb + fake-and-RETURN, no early call) vs FINAL BREAK phases.
    Plans capped at 4 so the WR stays reactive enough to deceive.
  - Break-heading fix: emit the FINAL break heading even if >90° from current (engine pivots over 1–2
    steps). Was emitting an intermediate turn heading (270) and locking it → ran an out instead of a curl.

### Verified (2-route smoke, seed 42, gpt-5-nano)
- slant: real jab-and-return deception (270° jab at 8yd → CB bites rec=3 → break 45°), CATCH.
- curl: now hooks BACK to 180° toward the QB (stem to +8.5yd → hook → comes back), proper curl shape.
- Outcomes still PBU on well-run contested curls (WR bleeds speed into the hook).

## Concerns (re: the merge into main) — READ BEFORE NEXT SESSION
1. **QB doctrine vs realism features.** The realism WR/resolution work assumes a QB that WAITS for the
   WR's call. main's QB ("prediction/anticipation doctrine", commit d376c1e) throws BEFORE the WR's break
   — under it, slant→PBU and curl→INCOMPLETE on early no-call throws. For testing we rolled the QB back to
   06bbbc2 on realism (commit 83c4e26); that rollback was **reverted before merging** so main keeps its QB.
   → On main right now, the realism WR is paired with the anticipation QB, which throws early. The realism
   gains only show once main's QB is fixed to wait for / trust the WR call.
2. **Two chats, one repo dir.** This folder was shared with another chat fixing the QB. Only one branch is
   checked out at a time — coordinate, or use `git worktree`, before switching branches/committing.
3. **Contested curl = PBU.** Route shape is correct now, but the WR decelerates to ~3–5 yd/s through the
   hook and the CB closes. Separate from shape; needs plant-and-burst out of the break.
4. **LLM nondeterminism.** curl varies run-to-run (sometimes still breaks early). Single runs aren't proof.

## NEXT STEP
Once main's QB is fixed to wait for the WR call, run the full suite: `python run_all_routes.py --seed 42`
then `python -m eval.metrics replays`. Compare to R14 baseline (8C/2INC). If the QB still throws early,
that — not the WR — is the blocker.
