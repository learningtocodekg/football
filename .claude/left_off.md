# Left Off
Date: 2026-06-09

## What We Worked On
Round 13 prep: diagnosed and fixed the CB agent across all 10 routes. Dispatched 10 parallel subagents to read each replay from Round 12 and produce per-route CB failure analysis. Then rewrote cb_system.txt, cb_pass1.txt, cb_pass2.txt based on findings. Tested curl-only with GPT-5-nano. Tried Ollama for full 10-route run — too slow with parse errors, killed it.

## What Got Done

### CB Failure Analysis (all 10 routes via subagents)

Six confirmed bugs, ordered by severity:

| Bug | Description | Routes | Cause in prompt |
|---|---|---|---|
| B3 (worst) | Self-induced cut_recovery from heading jitter | All 10 | CB runs 90° or 180° during stem, drifts, overcorrects with 70-90° snap → recovery=3 |
| B4 | Never matches WR heading during stem | All 10 | "Mirror" interpreted as running perpendicular to WR, not parallel |
| B5 | Structural 1-step delay on every cut | All 10 | "Wait one step before reacting" was a hard rule, not a jab filter |
| B1 | Swat from physically impossible distances | All 10 | No distance gate; CB said "yes" to "can you realistically reach?" always |
| B2 | Always 5 yd cushion pre-snap | All 10 | Example JSON in cb_pre_snap.txt hardcoded offset_yards=5 |
| B6 | Swat intent declared but action stays "cover" | 3/10 | Intent mismatch: cb_pass2 fires "swat" but pass1 outputs "cover" |

The doom loop (B3+B4): CB runs at 90° during stem → lateral drift grows → panics, snaps 70-90° → recovery=3 → loses ground → repeats. By throw time CB is 4-18 yd from landing zone.

### Prompt Fixes

**cb_system.txt:**
- Replaced LATERAL MIRRORING section with BACKPEDAL — THE SHADOW MODEL: explicit heading ≈ 0° during stem, tiny tilts (5-10°) to track x, flip to WR's heading on cut
- FLIP TRIGGER: "2+ consecutive steps" → "holds even ONE step"
- DO NOT OVER-COMMIT: updated to match 1-step confirmation
- ZONE-OF-CONTROL: replaced "small adjustments cheap" with 20° threshold and commit-one-heading rule
- REACTIVE FREEDOM concept: keep cut_recovery=0 during stem so burst available in all directions
- KEY PRINCIPLE: replaced with shadow model summary (stem: heading ~0°, cut: flip immediately, ball: arm ≤ 2 yd → swat else play_man)

**cb_pass1.txt:**
- Added PHASE IDENTIFICATION block at top: STEM PHASE (heading ~0°, tiny tilts, not 90° or 180°) and CUT PHASE (match WR heading immediately, one decisive move)
- Added AT SNAP note: stationary WR is not an invitation to close
- Added REACTIVE FREEDOM: don't sprint toward WR, preserve burst in all directions
- STEP 0: changed to "20-30° tilt max to close lateral gap, NOT 90° snap"
- CONFIRMED CUT CHECK: 2+ steps → "even ONE step, 45°+ = real cut"
- PATIENCE RULE: jab = snaps back same step; real cut = holds 1 step → react now

**cb_pass2.txt:**
- Added DISTANCE CHECK before options: arm tip > 2 yd → play_man automatically; 1-2 yd → evaluate; ≤ 1 yd → swat/INT viable

### Curl-Only Test (GPT-5-nano, seed=42)

Old (Round 12): CATCH, sep=9.41 yd, CB 12 yd from landing zone, swat intent, cut_recovery=3 at t=0.9 from heading jitter  
New: CATCH, sep=2.58 yd, CB picks play_man correctly ("arm tip 2.5 yd > 2 yd, physically impossible"), zero self-induced recovery during 2.5s stem, CB backpedaling heading=0° every step

One remaining issue: at t=2.6 CB says "WR made a real cut to 270°" but WR heading was 180°. CB confused the bearing from its position to WR (WR is to its left = 270° bearing) with WR's actual new heading (180°). Corrected itself at t=2.7. The initial wrong step triggered cut_recovery=3 and cost ~1 yd.

## What's Open / Known Issues

### CB — mostly fixed, two residual issues
1. **Bearing vs heading confusion on curl break**: at the moment WR cuts to 180° (back toward QB), CB reports "WR cut to 270°" — reading its own bearing to WR's new position rather than WR's heading. One-step error then self-corrects. May need a note: "match WR's HEADING, not the bearing from your position to WR."
2. **180° flip always costs recovery**: the curl break (and any comeback-type route) forces CB to do a 180° heading reversal, which always triggers cut_recovery=3. Unavoidable physics. CB just needs to be close enough when it happens.
3. **Pre-snap still 5 yd off every route**: cb_pre_snap.txt example JSON has offset_yards=5 baked in. Not changed yet.

### WR — unchanged from Round 12
- post_corner INCOMPLETE: Window A fires on intermediate 45° phase, locks heading, terminal 315° never executes
- curl INCOMPLETE (old runs): QB misprojects WR heading=180° as going upfield
- slant PBU: likely irreducible geometry

## NEXT STEP
Run full 10-route suite with GPT-5-nano (seed=42) to get Round 13 baseline with CB fixes. Command:
```
.\.venv\Scripts\python.exe run_all_routes.py --seed 42
```
Then analyze: did CB self-induced recovery drop? Did play_man get used on routes where CB can't reach? Did the shadow model stick?
