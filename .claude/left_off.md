# Left Off
Date: 2026-06-09

## What We Worked On
Round 12: Two targeted prompt fixes to `wr_live_free.txt` addressing the two root WR failures from Round 11. Then ran the full 10-route suite (GPT-5-nano) to get a Round 12 baseline.

## What Got Done

### Prompt changes (`agents/prompts/wr_live_free.txt`)

**Fix 1 — CB rec quality check (MOVE LOG section)**
Added GENUINE COMMIT vs TRACKING WOBBLE distinction:
- Genuine commit: CB heading in the 2-3 steps before rec appeared was significantly different from break direction (CB was running wrong way, had to turn hard).
- Tracking wobble: CB heading was approximately same as WR (following, headings within ~45°). Still positioned to contest. Not a window.
- Tells WR to check the last 2-3 CB headings before rec appeared. If CB was running same direction as WR → tracking noise, not commitment.

**Fix 2 — Route phase check in CALL RULES (STEP 0)**
Added explicit phase check at top of CALL RULES:
- If "YOUR HEADING NOW" shows "~Xs remaining, then cut to Yd" → intermediate phase, do NOT call regardless of CB state.
- If it shows "this is your final break. Run it." → now evaluate calling.

### Round 12 full run: 10 routes, GPT-5-nano, seed=42
**7C / 1PBU / 2INC — best GPT score to date (prev best: 4C/1D/2PBU/1INC/1INT in Round 5)**
0 parse errors across all agents.

| Route | Outcome | call_t | Notes |
|---|---|---|---|
| slant | PBU | 2.2 | Full stem; CB swat at 1.08 yd — physics |
| comeback | CATCH | 2.4 | Clean |
| go | CATCH | 1.0 | Clean |
| double_move | CATCH | 1.4 | Was t=0.1 call in R11 |
| curl | INCOMPLETE | 2.5 | WR correct (180°); QB threw behind WR (y=68.4 vs WR at y≈67.5 heading back) |
| zig | CATCH | 1.3 | Clean |
| drag | CATCH | 1.1 | Was PBU in R11 |
| corner | CATCH | 2.7 | Clean |
| post_corner | INCOMPLETE | 2.2 | WR used Window A before terminal 315° break; heading locked at 45° |
| in | CATCH | 2.2 | Clean |

## What's Open / Known Issues

### WR — mostly fixed, two remaining issues
1. **post_corner INCOMPLETE**: Window A misfires on multi-phase routes. WR correctly says "final cut in 0.2s, calling now" but calling locks heading at the CURRENT (intermediate) heading, preventing the terminal break. Window A should only fire when there are no more cuts coming.
2. **slant PBU**: Full stem executed (t=2.2), CB still swats at 1.08 yd. Likely physics — slant geometry puts CB in a natural swat position. May be irreducible.
3. **curl INCOMPLETE**: WR correct. QB targeting bug — QB projects WR on heading=180° as going upfield (positive y) instead of back toward QB (negative y).

### CB — BROKEN (newly visible now that WR works)
- **Always picks swat** (10/10 routes), and routinely admits in reasoning it's too far to reach the ball (arm tip 3-5 yd from ball path). Never picks play_man even at close range.
- **Always plays 5 yd off-coverage** every pre-snap, never presses.
- **Self-induces recovery** from its own minor tracking adjustments (2-4 times per route), killing burst when it needs to close.
- **Root cause**: Patience doctrine tipped into passivity. The CB was this broken before, but the WR was failing so badly (calling at t=0.1, wrong headings) that the CB never had to cover well. Now WR executes cleanly, CB weaknesses exposed.

## NEXT STEP
Fix the CB. The patience doctrine needs a concrete danger model — the CB has no concept of what "losing coverage" looks like. Needs to understand: swat from 5+ yd is worthless, soft 5-yd cushion every snap isn't a strategy, and self-inducing recovery from tracking adjustments kills closing burst. Prompt guidance, not hardcoded behavior.
