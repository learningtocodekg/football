# Left Off
Date: 2026-06-08

## What We Worked On
Focused session on the slant route: separation geometry redesign, WR call-timing improvement, QB CB-at-arrival projection, and parse error fixes. Goal was to get the slant to produce a CATCH.

## What Got Done

### Separation geometry redesign
- Added `PLAYER_RADIUS = 0.5` yd to `engine/physics.py`
- Redefined "open" as **1.5 yd edge-to-edge body gap** (= 2.5 yd center-to-center). Old threshold was 3.0 yd c-to-c — too conservative.
- `engine/resolution.py`: `eff_sep = max(0, sep - 2*PLAYER_RADIUS)`, sigmoid shifted to `mid=0.5, k=0.5` on edge-to-edge distance. `PBU_PROXIMITY` raised 1.0 → 1.5 yd.
- `agents/observation.py`: WR obs shows 4-tier body_gap system (VERY OPEN/OPEN/CONTESTED/CONTACT). QB and CB obs show body gap alongside center distance.
- `qb_system.txt`: thresholds updated to `>2.5 yd = open, 1.5–2.5 = contested, <1.5 = contact`.

### Collision enforcement
- `sim/runner.py`: After CB `apply_decision`, if CB-WR distance < 1.0 yd (2×PLAYER_RADIUS), CB is pushed out to minimum 1.0 yd. WR has right of way (pushing WR = penalty in NFL).

### QB CB-at-arrival projection
- `agents/qb_agent.py` `_build_options`: now accepts `cb_heading`, `cb_speed`, projects CB forward by ETA. Options table shows `WR at arrival | CB at arrival | sep@arr | [cb_context]`.
- `qb_pass2.txt`: rewrote with 3-step throw placement rule — (1) lead WR, (2) aim away from CB's projected position, (3) stay within 1.3 yd catch radius.

### WR deception clarity
- `wr_live_free.txt`: Added "DECEPTION SERVES YOUR FINAL CUT" block — fakes have ONE purpose, creating misdirection for the specific FINAL break direction.

### WR call-timing fix
- Added "CALL TIMING" note to `wr_live_free.txt` explaining the math: QB takes 1 step to process + ball flight. Calling at CB rec=3 → ball arrives at CB rec≈0. Waiting for visual confirmation the gap grew → ball arrives after window closes.
- Added "CRITICAL: CB rec > 0 after your final cut IS clear separation — do not wait to see the gap grow visually."
- Updated good note examples to show calling at CB rec=3 as correct behavior.

### QB parse error fix
- `agents/schema.py` `parse_qb_pass2`: added fallback for model generating old `target_coord/ball_speed_mph` format instead of `option: "<label>"`. Three missed throw windows per run were caused by this.
- `agents/qb_agent.py`: parse error logging now prints full raw (not truncated 120 chars).

### Result
Slant route: **CATCH at sep=2.07 yd**, 0 parse errors. WR called at t=1.8 (CB in recovery), QB threw at t=1.9, ball arrived with CB going for swat but not reaching.

## What's Open / Broken

### Carried forward from Round 9 (still open)
- **WR ignores per-step phase schedule (CRITICAL)**: NEXT FIX from last session. Still not done. Inject real-time "PHASE CHECK: t=X → Phase N, expected Y°, your heading Z°. [ON TRACK / OFF COURSE]" into `build_wr_observation()`.
- **max_sep=5.02 on all routes**: Pre-snap gap is still the maximum on every run. WR isn't creating dynamic separation beyond the pre-snap cushion.
- **N4 — WR phantom CB rec trigger**: WR references "CB rec > 0" which is computed from the move log. Need to verify the move log shows CB rec correctly so WR can use it.
- **W1/W2 — WR premature call on other routes**: Slant fixed; curl/post_corner still likely to call early or wrong heading.
- **N7 — CB over-commits to fake**, **N8 — CB geometric hallucinations**

### New findings this session
- The slant improvements haven't been tested on other routes — need a full run to see if they regress or help.
- WR "DECEPTION IS FOR THE FINAL CUT" appears twice in wr_live_free.txt (lines 39-45 and 47-54) — duplicate from earlier session, harmless but messy.

## NEXT STEP
Two options (pick one):
1. **Run all routes** (`run_all_routes.py`) to see if slant improvements hold/regress across the full 10-route set — get a Round 10 score.
2. **Implement PHASE CHECK** in `agents/observation.py` `build_wr_observation()` — the critical unfinished fix from Round 9.

Recommended: **run all routes first** to get a baseline before the phase check change, then implement phase check and run again.
