# Left Off
Date: 2026-06-06

## What We Worked On
Run 4: all 10 A4 routes with seed=42 (OpenAI gpt-5-nano), full analysis of which problems from problems2.md and problems3.md are still present vs fixed.

## What Got Done

### Run 4 results (seed=42, gpt-5-nano)
| Route | Result |
|-------|--------|
| slant | PBU |
| comeback | CATCH ✓ |
| go | DROP |
| double_move | CATCH ✓ |
| curl | DROP |
| zig | CATCH ✓ |
| drag | CATCH ✓ |
| corner | PBU |
| post_corner | PBU |
| in | INTERCEPTION |

**Score: 4 CATCH, 2 DROP, 3 PBU, 1 INT** (up from Round 3: 2C/6D/1PBU/1INT — improvement)

### Problem audit against problems2.md + problems3.md

**FIXED:**
- N3 (comeback QB lead inverted) — CATCH two runs in a row.
- N4 (double_move early fake exit) — WR held 90° correctly through t=2.0+. CATCH.
- O5 (double_move WR runs east during fake) — clean this run.
- O6 (post_corner 0.7s call delay) — reduced to 0.1s delay.
- O8 (drag QB lead lateral) — CATCH, QB led correctly.

**STILL BROKEN:**

**P-NEW (HIGH) — WR calls for ball before executing the route cut.**
Dominant failure this run. Slant (PBU), corner (PBU), in (INT), curl (DROP) all failed because the WR called `call_for_ball=true` while still running 0° upfield, before the cut was executed. The `call_tolerance` validation in runner.py requires heading within ±45° of `cut_heading`, but this only fires AFTER the decision — need to investigate whether this gate is actually enforced.
- slant: called t=1.0 @ hdg=0° (cut window ~2.0s, cut hdg ~315°)
- corner: called t=0.5 @ hdg=0° (cut window ~2.5s, cut hdg ~290°)
- in: called t=0.8 @ hdg=0° (cut window ~1.8s, cut hdg ~270°)
- curl: called t=0.9 @ hdg=0° (cut window ~1.8s, cut hdg ~180°)

**O7/N2 (HIGH) — Cookie-cutter 330°/30° jabs still on all routes.** Every route: 10-20 tiny alternating jabs off 0°. CB ΔHdg ≈ 0 on every fake. Deception produces zero separation. MOVE LOG didn't break the habit.

**O1 (MEDIUM) — Ball-in-air heading abandonment still present.** Drag: hdg reversed to 276° mid-flight. Zig: hdg drifted to 196°/202° during flight. Both still resulted in CATCH due to CB distance, but the bug is live.

**O4 (MEDIUM) — Slant WR never crosses field.** Compounded by P-NEW (called before executing any slant direction). WR treats slant as a go route with a prematurely called ball.

**N6/O3 (MEDIUM) — Go route QB threw lob again.** QB used lob/medium speed to (14.2, 57.5) on a deep route. WR overran. Need bullet default for go.

## What's Open / Known Issues
- P-NEW: pre-cut calling is now the #1 failure. Affects 4 routes directly.
- O7/N2: jab template unchanged across all 10 routes.
- O1: ball-in-air heading change still present (latent failure).
- O4: slant cut direction still misread.
- N6/O3: go route QB still throws too slow.
- detected_cut_t fires on first heading hold, not real route break.
- CB intent is always "swat" (except in route where it correctly chose go_for_pick and got the INT).

## NEXT STEP

**Diagnose P-NEW first**: check runner.py `call_tolerance` enforcement — does the ±45° heading gate actually reject pre-cut calls? Read [sim/runner.py] to find where `wr_called_for_ball` is set and whether call_heading validation blocks premature calls. If the gate isn't working, fix it. If it IS working, then these calls (slant @ hdg=0°, in @ hdg=0°) are somehow passing the ±45° check — which means cut_heading is 0° or the gate logic is wrong.

Then fix O7/N2 with the explicit angle blacklist (ideas in problems3.md: "JABS USED THIS PLAY: 330° (×4). DO NOT use 330° again. Pick a different angle.").
