# Left Off
Date: 2026-06-09

## What We Worked On
Round 11: WR call-timing overhaul. The WR was calling at t=0.0 because pre-snap cushion (CB starts 5 yd off) immediately satisfied the "body gap >= 1.5 yd" rule. Fixed the observation and prompt, ran all 10 routes with Ollama, dispatched 10 subagents for route-by-route WR analysis, updated problems.md.

## What Got Done

### Observation changes (`agents/observation.py`)
- **Removed editorial "VERY OPEN / OPEN / GAP / CONTESTED" labels** — these were telling the WR the conclusion instead of the facts. The WR read "VERY OPEN" at t=0 and called immediately.
- **Replaced with CB orientation hint**: when CB rec=0, show `"CB hips at X° (label), N° away from your position — advantageous angle"` or `"CB hips at X°, squared toward you — CB is set and mobile"`. Facts only, no conclusion.
- **Removed "THIS IS YOUR WINDOW — explode now"** from the HIP-TURNED alert → now says `"CB is committed and cannot change direction freely yet."` Let the WR decide what to do with that.
- **Changed CALL FOR BALL line**: from "signal when body gap >= 1.5 yd" to "0.1-0.2s before your final cut (anticipatory) OR immediately after that cut when CB rec > 0. Pre-snap cushion is not earned separation."

### Prompt changes (`agents/prompts/wr_live_free.txt`)
- **Rewrote point 5 (Separation)**: explains WHY pre-snap gap isn't separation ("CB has FULL BURST and can close. The pre-snap cushion is NOT earned separation. You have done nothing yet."), defines TRUE separation as gap the CB physically cannot close because hips are committed wrong.
- **Rewrote point 6 (When to call)**: two explicit windows only — Window A (0.1-0.2s before final cut) and Window B (just after final cut with CB rec > 0). Added the WHY for not calling during stem: "during the stem the CB is reading you and tracking upfield. If you cut early (before the stem commits their hips), they have FULL BURST and can mirror your break."
- **Rewrote CALL RULES block**: "Pre-snap body gap is NOT a valid call signal. Body gap only matters AFTER the stem has pulled the CB upfield and you have made your break."

### Memory / CLAUDE.md
- Created `memory/feedback_no_phase_gate.md` — never recommend phase-gate on WR call timing
- Updated `CLAUDE.md` section 5: when user shuts down an approach, ask explicitly before re-raising it

### Round 11 Results (Ollama qwen3:8b, seed=42)
7C / 3PBU — up from Round 10 (4C/1INC/5PBU with GPT, different model so not perfectly comparable)

| Route | Outcome | WR call_t | Key finding |
|-------|---------|-----------|-------------|
| slant | PBU | t=0.6 | Stem only 30% complete; CB minor wobble triggered call |
| comeback | CATCH | t=1.2 | Stem 48% done; broke to 270° (wrong dir), not 180° comeback |
| go | CATCH | t=1.2 | Clean straight route; CB self-induced recovery opened window |
| double_move | CATCH | t=0.1 | 1 step of stem; hallucinated CB rec>0 to justify call |
| curl | PBU | t=1.1 | Stem 44%; never ran 180° hook; called on stem heading |
| zig | CATCH | t=0.5 | Jab lasted 1 step; Phase 3 snap-right never executed |
| drag | PBU | t=0.7 | Route shape OK; call at cut → WR recovery delay → CB closed |
| corner | CATCH | t=1.1 | Improvised fake in wrong direction (270° not 90° inside) |
| post_corner | CATCH | t=1.1 | Treated 45° fake as catch heading; 315° never ran |
| in | CATCH | t=1.1 | CB had 6 consecutive parse errors; 90° cross never ran |

## What's Open / Broken

### Root problem (unchanged)
The WR's call trigger fires the moment ANY CB recovery event appears — including trivial tracking adjustments. CB makes a 1-step heading wobble to stay with the WR → WR reads this as "hip committed" and calls immediately, even if the stem is 20-50% complete. On every route, CB entered minor recovery from its own motion, not from genuine hip-commitment caused by a well-run stem.

### Multi-phase routes: terminal phase consistently skipped
On double_move, zig, post_corner, in — the WR called on an intermediate phase and never ran the final break. The WR treats "first cut I make = catch heading." The setup phase is not understood as a setup.

### Break direction wrong on some routes
Comeback: broke to 270° (sideline juke) not 180° (comeback to QB). Corner: improvised 270° fake instead of inside fake at ~90°. Post_corner: called at 45° (fake) not 315° (corner).

### qwen3:8b parse errors degrading CB quality
CB had 3-6 parse errors per route, which inflated some WR results (in: 7.7 yd sep is entirely CB parse failure, not WR execution).

## NEXT STEP
The WR now understands pre-snap cushion ≠ separation. The remaining failure is that it treats any CB recovery as "hip committed." Add to the prompt: the WR should distinguish between (1) CB rec caused by the stem working — CB was running upfield with momentum and now has to reverse — vs (2) CB rec from a minor tracking adjustment where the CB is still oriented correctly to chase the break. The signal for a genuine commit is that the CB was heading significantly *away* from the WR's final break direction before entering recovery. Mild 1-step wobble while tracking = not a window. CB sprinting the wrong way + entering recovery = real window.
