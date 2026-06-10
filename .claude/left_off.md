# Left Off
Date: 2026-06-10

## What We Worked On
Round 15 regression triage. R15 had scored 4C/1PBU/5INC vs R14's 8C/2INC. Traced root cause, fixed it, sanity-checked two routes. Did not re-run full suite.

## What Got Done

### Root cause found: Window A heading lock bug (all short-cut routes)
When WR calls Window A (0.1-0.2s before the final cut), it was outputting its current **stem heading (0°)** instead of its upcoming **break heading** (45° for slant, 180° for curl, etc.). The heading output at the call step is mechanically locked by the runner for the rest of the play — so the QB projects WR trajectory on the wrong heading and throws to the wrong spot. 5 of 6 INC/PBU regressions in R15 traced back to this.

**Fix**: Added `CRITICAL — HEADING WHEN CALLING` section to `wr_live_free.txt` near the bottom of CALL RULES:
- Window A must output BREAK heading, not current stem heading
- Added timing warning: "Do NOT call more than 0.2s early just because you know the break heading"

### WR ball-in-air brake guidance (go/curl overshoot)
WR was arriving at the landing zone early and running through it at full speed. On go route (no cut), WR hit landing zone at 9.5 yd/s with 0.53s remaining.

**Fix**: Added to `wr_ball_in_air.txt`: REQUIRED SPEED = dist_to_zone / ETA, with explicit BRAKE/COAST/ACCELERATE decision. Added current speed + required speed to `build_wr_observation` ball-in-air section in `observation.py`.

### CB sprint-or-play-man decision (WR ETA check)
CB was sprinting to the landing zone even when WR would arrive first and be set. Added WR ETA comparison to `cb_pass2.txt` and `build_cb_intent_observation` in `observation.py`. CB now computes wr_dist_to_zone/wr_speed and compares against sprint_time before committing to swat/pick.

### Sanity check results
- **slant_42**: INT → PBU (improvement; WR now calls heading=45°, but early at t=1.6 — timing warning added)
- **curl_42**: still INCOMPLETE — WR correctly calls heading=180° and QB targets (15.5, 61.4), but WR arrives at landing zone y=61.5 at t=3.3 with ETA=0.48s at speed=6.8, ignores brake signal, overshoots to y=58.9. Pure LLM behavioral failure.

### QB crossing route note (REVERTED)
Added note to `qb_pass2.txt` telling QB never to loft on crossing routes. User rejected: "that is the LLM proving it is not smart." Reverted. `qb_pass2.txt` unchanged from R14.

## What's Open / Known Issues
1. **Full 10-route suite NOT run with R15 fixes** — next step is `python run_all_routes.py --seed 42`
2. **Curl overshoot**: WR has correct required-speed info in observation but ignores brake guidance. Purely behavioral — may need stronger prompt language, or this is a model limit.
3. **WR early call on slant (t=1.6 vs correct t=1.8)**: timing warning added; not re-tested.
4. **Git push NOT done yet** — all fixes are staged.

## NEXT STEP
Run the full 10-route suite: `python run_all_routes.py --seed 42`
Look for: (a) heading lock fix closes the 5 R15 regressions, (b) CB WR-ETA check reduces go_for_pick on covered WRs, (c) brake guidance helps curl/go overshoot (skeptical), (d) new score vs R14 baseline of 8C/2INC.
Then git push if results acceptable.
