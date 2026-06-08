# Problems — Full Run Analysis

## Round 8 Results (seed=42, qwen3:8b via Ollama)

> **Note:** 4 routes (slant, drag, corner, in) errored mid-run due to a Windows console encoding bug (Unicode chars in print statements). Those routes use Round 7 / GPT data and are marked accordingly.

| Route | Data | Outcome | Sep @ Catch | Notes |
|-------|------|---------|-------------|-------|
| post_corner | R8 Ollama | CATCH | 7.32 yd | p=0.70; WR executed fake correctly |
| comeback | R8 Ollama | DROP | 2.47 yd | WR facing=71° at catch (should ~180°) |
| go | R8 Ollama | DROP | 2.75 yd | WR ran fake-cut route instead of fly |
| double_move | R8 Ollama | PBU | 0.58 yd | QB 1 step late; parse error at t=1.0 |
| curl | R8 Ollama | PBU | 0.78 yd | WR 9-step lateral drift ≠ curl |
| zig | R8 Ollama | PBU | 1.27 yd | WR headed 180° (toward CB) during ball flight |
| slant | R7 GPT | PBU | 1.24 yd | No slant break; 0°/40° oscillation |
| drag | R7 GPT | CATCH | 4.02 yd | WR ran 90° sideline route, not drag; catch via CB gap |
| corner | R7 GPT | CATCH | 6.66 yd | CB 2-step freeze; WR fakes hallucinated |
| in | R7 GPT | INTERCEPTION | 0.45 yd | WR never ran cut; called on stem |

**Round 8 score (6 new routes): 1C / 2D / 3PBU**
**All 10 combined: 3C / 2D / 4PBU / 1INT**

Regression vs Round 7 (3C / 1D / 3PBU / 1INC / 1INT / 1SACK): completion count holds at 3 but quality is worse — the 3 catches include 2 from old GPT data and the one genuine Ollama catch (post_corner) had p=0.70 (not clean).

---

## FIXED IN ROUND 8

### ✅ S3 — CB freeze removed
CB acts from t=0.0 on all R8 routes. No more 3-step pre-snap freeze. Confirmed by every new replay.

### ✅ S4 / P1 — cut_recovery field in replay JSON
`cut_recovery` is now present in per-player JSON snaps. Agents in R8 replays actively cite it: WR on double_move ("CB rec=1, snap to break"), zig ("CB rec=1, burst hard"), post_corner ("CB rec=3, call now"). The physics signal is now observable and acted on. This was the biggest structural fix.

### ✅ S5 — QB post-throw reasoning is "ball in air" stub
QB now emits `"ball in air"` after releasing — still a stub but no longer copies the throw-decision text. Not a active bug anymore.

---

## NEW ISSUES (Round 8)

### N1 — Parse error rate is unsustainably high with qwen3:8b (CRITICAL, ALL R8 ROUTES)

| Route | WR errors / calls | CB errors / calls | QB errors / calls |
|-------|-----------------|-----------------|-----------------|
| curl | 5 / 29 (17%) | 3 / 30 (10%) | 0 / 21 |
| post_corner | 5 / 25 (20%) | 5 / 26 (19%) | 0 / 17 |
| double_move | 0 / 16 | 4 / 16 (25%) | 1 / 9 (11%) |
| go | 2 / 19 (11%) | 2 / ~15 (13%) | 0 / 2 |
| comeback | 0 / 25 | 3 / 30 (10%) | 0 / 25 |
| zig | 1 / 16 (6%) | 0 / 17 | 0 / 9 |

Failures land at worst possible moments: CB parse error at comeback t=2.7 (WR call step), double_move QB parse error at t=1.0 (step before critical throw), post_corner CB parse error at t=1.8 (WR call step).

The engine falls back to the prior action on parse failure — this is silent degradation. With GPT (gpt-5-nano), parse errors were rare because `response_format=json_object` was enforced. Ollama/qwen3:8b has no JSON-mode equivalent in the current integration, so the model occasionally produces prose when it should produce JSON.

---

### N2 — WR executes the wrong route shape (CRITICAL, MOST ROUTES)

The WR understands deception tactics in the abstract but confuses or ignores the route geometry:

| Route | Required shape | Actual shape |
|-------|---------------|-------------|
| go | Straight upfield, no cut | 270° fake-cut at t=0.2–0.4, ball thrown 1.7 yd upfield |
| slant | Sharp diagonal cut across field (90°) | 0°/40° alternation; y: 50→64, x: 16→20 (seam, not slant) |
| in | Stem upfield → hard 90° inside | Straight 0° entire play, called on stem |
| zig | Phase 3 break = 90° rightward | Body heading 180° (toward CB) throughout ball flight |
| curl | Upfield stem → 180° hook | 9-step 270° lateral drift, 5.5 yards sideways; never hooked |
| drag | Flat cross toward QB | 90° toward right sideline the entire play |

Root cause: the WR prompt gives the WR freedom to choose deception moves but does not enforce the geometric skeleton of the route (where the phases must go). The model defaults to a generic "fake-then-break" strategy and picks whatever fake direction feels opportunistic, regardless of whether it matches the route shape.

---

### N3 — WR facing hallucination during ball flight causes drops and PBUs (CRITICAL)

| Route | Required facing | Actual facing | Consequence |
|-------|----------------|--------------|------------|
| comeback | ~180° (toward QB bearing ~69°) | 71° (northeast) | DROP — catch probability crushed |
| zig | ~90° (toward landing zone) | 180° (toward CB) | PBU — WR ran toward CB, away from ball |
| post_corner | ~143° (bearing to QB) | 270° (pure left) | p_catch degraded to 0.70 |
| go | 0° (upfield to catch) | 180° (back toward QB) claimed but contradicted | Contested catch |

The WR consistently miscalculates the bearing to the QB or the landing zone during ball flight. Facing is treated as a simple cardinal direction ("facing 180° = looking at QB") rather than computed from actual (x, y) positions. This is a geometry computation failure on every single route.

---

### N4 — WR's CB-commit trigger is phantom scaffolding (HIGH, ALL ROUTES)

The WR waits for "CB rec > 0" as the trigger to break. This was intended to be the cut_recovery fix (S4). However:

1. **The CB's cut_recovery is not in the WR's observation space.** The WR cannot see `CB.cut_recovery`. It is inferring this from CB heading changes, but the inference is unreliable.
2. **Comeback**: WR held the 270° fake for 16 steps waiting for "CB rec > 0" — which never fired because the CB was smoothly tracking (no sharp cuts = no recovery penalty). WR broke at t=1.7 without acknowledging the exit condition failed.
3. **Double_move**: At t=0.7 the WR declared "Fake right failed to commit CB (heading 149°)" when CB heading 149° + rec=1 is exactly a committed CB. The WR misread success as failure.
4. **Drag**: WR cites "CB rec=0" and "CB rec>0" as if reading a sensor value — this field does not exist in WR's observation.

The WR prompt needs to clarify what observable signals indicate CB commitment (heading delta, consecutive steps in same direction) rather than relying on a field it cannot see.

---

### N5 — WR has no escalation counter; gets stuck in fake loops (HIGH)

| Route | Loop behavior | Duration | Consequence |
|-------|--------------|----------|------------|
| comeback | 270° lateral fake, waiting for CB rec | 16 steps / 1.5s | CB never committed, WR broke on wrong signal |
| curl | 270° lateral fake | 9 steps / 0.9s, 5.5 yards lateral | Route became a drift, not a curl |
| in | 20° left jab, repeated | 4 times at t=0.1/0.5/0.6/0.7 | No escalation; cut never run |
| slant | 0°/40° oscillation | 2.4s | No separation; CB never misled |

The WR evaluates each step independently. It has no "I have been doing X for N steps with no result — time to escalate or change strategy." Every step the cheap repetitive option wins over the costly commitment. Until there is a step-count or time-budget signal, the WR will keep looping.

---

### N6 — QB one-step delay costs completions (HIGH)

- **double_move**: Peak separation 5.02 yd at t=0.8. WR called at t=0.8. QB threw at t=1.1 (one step late due to parse error at t=1.0). CB closed from 3.7 yd to 0.58 yd. Outcome: PBU. An on-time throw at t=0.9 would have given WR a 3+ yd lead.
- **curl**: WR called at t=2.3 (sep=0.78 yd), CB closing at 4.25 yd/s. QB threw at t=2.4. One step earlier (t=2.2, when WR snapped to 180° and CB was still at rec=1) would have beaten the CB.
- **zig**: QB correctly held through the fake; but once WR called, body was at heading 180° (not 90°) — QB threw at the wrong WR state.

The QB is reactive to the WR_CALL signal but does not anticipate the ideal throw window independently. On short-window plays, 0.1s matters.

---

### N7 — CB over-commits to fake direction, no route anticipation (HIGH, MOST ROUTES)

| Route | CB failure |
|-------|-----------|
| zig | After 3 steps of 270°: "Confirmed left cut." Stops hedging entirely. WR snaps to different direction and CB is fully committed. |
| double_move | Never analyzes the double-move threat; treats rightward fake as real route until WR breaks back |
| corner | 2-step freeze after WR cut (t=2.2–2.4); still backpedaling when throw released at t=2.4 |
| post_corner | Declares "confirmed cut to 45°" then takes heading=4° cut (rec=3) at t=1.7 — exactly when WR executes Phase 3 break to 315° |
| curl | Follows WR's 9-step lateral drift all the way left; no rotation back when curl time arrives |

The CB has good angle-tracking but no concept of route shapes or fake structures. It can track where the WR is going right now but cannot predict where it will go next based on route phase logic. "N consecutive steps in same direction" is sufficient for the CB to declare a real cut and abandon all hedging.

---

### N8 — CB geometric hallucinations (MEDIUM, MULTIPLE ROUTES)

- **post_corner t=0.2**: CB responds to "lateral drift" that does not exist in the data (WR x=16.0 at both t=0.1 and t=0.2).
- **post_corner t=0.6**: CB sets heading 180° (downfield) claiming "intercept" while WR is accelerating upfield at 6.39 yd/s.
- **corner t=0.7**: CB sets heading 80° (sideways) while reasoning says "maintain cushion."
- **corner t=1.4**: CB heading 270° (pure lateral) while WR is running straight upfield.

The CB computes WR deltas incorrectly and sometimes invents movement that isn't there. This drives heading errors that burn burst via cut_recovery.

---

## UPDATED SYSTEMIC ISSUES

### S1 — WR hallucination has changed form (HIGH, PERSISTS)

The "jabbed left last step" boilerplate (Round 7) is gone from new Ollama routes. However, the underlying problem has mutated:
- Route confusion (N2): WR fabricates a route shape that wasn't called
- Phantom signals (N4): WR cites "CB rec" as a sensor when it isn't observable
- Facing geometry (N3): WR claims facing X° when actual facing output is different

Hallucination is still present; it has migrated from deception-history fabrication to state-reading fabrication.

### S2 — CB template-locked reasoning (HIGH, PERSISTS)

Round 7 template: "WR is still approaching and I want to keep cushion while watching for the cut"
Round 8 template (corner R7 data): Same string, 14/20 steps

qwen3:8b produces different boilerplate but the same behavioral pattern: the CB generates situationally generic reasoning that doesn't update on new observations. The CB at t=2.3 in the corner replay uses the same template as t=0.3, even though the WR has just cut and the ball is in the air.

### S6 — Parse errors at critical moments (now N1, severity upgraded to CRITICAL)

Rate has increased significantly with qwen3:8b vs GPT. See N1.

### W1 — WR calls for ball before completing route cut (PERSISTS)

- **In**: Called at t=0.8 heading 0° (never ran the cut)
- **Zig**: Called at t=1.1 while body was heading 180° (wrong direction)

### W2 — WR heading / facing wrong after calling (PERSISTS, NEW FORM)

Was: heading change after calling. Now also: facing mismatch during ball flight (N3). Comeback dropped because facing=71° at catch. Zig PBU'd because body kept heading 180° (toward CB) during ball flight.

### W3 — WR never executes the actual route (PERSISTS)

Same as Round 7. go, in, slant, curl, drag, zig all show wrong route shapes. N2 is the full characterization.

### W4 — Jab fakes too shallow (PERSISTS)

Corner replay (R7): x-position frozen at 16.0 throughout stem, but WR claims 14 jabs. Zero physics execution.

### Q1 — QB throws without WR call on go route (RESOLVED / CHANGED)

Round 7: QB freelanced at t=0.8 without any call.
Round 8: QB held correctly and waited. WR eventually called (at t=0.5 — too early after self-inflicted cut). The issue has shifted — QB now waits, but WR calls prematurely on a botched route.

### Q4 — QB template-locked during broken play (PERSISTS)

Boilerplate hold reasoning for 7–20 consecutive steps in all routes. QB is a passive relay — it waits for WR_CALL_FOR_BALL and doesn't independently read the field. Never references CB position during hold phase on any route.

### P3 — detected_cut_t fires on jabs (PERSISTS)

- In: `detected_cut_t: 0.7` on a 20° jab (still Round 7 data)
- Slant: `detected_cut_t: 0.1` on early oscillation

---

## MASTER ISSUES TABLE

| ID | Problem | Routes Affected | Severity | Status |
|----|---------|----------------|----------|--------|
| S1 | WR hallucination (mutated: phantom signals, route confusion, facing fabrication) | ALL | HIGH | OPEN — new form, same root |
| S2 | CB template-locked reasoning | ALL | HIGH | OPEN — persists across models |
| S3 | CB frozen 3 steps at pre-snap | ALL | — | ✅ FIXED R8 |
| S4 | cut_recovery absent from replay JSON / agents blind to physics | ALL | — | ✅ FIXED R8 |
| S5 | QB reasoning copy-pasted post-throw | ALL | — | ✅ MITIGATED (now "ball in air" stub) |
| S6 | Parse errors at critical moments | ALL | CRITICAL | OPEN — 10–25% failure rate with qwen3:8b |
| N1 | (see S6) Parse error rate unsustainable with qwen3:8b | ALL R8 | CRITICAL | NEW |
| N2 | WR executes wrong route shape (go, slant, in, zig, curl, drag) | 6/10 | CRITICAL | NEW |
| N3 | WR facing hallucination during ball flight causes drops | comeback, zig, post_corner, go | CRITICAL | NEW |
| N4 | WR's CB-commit trigger ("CB rec > 0") is unobservable phantom | ALL | HIGH | NEW |
| N5 | WR has no escalation counter; loops fake indefinitely | comeback, curl, in, slant | HIGH | NEW |
| N6 | QB one-step delay costs completions | double_move, curl | HIGH | NEW |
| N7 | CB over-commits to fake; no route anticipation | zig, double_move, corner, post_corner, curl | HIGH | NEW |
| N8 | CB geometric hallucinations (invents WR lateral drift) | post_corner, corner | MEDIUM | NEW |
| W1 | WR calls for ball pre-cut or mid-cut | in, zig | CRITICAL | OPEN |
| W2 | WR heading/facing wrong after calling for ball | comeback, zig, post_corner | CRITICAL | OPEN — now also affects facing |
| W3 | WR never executes the actual route geometry | go, slant, in, curl, drag, zig | HIGH | OPEN |
| W4 | WR jab fakes too shallow; no physics execution | corner, in, slant | HIGH | OPEN |
| C1 | CB no lateral coverage during stem | ALL | HIGH | OPEN |
| C2 | CB 2–6 step react delay after cut | corner, curl, post_corner | HIGH | OPEN |
| C3 | CB intent randomly assigned — not position-aware | ALL | MEDIUM | OPEN |
| C4 | CB speed locked at 6.75 in backpedal | SOME | LOW | OPEN |
| Q1 | QB throws without WR call — go route | go | HIGH | CHANGED — QB now waits; WR calls on wrong heading |
| Q2 | QB throw geometry errors on angled routes | slant | HIGH | OPEN |
| Q3 | QB lead calc ignores WR cut-recovery speed arc | SOME | MEDIUM | OPEN |
| Q4 | QB template-locked during hold phase | ALL | HIGH | OPEN — boilerplate hold for 7–20 steps every route |
| P3 | detected_cut_t fires on jabs | in, slant, drag | MEDIUM | PERSISTENT |

---

## WHAT'S WORKING

1. **CB freeze removed (S3)** — CB acts from t=0. Confirmed all R8 routes.
2. **cut_recovery in replay JSON (S4)** — Field present; agents cite it and act on it.
3. **WR recovery-aware break timing** — On double_move, zig, post_corner, WR correctly waited for CB rec > 0 before breaking. The CB-commit logic is structurally sound, even if the trigger signal is imprecise.
4. **Post_corner catch (7.32 yd)** — The only clean R8 Ollama catch. WR correctly executed 3-phase route (stem→fake→break). CB paid cut_recovery cost at the right moment. Full route completed as designed.
5. **Double_move fake mechanics** — WR correctly bit the fake, CB committed (rec=1), WR snapped back. The separation window (5.02 yd) was real and earned. Play failed from QB latency, not route failure.
6. **QB holds for WR call** — Still working (5/6 R8 routes, Q1 also fixed). No more freelance throws.
7. **Dynamic burst physics** — WR speed ramps (1.4 → 9.5 yd/s) and cut penalties are correct and consistent.
8. **CB aggressive close-out when exploitation window opens** — double_move CB closed from 3.7 → 0.58 yd correctly; corner CB reached landing zone for PBU.

---

## ROOT CAUSE HIERARCHY

**Tier 1 — blocks most completions:**
1. **WR route shape confusion (N2)** — WR ignores route geometry. On 6/10 routes the WR executes a different route than called. Without correct shape execution, deception, timing, and QB lead are irrelevant. Fix: inject explicit per-phase heading constraints into scenario YAML and enforce them in the WR pre-snap observation.
2. **WR facing hallucination during ball flight (N3)** — Every ball-in-air phase with qwen3:8b shows wrong facing. Fix: compute and inject the QB bearing explicitly in the observation rather than letting the model estimate it.
3. **Parse error rate with qwen3:8b (N1/S6)** — 10–25% of calls fail to produce JSON. Retry logic exists but consecutive failures leave agents on autopilot. Fix: enforce JSON via system prompt ("respond only with a JSON object") or switch to a model with more reliable structured output.

**Tier 2 — converts open windows into incompletions:**
4. **WR phantom CB-commit trigger (N4)** — WR is waiting for a signal it cannot observe. Fix: replace "wait for CB rec > 0" with observable proxy: "if CB heading has shifted >90° from initial in the last N steps, break."
5. **WR escalation loop (N5)** — WR repeats cheap fakes indefinitely. Fix: add a step-count to the WR scratchpad; after N steps of same fake, force commit to the real cut.
6. **CB over-commitment / no route anticipation (N7)** — CB correctly closes but cannot predict route shapes. Fix: after N consecutive steps in same direction, CB should begin hedging toward the route's most likely break direction rather than continuing to mirror.

**Tier 3 — degrades quality on plays that otherwise work:**
7. **QB hold-phase boilerplate (Q4)** — QB never reads CB position independently. Plays where WR calls correctly still get narrow windows because QB doesn't anticipate. Fix: QB should output at minimum: current CB distance to WR, whether separation is growing or shrinking, and whether it should be pressuring the WR to call sooner.
8. **QB one-step delay (N6)** — On short-window plays, QB needs to throw within 0–1 step of WR call, not 2. Fix: QB throw decision should fire within the same step as the WR call when separation meets threshold.

---

## APPENDIX — Round 7 Results (seed=42, gpt-5-nano, pre-Round-8-fixes)

| Route | Outcome | Separation | Notes |
|-------|---------|-----------|-------|
| slant | PBU | 1.24 yd | WR oscillated headings every step, no real route; QB throw geometry off |
| comeback | CATCH | 9.36 yd | CB ran itself out of play; misleading success |
| go | INCOMPLETE | 2.26 yd | WR never called; QB threw without call, 1.0 yd lateral error |
| curl | DROP | 2.31 yd | WR changed heading after calling; CB template-locked |
| zig | PBU | 0.75 yd | Spurious 0° step at t=0.9 caused double cut penalty; WR slow at call |
| drag | CATCH | 4.02 yd | WR fake hallucinated; CB frozen 3 steps; catch despite bad execution |
| corner | CATCH | 6.66 yd | CB pure backpedal; WR cut to wrong angle (290° not 315°) |
| post_corner | PBU | 1.54 yd | CB ignored 45° fake; QB throw geometry wrong for 315° route |
| in | INTERCEPTION | 0.45 yd | WR never ran the cut; called for ball on stem heading 0° |
| double_move | SACK | — | WR broke out of bounds; QB template-locked for 2.9s |

**Round 7 score: 3C / 1D / 3PBU / 1INC / 1INT / 1SACK**

Round 7 fixes applied to Round 8:
- S1 (WR boilerplate): patched in wr_live_free.txt / wr_system.txt
- S3 (CB freeze): removed t >= 0.3 guard in runner.py ✅
- S4 (cut_recovery in JSON): added to _player_snap() ✅
- S5 (QB post-throw copy-paste): QB now emits "ball in air" stub ✅
- S6 (empty response retry): added retry in call_llm ✅
- Q2/Q3 (QB lead with recovery): qb_agent.py _build_options() now includes recovery-aware projections
- W1 (WR call criteria): strengthened in wr_live_free.txt
- W4 (jab depth): minimum 60–90° jab depth guidance added
- C1/C2 (CB lateral coverage): lateral mirroring and flip-trigger guidance added to cb_system.txt
