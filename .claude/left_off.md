# Left Off
Date: 2026-06-10

## What We Worked On
Route analysis (corner + go), QB lead prompt fix, full Round 14 3D baseline, CB overhaul (press coverage, break-on-ball, cut detection stabilization, jam mechanic).

## What Got Done

### Route analysis: corner INCOMPLETE → root cause isolated
- **corner_42**: INCOMPLETE — ball_offset > 1.3 yd (WR arrived ~0.1s late). sep=2.32 yd, CB irrelevant. Root: QB projected arrival using constant WR speed but WR was in 3-step cut recovery immediately after the 290° break — arrived ~1.4 yd short of the catch spot.
- **go_42** (before lead fix): CATCH, sep=2.4 yd, 33.3 yd bullet. Clean isolation: same arc, longer distance, no cut, no recovery → CATCH. Corner missed only because of recovery drag. QB lead math was the bug.

### QB lead prompt fix
- `qb_pass2.txt` / `qb_system.txt`: replaced vague "lead the WR" with concrete **0.3–0.5 yd ahead in movement direction** + **0.3–0.5 yd opposite the CB**, with per-case examples (CB left → throw right of WR center; CB underneath → add lead AND raise z; WR runs INTO the ball, not waits for it).

### Round 14 — 8C / 2 INCOMPLETE (first full 3D baseline)
```
slant    CATCH  sep=4.77  corner  CATCH  sep=5.34 ← was INCOMPLETE, now fixed
go       INCOMPLETE (WR called at t=3.7, model variance late call)
comeback INCOMPLETE (pre-existing: WR calls heading=0° before 180° break, heading locks wrong)
double_move CATCH sep=9.33   curl  CATCH   zig  CATCH   drag  CATCH
post_corner CATCH             in   CATCH
```
Corner fix confirmed. Go regression = WR model variance (called at t=2.2 last run, t=3.7 this run — WR on go route doesn't have a "cut/rec>0" trigger, just pure speed separation). Comeback is a pre-existing WR bug.

### CB overhaul (code + prompts, smoke-tested on slant)
Four changes, all landed and verified:

1. **`cb_pre_snap.txt`** — real PRESS/OFF/CUSHION alignment with explicit tradeoffs. CB no longer defaults to 5 yd every play.

2. **`cb_pass2.txt`** — replaced hard "arm tip > 2 yd → play_man, full stop" gate with sprint-time-vs-ETA check. CB now computes `dist_to_zone / max_speed` vs `ball_ETA` and chooses to race to the landing spot (swat/pick) when it can get there in time. Smoke test line 85: CB correctly printed "sprint_time 1.26s > ball_ETA 1.17s → play_man" — math working.

3. **`observation.py`** — three additions:
   - `build_cb_intent_observation`: added `max_speed` + sprint ETA line so CB has the numbers for the sprint check
   - `build_cb_observation`: added `detected_cut_t` param; emits "CUT CONFIRMED at t=X" in live phase — CB no longer re-derives the cut each step
   - `build_wr_pre_snap_observation`: press warning when CB sep ≤ 1.5 yd ("expect physical jam, release move helps")

4. **`runner.py`** — two additions:
   - Pass `detected_cut_t` to both LIVE and BALL_IN_AIR `build_cb_observation` calls
   - **Jam mechanic**: if CB chose press (offset ≤ 1 yd), WR throttle capped at "coast" for 3 steps (0.3s); reduced to 1 step if WR's first heading diverges ≥45° from CB press facing (release beat press). Prints `[PRESS RELEASE]` or `[JAM CLEARED]` log lines.

## What's Open / Known Issues
1. **Full 10-route run with CB changes NOT yet done** — only smoke tested slant. Need a full run to see if press coverage fires and if sprint-on-ball produces swat attempts.
2. **CB flip-flop partially fixed** — CUT CONFIRMED in observation helps, but cb_pass1 stem-check logic can still override it on later steps. May need the stem-phase check to stop applying once detected_cut_t is set.
3. **Comeback WR bug**: WR calls at heading=0° before executing the 180° break → heading locks wrong direction. Pre-existing.
4. **Go route call timing**: WR doesn't know when to call on a no-cut vertical (no "CB rec>0" trigger). High variance.
5. Jump action (WR/CB vertical timing) deferred.
6. gen_demo.py legacy ball_speed_mph format.

## NEXT STEP
Run the full 10-route suite with the new CB changes: `python run_all_routes.py --seed 42`
Look for: (a) CB choosing press on short routes, (b) sprint-on-ball producing swat intents on longer flights, (c) jam fires (look for `[JAM CLEARED]` in log), (d) whether the 8C baseline holds or CB improvements cause regressions.
