# Left Off
Date: 2026-06-13

This session: ran the full 10-route A4 suite, diagnosed the deep-ball / air-phase failures from the
replay JSONs, and fixed them MECHANICALLY in the runner + solver (not via prompts). Philosophy shift
(user): keep LLM freedom in *what it does*, but *restrict its options* — move brittle physics
decisions out of the prompt and into the deterministic runner so they can't regress from model
variance. This is what stops the fix-one-break-another loop.

## What got done (all deterministic; prompts shrank, not grew)
- **Fix 1 — WR air-phase throttle removed.** In BALL_IN_AIR the runner now drives the WR at full
  speed toward the catch point and CLAMPS it so it can't overshoot the landing (freezes at closest
  approach). The LLM keeps heading/facing freedom (bad-throw adjustment) but no longer chooses
  throttle. Killed the universal "WR brakes to match landing timing → CB closes" bleed. The
  required-speed/brake math was DELETED from `wr_ball_in_air.txt` (prompt got shorter).
  [`sim/runner.py` move block ~line 546-568]
- **Fix 3 — QB meeting-point solver projects the WR in-stride.** `_meeting_options` (`qb_agent.py`)
  used the WR's *instantaneous* speed at release (often low, mid-cut-recovery) → placed the ball
  short → WR arrived early and froze. New `_proj_distance()` projects a ramp from current speed to
  top speed, **lengthened by cut-recovery time** and scaled by a conservative `safety=0.9`. Threaded
  `wr_max_speed` + `wr_cut_recovery` from `decide()` into the solver. Conservative bias is
  deliberate: over-projecting lands the ball out of reach (INCOMPLETE, always a loss);
  under-projecting only costs a brief early arrival (contested, often still a catch).
- **Fix 2 — honest telemetry.** Added `sep_at_throw` and `sep_at_catch` (decisive numbers).
  `max_separation` is the play-peak and is useless for judging outcomes (it clustered at 5.02/3.04).
  `run_all_routes.py` summary now prints `sep@throw -> sep@catch`.

## Results (gpt-5-nano, seed 42) — progression across the session
- Baseline (start of session): **4C / 5PBU / 1INT**
- After Fix 1 only: 5C/5PBU — air bleed gone, but WR now arrived early and FROZE at the spot (CB
  closed during the dead time; comeback froze a full 1.0s).
- After Fix 1 + naive ramp: 5C/1PBU/1INT/3INC — freeze fixed but ramp OVER-projected → undershoot →
  ball out of reach (INCOMPLETE) on cut-recovery / double-move routes.
- After Fix 1 + conservative cut-recovery ramp (final): **6C / 3PBU / 1DROP**, zero INCOMPLETE.
  Separation now GROWS in flight (comeback 2.93→7.62, curl 2.89→6.82). Verified from JSON that all
  non-catches REACHED the ball (final WR-to-ball 0.18-0.37yd, only the single clamp step frozen) —
  the remaining losses are genuine coverage contests, not freeze/overshoot artifacts.

## Broken / Open
- **Multi-break routes throw before the final cut.** drag / corner / post_corner / double_move are
  the remaining non-catches. The WR executes a SECOND cut AFTER the QB throws (speed drops to ~0
  mid-flight) — the solver cannot foresee it, so projection error is large there (corner +3.85yd in
  the deterministic check). This is a WR-call-timing / route-phase problem (WR calling for the ball
  before its last break), NOT ball-placement physics. Right next layer if pursued.
- **go is a coverage contest now, not a checkdown.** This run go=PBU (threw deep ~17.7yd, WR reached
  the ball at 0.34yd but CB in phase, sep@catch 0.44). The old "go is a 9yd checkdown" illusion is
  gone; losing it now is the QB throwing a catchable deep ball into tight man — a beat-coverage
  problem, governed by LLM decision freedom.
- LLM nondeterminism: gpt-5-nano varies run-to-run even at fixed seed. Single-run route outcomes are
  noisy; the mechanical fixes were validated DETERMINISTICALLY against recorded trajectories
  (projected vs actual WR travel) to avoid chasing model noise. Do the same when iterating.
- Ollama path unchanged (lenient text parsers, `--ollama`).

## NEXT STEP
**Gate the WR's `call_for_ball` on having no remaining cuts** (only call once on the FINAL break) so
the QB stops throwing into a developing double-move on drag/corner/post_corner/double_move. That's
the sole remaining mechanical lever; everything else left is beat-the-coverage QB decisioning.

## Housekeeping
- Scratch files still in repo root: `kg_qb_prompt.txt`, `*_step_example.txt`, `curl_check.py`,
  `show_wr_obs.py`, `wr_obs.txt`, `run_log_42.txt`. Delete when convenient (not touched this session).
