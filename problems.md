# Problems — Full Run Analysis

---

## CURRENT STATE (post-Round 11 — Ollama qwen3:8b, seed=42, new observation + prompt)

### Round 11 Results

| Route | Outcome | Sep @ resolution | WR call_t | CB rec at call | Notes |
|-------|---------|-----------------|-----------|---------------|-------|
| slant | PBU | 1.0 yd | t=0.6 | rec=2 | Stem only 0.6s of 2.0s; CB mild recovery, not genuine hip commit |
| comeback | CATCH | 3.26 yd | t=1.2 | rec=2 | Stem 1.2s of 2.5s; broke to 270° (sideline juke) not 180° (comeback) |
| go | CATCH | 3.06 yd | t=1.2 | rec=0 | Ran straight upfield correctly; CB self-induced recovery opened window |
| double_move | CATCH | 3.6 yd | t=0.1 | rec=0 | **1 step of stem**; hallucinated CB rec>0 to justify call; CB rec was 0 |
| curl | PBU | 2.36 yd | t=1.1 | rec=1 | Stem 1.1s of 2.5s; never executed 180° hook; called on stem heading 0° |
| zig | CATCH | 3.77 yd | t=0.5 | rec=1 | Stem 0.5s of 1.0s; jab lasted 1 step; Phase 3 (snap right 90°) never ran |
| drag | PBU | 1.35 yd | t=0.7 | rec=1 | Route shape OK; call at cut → WR recovery → QB waited → CB closed |
| corner | CATCH | 2.18 yd | t=1.1 | rec=2 | Improvised 270° fake (wrong dir: should be inside ~90°); QB 4 parse errors, 0.7s late |
| post_corner | CATCH | 2.11 yd | t=1.1 | rec=0 | Treated 45° (fake phase) as catch heading; 315° (corner) never run |
| in | CATCH | 7.7 yd | t=1.1 | rec=3 | Never ran 90° cross; CB had 6 consecutive parse errors = CB was frozen |

**Round 11 score: 7C / 3PBU** — up from Round 10 (4C/1INC/5PBU). Ollama vs GPT, so not directly comparable, but structural improvement is real.

**What drove the improvement:** Pre-snap cushion no longer triggers instant call (most routes). WR now holds stem for at least a few steps before calling.

**What the catches actually mean:** Of 7 catches, only 2-3 represent genuine route execution (comeback is borderline, go is clean). The others won because: CB had parse errors (in: 6 consecutive, go, double_move), or positional gap from stem was large enough to survive a short stem + fast QB throw. The routes were not run correctly — they succeeded despite that.

---

### New Round 11 Issues

#### R11-W1 — CB rec fires as premature trigger on ANY CB motion (CRITICAL)
The WR calls the moment CB rec > 0, regardless of what caused the CB to enter recovery. On every route, the CB entering even a 1-step recovery from its own heading adjustment triggers an immediate WR call — even if the stem is only 20-50% complete. The WR is not distinguishing between "CB genuinely committed the wrong way from my stem" and "CB made a minor lateral step and has a 1-step wobble." Fix: the WR needs to understand that CB rec is only a valid window if the CB was committed in the wrong direction *before* entering recovery — not just any transient recovery state.

#### R11-W2 — Stems terminated 40-80% too early on all routes (CRITICAL)
| Route | Required stem | Actual stem | % complete |
|-------|--------------|------------|-----------|
| slant | 2.0s | 0.6s | 30% |
| comeback | 2.5s | 1.2s | 48% |
| double_move | 1.5s | 0.1s | 7% |
| curl | 2.5s | 1.1s | 44% |
| zig | 1.0s | 0.5s | 50% |
| in | 2.0s | 1.1s | 55% |
The WR's reasoning correctly states the required stem length at early steps, then overrides it when any CB recovery event appears.

#### R11-W3 — Multi-phase routes: terminal phase skipped (CRITICAL)
On every route with 3+ phases (double_move, zig, post_corner, in), the WR called on an intermediate phase and never ran the final break. The "catch heading" — the one the QB throws to and the WR runs to open space — was never executed. The WR treats the setup phase as the payoff phase.

#### R11-W4 — Break direction wrong on some routes (HIGH)
- Comeback: reasoning said 180° (back toward QB), action was 270° (lateral toward sideline)
- Corner: reasoning said "fake inside at 90°," action was 270° (toward sideline — the wrong direction for an inside fake)
- Post_corner: reasoning said 315° terminal, action cut to 45° (the fake, not the break)

#### R11-W5 — Go route working, but call logic uses wrong framework (LOW)
Go route ran correctly (straight 0° stem, no unnecessary fakes). But the WR's call reasoning borrowed cut-route logic ("CB hip committed") rather than speed-route logic ("I am faster and pulling away"). Worked accidentally because the CB self-induced recovery. Would fail against a CB that never cuts.

#### R11-P1 — qwen3:8b parse errors degrading CB quality (MEDIUM)
CB had 3-6 parse errors per route. The "in" route CATCH (sep=7.7yd) is a CB failure artifact — 6 consecutive CB parse errors froze the CB for 0.6 seconds. The separation earned is misleading. On routes where CB parsed correctly, the WR's abbreviated stems produced much tighter results.

---

## CURRENT STATE (post-Round 10 session)

### QB — ✅ WORKING
- Throws at the right time after WR calls
- "Open means at arrival" tip (`qb_pass2.txt`) is working — QB now throws at 1.5–1.8 yd sep instead of holding for "cleaner" windows
- Parse error rate ~2% with GPT — survivable
- No critical issues

### CB — ✅ WORKING
- Man coverage is playing correctly
- Tracks WR, reacts to cuts, contests at catch
- Swat intent on 10/10 routes — uniform but not harmful
- No critical issues

### WR — ❌ BROKEN (same root problem since Round 8)

**The WR ignores route phase geometry and runs its own deception strategy.**

Every fix attempted this session failed:
- Added `ROUTE_DESCRIPTIONS` with plain-English explanation of each phase → WR reads it, then runs 270° anyway
- Added per-step phase indicator: "YOUR HEADING THIS PHASE: 0° | ~1.4s left" → WR reads it, then runs 270° anyway
- Changed pre-snap prompt to forbid specific heading commands → WR stopped writing "jab to 270°" in the plan, but still goes 270° at step 2 from its own per-step reasoning
- Added "Do not add lateral cuts or jab fakes during this phase" to the observation → not tested (user called break)

**Concrete example (curl, this session):**
Route requires: 0° upfield for 1.5s → break to 180° toward QB.
WR actually ran: 0° for 0.1s → 270° (LEFT, sideways) for 5 steps → 180°.
The WR ran LEFT for most of the play. It was not a curl. It got a CATCH only because the CB happened to chase the wrong direction.

**Why the freedom principle blocks the fix:**
The WR has full autonomy over its heading each step. The route description, phase indicators, and "do not add lateral fakes" text are all guidance — the WR LLM reads them and then overrides them with its own per-step reasoning ("a 270° jab will commit CB hips"). No prompt text has yet convinced gpt-5-nano to run a clean upfield stem when it has decided a sideways jab is smarter.

**What this means:**
Until the WR actually follows route geometry, results are lucky-geometry catches, not real route execution. The QB and CB are not the bottleneck.

---

## Round 10 Results (seed=42, gpt-5-nano)

| Route | Outcome | Sep @ resolution | Sep @ throw | throw_t | Notes |
|-------|---------|-----------------|-------------|---------|-------|
| curl | CATCH | 4.27 yd | 4.29 yd | 0.5s | WR 270°→180° fake, called t=0.4, decisive |
| zig | CATCH | 2.41 yd | 2.45 yd | 0.9s | All 3 phases correct (0°→270°→90°) |
| drag | CATCH | 2.10 yd | 2.06 yd | 1.6s | 2 QB parse errors survived; final 90° shape correct |
| corner | CATCH | 2.09 yd | 1.80 yd | 1.3s | 290° break correct; CB 3-step recovery |
| slant | PBU | 1.0 yd | 1.01 yd | 2.4s | WR ran 220° fake as primary heading for 14 steps; parse error delayed QB |
| comeback | PBU | 1.0 yd | 1.69 yd | 1.6s | CB closed 0.69 yd during ball flight (0.2s); sep at throw insufficient |
| double_move | PBU | 1.0 yd | 1.46 yd | 1.9s | WR oscillated 0°/90° 18 steps; no real double-move executed |
| post_corner | PBU | 1.0 yd | 0.99 yd | 1.3s | WR output Chinese at t=1.1; tight from throw |
| in | PBU | 1.0 yd | 1.00 yd | 1.4s | CB body-on-body at throw; separation never established |
| go | INCOMPLETE | 1.0 yd | — | 1.4s | WR called at t=0.7 on 90° heading; go route requires 0°; ball unreachable |

**Round 10 score: 4C / 1INC / 5PBU** — best full-run score since Round 4 (4C/2D/3PBU/1INT)

Vs Round 9 (2C/3D/4PBU/1INT): +2 catches, −3 drops, +1 PBU, −1 INT, +1 INC.

**The sep=1.0 floor on PBUs is physics, not code.** The runner's collision-pushout enforces `min_d = 2 × PLAYER_RADIUS = 1.0 yd`. When sep=1.0 is reported, the CB was body-on-body with the WR at catch time. It is not a reporting artifact.

**The single discriminator for catch vs PBU is sep at throw time.** Every catch had ≥ 1.80 yd at throw. Every PBU had ≤ 1.69 yd at throw, and the CB closed the rest (0.14–0.20s flight). CB swat intent is universal (10/10 routes) and does not distinguish outcomes.

---

## FIXED / IMPROVED IN ROUND 10

### ✅ Drops eliminated
Round 9: 3 drops. Round 10: 0 drops. WR facing during ball flight is no longer generating contact-zone misses. The facing computation in `wr_live_free.txt` and ball-in-air prompt are working correctly.

### ✅ INT eliminated
Round 9: 1 INT (in route). Round 10: 0 INTs. The in route now executes a real 90° cut (called at t=1.0 on correct heading) rather than calling while running straight upfield.

### ✅ Parse error rate with GPT (S6 / N1)
Round 8 with qwen3:8b: 10–25% per-agent failure rate. Round 10 with gpt-5-nano: 5 errors across ~220+ calls (~2%). Parse errors are survivable at this rate (drag: 2 errors, still caught). This is no longer critical with GPT. Severity downgraded.

### ✅ CB swat geometry resolved (N8 partially)
CB geometric hallucinations (inventing lateral drift not in data) appear reduced — CB reasoning this round tracked actual WR positions accurately on most routes. Not confirmed fully resolved.

### ✅ WR route shape improved (N2 partially)
4/10 routes now execute correct terminal shape: zig (0°→270°→90°), drag (flat 90° cross), corner (290° break), curl (180° hook). Round 8: all 6 new-data routes had wrong shape.

---

## NEW ISSUES (Round 10)

### R10-N1 — PBU routes lose during ball flight; need ≥1.8 yd at throw, not at call (CRITICAL)

The previously stated problem "WR calls too late" is only half the issue. Even when the WR calls with 1.69 yd (comeback) or 1.46 yd (double_move), the CB closes to body contact (1.0 yd) before the ball arrives.

Ball flight ETA for contested routes is ~0.14–0.20s. At typical CB burst speed (~6.7 yd/s), the CB can close ~0.9–1.3 yd during flight. Therefore:
- **Sep < 1.7 yd at throw = PBU** (CB reaches contact before ball)
- **Sep ≥ 1.8 yd at throw = CATCH** (CB cannot close fully)

The hard threshold is ~1.8 yd at throw time, not call time. WR must establish this separation before calling. For comeback (throw_t=1.6s) CB closed 0.69 yd during flight. For corner (throw_t=1.3s) CB was already at 1.80 yd and couldn't close to 1.0 yd in time — barely caught.

---

### R10-N2 — WR fake direction treated as primary heading (slant-specific regression) (HIGH)

In the focused session, slant was a CATCH (sep=2.07). In Round 10 it was PBU.

Root cause: WR spent 14 consecutive steps (t=0.3→t=1.7) on heading 220° — the fake direction — before finally breaking to 40° at t=2.1. The slant route requires heading ~40° (diagonal upfield-right) as the primary path, with occasional jab-fakes. Instead the WR inverted the logic: it ran 220° as the main route and treated 40° as the endpoint. Combined with a QB parse error delaying throw to t=2.4 (0.3s after WR call), the CB had fully recovered by throw time.

**Why this happened:** The WR chose a long fake to "commit the CB" but the CB simply mirrored the fake direction (heading 210°–220°). The 14-step fake created no CB commitment — CB rec stayed at 0 throughout. The WR held the fake for diminishing returns.

---

### R10-N3 — Go route: WR called at t=0.7 on 90° heading; go requires 0° (HIGH)

A go route is a straight fly — heading 0° (straight upfield), no cuts. The WR instead:
- t=0.0: 0° (correct)
- t=0.1: 90° (wrong)
- t=0.2–0.6: 0° (recovers)
- t=0.7: 90° again, **calls for ball on this heading**

QB threw to [22.5, 53.5] — a location the WR never reached (ball_offset=2.09 yd). Result: incomplete.

The WR inserted a lateral cut into a route that has no cuts. Same root cause as N2: WR executes deception moves regardless of whether the route has a deception phase.

---

### R10-N4 — CB swat is universal and effective; all 10 routes (MEDIUM)

CB intent = "swat" on 10/10 routes, including all 4 catches. This means:
- The CB intent system is not generating play_man or go_for_pick decisions even when body-on-body (in route: sep=1.0, chose swat)
- CB swat is only "succeeded" at stopping the catch when sep < ~1.8 yd at throw — at larger sep, the arm reach can't get to the landing zone
- C3 (CB intent variety) is confirmed: CB always picks swat regardless of proximity or positioning

Low urgency because swat choice is rarely suboptimal — go_for_pick has lower success rate and play_man can enable a catch if WR has real separation. But the uniformity suggests CB intent logic isn't using position correctly.

---

### R10-N5 — LLM language switch on post_corner (LOW)

At post_corner t=1.1, WR reasoning switched to Chinese: "已完成最终切入315°，等待CB的rec>0信号再发球。" (Translation: "Final cut to 315° completed, waiting for CB rec>0 before calling.") The JSON field parsed correctly and the action (heading=315°) was valid. The language switch had no gameplay impact this run but indicates gpt-5-nano can switch languages unpredictably. Low priority since it didn't affect the JSON action field.

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

**R10 update:** Not an issue with GPT. 5 errors / ~220 calls (~2%). Survivable.

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

**R10 update:** Partially fixed. zig, drag, corner, curl now execute correct terminal shape. go (90° not 0°) and slant (220° fake as primary heading) still wrong. double_move oscillated without committing to either phase.

---

### N3 — WR facing hallucination during ball flight causes drops and PBUs (CRITICAL)

| Route | Required facing | Actual facing | Consequence |
|-------|----------------|--------------|------------|
| comeback | ~180° (toward QB bearing ~69°) | 71° (northeast) | DROP — catch probability crushed |
| zig | ~90° (toward landing zone) | 180° (toward CB) | PBU — WR ran toward CB, away from ball |
| post_corner | ~143° (bearing to QB) | 270° (pure left) | p_catch degraded to 0.70 |
| go | 0° (upfield to catch) | 180° (back toward QB) claimed but contradicted | Contested catch |

**R10 update:** Drops eliminated. WR facing during ball-in-air phase now consistently tracks ball direction. Still not perfect on PBU routes but no longer causing drops.

---

### N4 — WR's CB-commit trigger is phantom scaffolding (HIGH, ALL ROUTES)

The WR waits for "CB rec > 0" as the trigger to break. This was intended to be the cut_recovery fix (S4). However:

1. **The CB's cut_recovery is not in the WR's observation space.** The WR cannot see `CB.cut_recovery`. It is inferring this from CB heading changes, but the inference is unreliable.
2. **Comeback**: WR held the 270° fake for 16 steps waiting for "CB rec > 0" — which never fired because the CB was smoothly tracking (no sharp cuts = no recovery penalty). WR broke at t=1.7 without acknowledging the exit condition failed.
3. **Double_move**: At t=0.7 the WR declared "Fake right failed to commit CB (heading 149°)" when CB heading 149° + rec=1 is exactly a committed CB. The WR misread success as failure.
4. **Drag**: WR cites "CB rec=0" and "CB rec>0" as if reading a sensor value — this field does not exist in WR's observation.

**R10 update:** Still present. Slant WR at t=1.1 cited "CB rec=2" but CB was at rec=0. However the trigger is now working better in some routes (zig: correctly called when CB had rec=2).

---

### N5 — WR has no escalation counter; gets stuck in fake loops (HIGH)

| Route | Loop behavior | Duration | Consequence |
|-------|--------------|----------|------------|
| comeback | 270° lateral fake, waiting for CB rec | 16 steps / 1.5s | CB never committed, WR broke on wrong signal |
| curl | 270° lateral fake | 9 steps / 0.9s, 5.5 yards lateral | Route became a drift, not a curl |
| in | 20° left jab, repeated | 4 times at t=0.1/0.5/0.6/0.7 | No escalation; cut never run |
| slant | 0°/40° oscillation | 2.4s | No separation; CB never misled |

**R10 update:** Still present. double_move oscillated 0°/90° for 18 steps with no escalation. Slant spent 14 steps at fake heading with no escalation logic.

---

### N6 — QB one-step delay costs completions (HIGH)

- **double_move**: Peak separation 5.02 yd at t=0.8. WR called at t=0.8. QB threw at t=1.1 (one step late due to parse error at t=1.0). CB closed from 3.7 yd to 0.58 yd. Outcome: PBU. An on-time throw at t=0.9 would have given WR a 3+ yd lead.
- **curl**: WR called at t=2.3 (sep=0.78 yd), CB closing at 4.25 yd/s. QB threw at t=2.4. One step earlier (t=2.2, when WR snapped to 180° and CB was still at rec=1) would have beaten the CB.
- **zig**: QB correctly held through the fake; but once WR called, body was at heading 180° (not 90°) — QB threw at the wrong WR state.

**R10 update:** Still present. Slant: QB parse error at t=2.2 delayed throw 0.3s after call (to t=2.4). Drag: 2 parse errors cost 0.2s but the separation cushion was large enough to survive.

---

### N7 — CB over-commits to fake direction, no route anticipation (HIGH, MOST ROUTES)

| Route | CB failure |
|-------|-----------|
| zig | After 3 steps of 270°: "Confirmed left cut." Stops hedging entirely. WR snaps to different direction and CB is fully committed. |
| double_move | Never analyzes the double-move threat; treats rightward fake as real route until WR breaks back |
| corner | 2-step freeze after WR cut (t=2.2–2.4); still backpedaling when throw released at t=2.4 |
| post_corner | Declares "confirmed cut to 45°" then takes heading=4° cut (rec=3) at t=1.7 — exactly when WR executes Phase 3 break to 315° |
| curl | Follows WR's 9-step lateral drift all the way left; no rotation back when curl time arrives |

**R10 update:** Improved. CB tracking this round was more accurate — fewer wrong-direction commits. Still over-commits on multi-phase routes.

---

### N8 — CB geometric hallucinations (MEDIUM, MULTIPLE ROUTES)

- **post_corner t=0.2**: CB responds to "lateral drift" that does not exist in the data (WR x=16.0 at both t=0.1 and t=0.2).
- **post_corner t=0.6**: CB sets heading 180° (downfield) claiming "intercept" while WR is accelerating upfield at 6.39 yd/s.
- **corner t=0.7**: CB sets heading 80° (sideways) while reasoning says "maintain cushion."
- **corner t=1.4**: CB heading 270° (pure lateral) while WR is running straight upfield.

**R10 update:** Reduced. CB reasoning this round was more grounded in actual positions. Still present but lower frequency.

---

## UPDATED SYSTEMIC ISSUES

### S1 — WR hallucination has changed form again (HIGH, PERSISTS)

Round 8 form: route confusion (executes different route than called), phantom CB rec signals.
Round 10 form: **fake direction as primary heading** — WR runs the intended deception jab as its main route and treats the real break direction as the endpoint only. Slant: ran 220° for 14 steps (= the fake), then broke to 40° (= the real slant) only at call time. Go: inserted a 90° cut into a no-cut route.

Root cause unchanged: model optimizes each step independently without tracking whether the deception has served its purpose. A fake that runs 14 steps is no longer a fake — it is the route.

### S2 — CB template-locked reasoning (HIGH, PERSISTS)

Pattern still present but less prominent in Round 10. CB reasoning is more situationally specific in some routes (correctly tracking CB rec, closing at right moments). Still shows boilerplate "WR not yet committed; mirror patience" for 5–8 consecutive steps even when WR has been committed for 3+ steps.

### S6 — Parse errors at critical moments (DOWNGRADED to LOW with GPT)

Rate: ~2% with gpt-5-nano (5/~220 calls this round). The one critical case: slant QB parse error at t=2.2 cost 0.3s and turned a near-catch into PBU. But drag survived 2 parse errors because the separation cushion was wide enough. Not a systemic blocker with GPT.

Still CRITICAL with qwen3:8b — not addressed.

### W1 — WR calls for ball before completing route cut (PERSISTS, NEW FORM)

Go: WR called at t=0.7 on 90° heading (go route requires 0°). The WR inserted a cut into a no-cut route and called on the wrong heading.

### W2 — WR heading / facing wrong after calling (PARTIALLY FIXED)

Drops eliminated in Round 10 — WR facing during ball flight now tracks ball direction. Remaining issue: the heading at call time is still wrong on go (90° not 0°) and was wrong on slant for too long before correcting.

### W3 — WR never executes the actual route (PARTIALLY FIXED)

Round 8: 6/6 new routes with wrong shape. Round 10: 6/10 routes with issues (go, slant, double_move, comeback, in, post_corner have shape problems; zig, drag, corner, curl correct).

### W4 — Jab fakes too shallow (PERSISTS)
Still present on some routes; less prominent than Round 8.

---

## MASTER ISSUES TABLE

| ID | Problem | Routes Affected | Severity | Status |
|----|---------|----------------|----------|--------|
| S1 | WR hallucination (now: fake direction as primary heading, wrong route for go) | slant, go, double_move | HIGH | OPEN — new form |
| S2 | CB template-locked reasoning | ALL | MEDIUM | OPEN — reduced in R10 |
| S3 | CB frozen 3 steps at pre-snap | ALL | — | ✅ FIXED R8 |
| S4 | cut_recovery absent from replay JSON / agents blind to physics | ALL | — | ✅ FIXED R8 |
| S5 | QB reasoning copy-pasted post-throw | ALL | — | ✅ MITIGATED |
| S6 | Parse errors at critical moments | ALL | LOW (GPT) / CRITICAL (Ollama) | DOWNGRADED for GPT |
| N1 | Parse error rate with qwen3:8b | ALL Ollama | CRITICAL | N/A for GPT runs |
| N2 | WR executes wrong route shape | go, slant, double_move, in | HIGH | PARTIALLY FIXED — 4/10 correct in R10 |
| N3 | WR facing hallucination during ball flight | ALL | — | ✅ DROPS ELIMINATED R10 |
| N4 | WR's CB-commit trigger ("CB rec > 0") is unobservable phantom | ALL | MEDIUM | PERSISTS — less critical, some correct use |
| N5 | WR has no escalation counter; loops fake indefinitely | slant, double_move, comeback | HIGH | PERSISTS |
| N6 | QB one-step delay costs completions | slant, drag | HIGH | PERSISTS — survivable if sep cushion wide enough |
| N7 | CB over-commits to fake; no route anticipation | multi-phase routes | MEDIUM | IMPROVED in R10 |
| N8 | CB geometric hallucinations (invents WR lateral drift) | post_corner, corner | LOW | REDUCED in R10 |
| W1 | WR calls for ball at wrong heading | go | HIGH | PERSISTS — go calls at 90°, not 0° |
| W2 | WR heading/facing wrong after calling | — | — | ✅ DROPS ELIMINATED R10 |
| W3 | WR never executes the actual route geometry | go, slant, double_move, in | HIGH | PARTIALLY FIXED — 4/10 correct |
| W4 | WR jab fakes too shallow; no physics execution | some routes | LOW | PERSISTS |
| C1 | CB no lateral coverage during stem | ALL | MEDIUM | OPEN |
| C2 | CB 2–6 step react delay after cut | corner, curl | LOW | REDUCED in R10 |
| C3 | CB intent randomly assigned — always swat (10/10 R10) | ALL | MEDIUM | OPEN — uniformly swat now |
| C4 | CB speed locked at 6.75 in backpedal | SOME | LOW | OPEN |
| Q1 | QB waits correctly; WR calls on wrong heading (go) | go | MEDIUM | CHANGED — QB waits; WR heading wrong |
| Q2 | QB throw geometry errors on angled routes | SOME | LOW | REDUCED |
| Q3 | QB lead calc ignores WR cut-recovery speed arc | SOME | LOW | OPEN |
| Q4 | QB template-locked during hold phase | ALL | MEDIUM | PERSISTS — slightly better in R10 |
| P3 | detected_cut_t fires on jabs | in, slant | LOW | PERSISTS |
| R10-N1 | PBU during flight: need ≥1.8 yd at throw, not at call | comeback, double_move | CRITICAL | NEW — hard threshold now defined |
| R10-N2 | Fake direction as primary heading — slant spent 14 steps at 220° | slant | HIGH | NEW — regression from focused session |
| R10-N3 | Go route: WR calls at 90° heading; go requires 0° | go | HIGH | NEW |
| R10-N4 | CB swat intent universal (10/10); no play_man or go_for_pick | ALL | MEDIUM | NEW |
| R10-N5 | LLM language switch (post_corner WR → Chinese at t=1.1) | post_corner | LOW | NEW |

---

## WHAT'S WORKING

1. **CB freeze removed (S3)** — CB acts from t=0. Confirmed all routes.
2. **cut_recovery in replay JSON (S4)** — Field present; agents cite it and act on it.
3. **Drops eliminated (R10)** — WR facing during ball-in-air phase now correct in 10/10 routes.
4. **INTs eliminated (R10)** — In route now executes a real 90° cut before calling.
5. **4 correct route shapes (R10)** — zig (0°→270°→90°), drag (90° flat cross), corner (290°), curl (180° hook). The geometric instruction in scenario YAMLs is being followed on 4 routes.
6. **Parse error rate near-zero with GPT** — ~2% failure rate is not systemic. Survivable when separation cushion > 1.8 yd.
7. **CB recovery-aware break timing** — WR on zig and corner correctly waited for CB rec > 0 before breaking.
8. **Dynamic burst physics** — Speed ramps and cut penalties are correct and consistent.
9. **Sep-at-throw threshold quantified** — Clear empirical threshold: ≥1.8 yd at throw → CATCH; ≤1.69 yd → PBU (CB closes to contact during flight).

---

## ROOT CAUSE HIERARCHY

**Tier 1 — blocks most completions:**
1. **Sep at throw < 1.8 yd (R10-N1)** — The hard constraint. On comeback (1.69), double_move (1.46), post_corner (0.99), in (1.00), the CB closes to body contact during ball flight. WR must reach ≥1.8 yd before calling. Fix: WR needs to keep extending separation after the break — currently it brakes or coasts after calling, giving CB time to close. The break must accelerate THROUGH the call point.
2. **WR fake direction as primary heading (R10-N2)** — WR executes the fake as its main route. Slant: 14 steps at 220° fake, only broke to 40° at call. Go: inserted 90° cut into a no-cut route. Fix: inject explicit per-step phase constraints ("Phase 1 = 0° stem; Phase 2 = final break at 40°. You are on Phase 1. Your next target heading is 40°.") — the WR needs structural guidance on which direction is the REAL route.
3. **WR escalation loop (N5)** — No step counter; WR repeats cheap fakes indefinitely. Slant: 14 steps at 220°. Double_move: 18 steps oscillating. Fix: inject "You have been on this heading for N steps. If N > 3, execute the real break now."

**Tier 2 — converts open windows into incompletions:**
4. **QB parse error delay on short-window plays (N6)** — A 0.3s delay turned slant into PBU. Fix: already have retry logic; consider increasing retry count from 1 to 2.
5. **CB swat closes ≤0.7 yd during flight (R10-N1 mechanism)** — CB reaches body contact from ~1.69 yd in 0.2s. This is physically correct but means the throw window is brutally narrow. Cannot fix without increasing WR acceleration out of the break, or throwing sooner (before CB has fully recovered).
6. **WR wrong heading at call — go route (R10-N3)** — WR inserted a 90° cut into a no-cut route. Fix: pre-snap instruction must state "This route has NO cuts. Do not change heading."

**Tier 3 — degrades quality on plays that otherwise work:**
7. **QB hold-phase boilerplate (Q4)** — QB never reads CB position during hold. Fix: QB observation should include CB recovery steps and bearing to WR.
8. **CB intent uniformly swat (R10-N4)** — CB does not differentiate close-contact vs distant situations for play_man. Low impact since swat is often correct choice.

---

## APPENDIX A — Round 9 Results (seed=42, gpt-5-nano, post-encoding+JSON+geometry fixes)

**Round 9 score: 2C / 3D / 4PBU / 1INT**

| Route | Outcome | Notes |
|-------|---------|-------|
| comeback | CATCH | 9.36 yd — CB ran out of play |
| in | CATCH | WR executed 90° cut correctly |
| slant | PBU | 1.24 yd — WR oscillated; no real break |
| go | DROP | — |
| double_move | DROP | — |
| curl | DROP | — |
| zig | PBU | — |
| drag | PBU | — |
| corner | PBU | — |
| post_corner | PBU | regression from R8 CATCH |

---

## APPENDIX B — Round 8 Results (seed=42, qwen3:8b via Ollama)

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

---

## APPENDIX C — Round 7 Results (seed=42, gpt-5-nano, pre-Round-8-fixes)

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
