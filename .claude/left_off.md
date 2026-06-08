# Left Off
Date: 2026-06-08

## What We Worked On
Round 9 fixes + run with GPT-5-nano (all 10 routes) + analysis. Also full rewrite of `.claude/future_3d.md` via subagent codebase audit.

## What Got Done

### Round 9 Fixes (applied before run)
- **Encoding fix**: Added `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')` to `run_all_routes.py`. Replaced all `:.0f}°` with `:.0f}deg` in `runner.py` print statements.
- **JSON enforcement**: Appended "Respond ONLY with a valid JSON object" instruction to `wr_system.txt`, `qb_system.txt`, `cb_system.txt`.
- **Route geometry injection**: Added `_ROUTE_GEOMETRY` dict to `agents/observation.py`; injected into pre-snap WR observation as `Route shape: <prose description>`. Also injected full phase schedule from `route_phases` in both pre-snap and per-step observations.
- **QB bearing injection**: In ball-in-air block, added explicit `FACING INSTRUCTION: Set facing={bearing_to_qb:.0f} exactly` line — computed from real coordinates, so WR no longer estimates it.
- **Heading streak counter**: Computed `steps_on_this_heading` in `build_wr_observation()` by scanning WR history for consecutive steps within 20° of current heading. Injected as `steps_on_this_heading=N` on the WR line.
- **`future_3d.md` rewrite**: Subagent did full codebase audit and rewrote the 3D planning doc to reflect actual current architecture (PlayPhase enum, BallState fields, QB two-pass, replay JSON schema). Added "Problems Solved by 3D" and "Problems NOT Solved" sections.

### Round 9 Run (GPT-5-nano, seed=42)
- **Score: 2C / 3D / 4PBU / 1INT** (vs Round 8: 3C / 2D / 4PBU / 1INT — regression on completion count)
- Comeback: CATCH ← new (was DROP in R8)
- In: CATCH ← new (was INT in R8)
- Post_corner: DROPPED ← regression (was CATCH in R8; WR skipped phases 1 and 2, called at 0.8s instead of ~2.4s)
- Parse errors: 0 for WR and CB (JSON enforcement worked). QB pass1 still had 3 parse errors on slant — truncation issue (token limit).

### Key findings from Round 9
- **max_sep=5.02 on 8/10 routes** — pre-snap gap is the maximum separation on almost every route. WR is creating zero dynamic separation. The CB tracks with small 10-20° adjustments that never trigger cut_recovery, so WR fakes don't commit CB hips.
- **Route geometry helps planning, not execution**: WR pre-snap notes correctly described route plan (citing shape), but per-step execution ignored the phase schedule. Post_corner WR jumped to phase 3 heading (315°) at t=0.1, skipping phases 1 and 2 entirely. Go WR immediately faked to 90° despite "NO cut, fly upfield" instruction.
- **QB bearing injection worked on most routes**: Slant facing 185–188°, double_move 190°. Comeback and in both CATCH.

## What's Open / Broken

### Biggest remaining issue
- **WR ignores per-step phase schedule**: Phase info is shown in observation but WR doesn't follow it during live play. WR's `wr_note` shows correct planning ("I should be in phase 1 now") but heading output contradicts it. Need to inject real-time phase status: "You are at t=X.Xs. Current phase: Phase N. Expected heading: ~Y°. Your heading: Z°. [OFF COURSE / ON TRACK]."

### Still open from R8
- **N4**: WR CB-commit trigger ("CB rec > 0") still referencing unobservable field. Replace with observable proxy from move log (CB Δhdg > 90° in last N steps).
- **W1/W2**: WR premature call and wrong heading at call. Post_corner called at 0.8s (phase 1), curl called at 0° (wrong direction for curl).
- **N7/N8**: CB over-commitment and geometric hallucinations.
- **QB pass1 truncation**: slant had 3 parse errors from truncated JSON (not malformed). Token limit issue on pass1.

## NEXT STEP
**Inject real-time phase status into per-step WR observation** in `agents/observation.py`, `build_wr_observation()`:
- Compute current expected phase from `route_phases` and `t`
- Compare expected heading to `wr.heading`
- If off by more than ~30°, inject: "PHASE CHECK: t=X.Xs → Phase N ({prev_t}–{threshold_t}s): expected heading ~Y°. Your heading: Z°. OFF COURSE — correct this step."
- If on track: "PHASE CHECK: t=X.Xs → Phase N: heading Z° ✓ ON TRACK"
All data already available in `build_wr_observation()` — no new parameters needed.
