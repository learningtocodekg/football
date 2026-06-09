# Left Off
Date: 2026-06-09

## What We Worked On
Round 13: ran full 10-route suite (GPT-5-nano, seed=42) to baseline the CB prompt overhaul from last session. Confirmed results. User declared ready to move to 3D.

## What Got Done

### Round 13 Full Run — 7C/2PBU/1DROP

| Route | Result | Sep @ resolution | CB intent |
|-------|--------|-----------------|-----------|
| slant | CATCH | 2.18 yd | play_man |
| comeback | CATCH | 2.76 yd | play_man |
| go | PBU | 1.84 yd | swat |
| double_move | CATCH | 4.81 yd | play_man |
| curl | CATCH | 2.50 yd | play_man |
| zig | CATCH | 3.97 yd | play_man |
| drag | CATCH | 4.35 yd | play_man |
| corner | PBU | 1.27 yd | play_man |
| post_corner | DROP | 1.0 yd | swat |
| in | CATCH | 2.42 yd | play_man |

vs Round 12 (7C/1PBU/2INC): same catch count, 2 INC → 1PBU + 1DROP.

**CB shadow model confirmed working at scale:**
- play_man on 8/10 routes — distance gate working (arm tip >2 yd → play_man, no further evaluation)
- No doom loop (self-induced cut_recovery from heading jitter) on any route
- Separation at throw time 2–4 yd range vs 9+ yd in Round 12

## What's Open / Known Issues

1. **go PBU** — no cuts, CB runs WR down. Sep=1.84 at arrival, swat. Probably irreducible geometry on a pure vertical with the CB now actually tracking.
2. **corner PBU** — sep=1.27 yd, CB correctly played play_man. QB's own telemetry said "contested" but threw anyway. QB decision failure, not CB or WR.
3. **post_corner DROP** — sep=1.0 yd, CB swat. Still the Window A timing bug: WR calls on intermediate 45° phase, terminal 315° break never executes. Heading locks at 45°.
4. **CB pre-snap 5 yd every route** — cb_pre_snap.txt example JSON hardcodes offset_yards=5. Not fixed.
5. **CB bearing vs heading** — on curl break, CB briefly reads "WR cut to 270°" instead of 180°. Self-corrects next step. 1-step error.

## NEXT STEP
Move to 3D. The 2D sim has reached a stable plateau: 7C on most routes, CB doom loop eliminated, WR multi-phase timing mostly fixed. The remaining failures (go geometry, QB decision quality, post_corner Window A) are worth carrying into 3D where vertical separation, jump timing, and ball trajectory add new dimensions.
