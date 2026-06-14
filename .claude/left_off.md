# Left Off
Date: 2026-06-14 (session 3)

This session: the user reframed the whole eval — **a CATCH is not a good play and a PBU is not a bad one**;
judge by route correctness, ball accuracy, coverage, and air-play (see memory feedback-outcome-vs-quality).
Under that lens the 9C/1PBU suite was mostly broken routes that happened to be caught. We did a ground-up
fix of WR route execution via a **soft rail**, plus QB throw-timing fixes. Result: the 6 routes the user
flagged as broken now run with CORRECT SHAPES (not lucky catches).

## The core idea (memory: project-wr-soft-rail)
The WR's one `heading` output was doing two fighting jobs — RUN THE ROUTE and JUKE. No prompt phrasing
could make the model do both, so it abandoned the route to juke. Fix: **split them.** The engine guarantees
the route SHAPE as a backstop (with advance warning in a ROUTE STATUS obs line); juke/read/call stay free.

## What got done
- **`RouteRail`** (`agents/scripted.py`): per-play soft rail. govern() corrects the WR's decision each tick;
  status() narrates the backstop. Mechanics: **depth-gated stem** (break only after running the route's
  designed depth = `_burst_distance(stem_dur)`, early read past 70%); **duration-held fakes**; **early break
  only from the stem (leg0)** so a fake can't be short-circuited; **STEM_CONE=25°** feint limit (a hard turn
  sheds ~40% speed, so wider weaving dawdled the stem and arrived late — this was the curl/double_move killer
  at cone 45–70); **positional leash** (2yd lateral / 0.75yd backward) on the final leg/go; **settle** stop
  for comeback/curl. Forced accelerate on non-final legs.
- **Call gate** (user-approved override of no-phase-gate; memory project-wr-call-gate): a call is HELD until
  the FINAL break (stem finished); for a settle route it fires AS THE WR HOOKS (not after fully planted) so
  the ball arrives while the CB's deep momentum carries him past. Early calls are deferred and auto-fire.
- **QB window-filter** (`qb_agent._meeting_options`; memory project-qb-window-filter): pass2 is only offered
  arcs that ARRIVE inside pass1's open window; if none fit, hold. Mechanically enforces deep-ball cushion
  discipline. DISABLED for settle routes (a stopped WR waits for the ball). Fixed the go PBU→CATCH.
- **QB lob heuristic** (`qb_pass2.txt`; memory feedback-qb-lob-over-cb): when the CB is BETWEEN the WR and
  the QB (in the lane), throw a LOB over his head, not a flat bullet. Verified: go now throws a `touch` arc.
- WR prompt (`wr_live_free.txt`) slimmed to juke / read / call (the rail does route execution now).
- 11 deterministic rail unit tests (`tests/test_route_rail.py`) — all pass (no LLM).
- Deleted dead `_phase_instruction`/`_est_yards` from observation.py; centralized SETTLE_* in scripted.py.

## Per-route result (gpt-5-nano, seed 42) — judged by SHAPE, not just outcome
- go: **CATCH 2.29**, real straight go, QB lobs (`touch`) over the trailing CB ✓ (was: WR bailed to 90°)
- comeback: **CATCH 2.1**, true 12yd stem → break back → plant & sit ✓ (was: caught at LOS)
- curl: **CATCH 1.79**, clean stem → hook → settle, throw on the hook ✓ (was: never sat)
- zig: **CATCH 2.92**, runs BOTH moves (jab + out) ✓ user: "perfect" (was: skipped the in-part)
- double_move: **CATCH 7.02**, clean fake holds → snap back deep → CB beaten ✓ (was: thrown on the dig)
- corner: **CATCH 1.81** ✓ user: "good" (was: the lone PBU 0.85)
- slant / drag / in: CATCH, still good ✓
- post_corner: user says "perfect" (route runs stem→fake→corner, WR open). One auto-run was INCOMPLETE on
  the QB's deep-corner throw placement (WR was open, sep ~3) — a QB meeting-solver projection limit, not a
  route bug.

## Broken / Open
- **curl earlier-throw hint UNVERIFIED live.** Added to qb_pass2 ("settle window is brief, throw as he
  hooks") but the verifying run got cut by the 599s batch timeout (go ran, curl did not). The curl replay
  in the repo is the prior CATCH 1.79 (throw at t=2.2 on the hook — already decent). Re-run to confirm.
- **post_corner throw accuracy**: QB meeting-point solver mis-places the throw after the multi-break deep
  corner (WR open). The known multi-break projection limit — pass2 projects the WR in-stride and can't
  foresee the path after a late second cut. Lone real open item.
- comeback can break a touch shallow (~8yd) when the 70%-depth early-read fires; raise the floor if deeper
  comebacks are wanted (user didn't flag it).
- LLM nondeterminism persists; rail mechanics are validated DETERMINISTICALLY by the unit tests on top.

## NEXT STEP
**Re-run curl to verify the earlier-throw hint, then tackle post_corner throw accuracy** — make the QB
meeting-point solver project the WR along his FINAL leg (post-second-cut) on multi-break routes, so the
deep-corner throw lands where the (open) WR actually ends up.

## Workflow note
Each route is ~3–5 min of LLM latency, so `run_all_routes.py` fits only ~2 routes per 599s Bash timeout;
it runs routes in the ARG order given, and the first (slow) route can eat the budget and leave later ones
STALE — always check replay mtimes before trusting results.
