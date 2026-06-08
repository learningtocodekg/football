# Problems — Full Run Analysis (Round 7, seed=42, gpt-5-nano, post-physics-overhaul)

## Round 7 Results

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

**Score: 3C / 1D / 3PBU / 1INC / 1INT / 1SACK = 3 catches (down from Run 5's 4)**

The physics overhaul (dynamic burst + cut recovery) is working in the engine — speed drops are visible on cuts. But no agent reads or reacts to the new physics signals, making the overhaul functionally invisible to agent decision-making.

---

## SYSTEMIC ISSUES (all or most routes)

### S1 — WR hallucinates deception that never happens (CRITICAL, ALL ROUTES)

The WR's reasoning describes jabs and fakes that do not appear in the physics output. The most common form is the boilerplate string appearing verbatim across routes:

> "stem at 0; jabbed left last step so returning to 0 now"

This text appears at **t=0.0** on slant, comeback, corner, post_corner, zig, and go — the very first step, when no previous step has occurred. It is fabricated context. It also appears mid-fake (zig t=0.9: WR claims to be returning from a jab while it should be holding a 270° fake) causing it to abort the route.

**Route-specific evidence:**
- **Slant**: WR alternates 0°/40° every step for 2.4 seconds, claiming "disrupt CB projection" — but no heading is held long enough to sell anything. CB never reacts.
- **Corner**: WR claims "jabbed left last step" at t=0.2, 0.7, 1.1, 1.4–1.7 but heading is 0° at all those steps.
- **Post_corner**: Same pattern — "jabbed left" at t=0.0, 0.1, 0.2, 0.7, 1.1. Heading never leaves 0° for those steps.
- **Go**: WR says "jabbed left last step so returning to 0 now" repeatedly but x-position stays locked at 16.0 — zero lateral movement the entire stem.
- **Comeback**: Claims "jabbed left last step" at t=1.1, t=1.3 when the previous step was actually a right jab. State tracking is wrong.
- **Double_move**: WR claims it is "faking left" for 2.1 seconds while running a pure 270° horizontal stem with zero directional variation.
- **Zig**: At t=0.9, the boilerplate fires mid-fake ("jabbed left last step so returning to 0 now") and the WR aborts the 270° left fake — creating a spurious 0° step and a second cut penalty.

**Root cause**: The WR's scratchpad memory is not verified against actual physics state. The LLM hallucinates prior actions to fit its narrative.

---

### S2 — CB reasoning is template-locked across all routes (CRITICAL, ALL ROUTES)

The phrase "WR is still approaching and I want to keep cushion while watching for the cut" — or near-verbatim variants — appears across all 10 routes, in many cases for 15–25 consecutive steps:

- **Comeback**: ~23 of 33 CB steps use this exact string, including steps after the WR has completed the comeback cut and is running away.
- **Post_corner**: 22 consecutive steps (t=0.4–2.8).
- **Corner**: ~14 of 29 CB steps.
- **In**: 7 consecutive identical steps, zero reaction to WR jabs.
- **Curl**: 7 consecutive identical steps, including steps after ball is in the air.

The CB never: identifies a WR hip-angle, commits to closing on the ball, references its own burst state or positioning geometry, or acknowledges any fake as a fake.

The only time the CB does something non-template is (a) when the ball is in the air and it switches to `go_for_pick` or `swat` intent, or (b) rarely when the WR makes an actual sustained lateral break (zig).

---

### S3 — CB frozen for 3 steps at snap (HIGH, ALL ROUTES)

On every route, the CB reasoning at t=0.0, t=0.1, t=0.2 is `"pre-snap alignment done"` with speed=0. The CB does not begin moving until t=0.3. This gives the WR a free ~3-step release.

**Drag**: The CB's 3-step frozen start is the single largest contributor to the 4.02 yd final separation on what should be a tightly contested short route.

---

### S4 — No agent reads or reacts to cut_recovery data (CRITICAL, ALL ROUTES)

The physics overhaul introduced `cut_recovery` as a key signal — steps remaining of reduced burst after a hip-turn. **Zero agents in any route cite this field in reasoning.** The physics are correct:

| Route | Cut | Speed before | Speed after | Drop |
|-------|-----|------------|------------|------|
| zig | 270° at t=0.6 | 8.4 | 5.11 | 39% |
| curl | 180° at t=1.3 | 9.5 | 2.09 | 78% |
| comeback | 180° at t=2.2 | 9.5 | 2.09 | 78% |
| corner | 110° at t=2.2 | 9.5 | 6.77 | 29% |
| post_corner | 90° at t=2.4 | 9.5 | 5.59 | 41% |

No WR, QB, or CB says "cut_recovery = X", "I'm still recovering", "WR is slow — close now", or "wait for recovery before calling."

**Additionally**: The `cut_recovery` field does not appear in the per-player JSON output. Agents reference `rec` values in reasoning but these cannot be verified from the replay. Either the field is not being written or the observation builder isn't surfacing it correctly.

**Impact**:
- WR calls for ball mid-recovery: zig (speed 2.71), curl (speed 2.09), corner (speed 6.77)
- QB throws without knowing WR speed at catch time
- CB misses windows when WR is slowest and easiest to close on

---

### S5 — QB reasoning copy-pasted post-throw (MEDIUM, ALL ROUTES)

After releasing the ball, the QB copies its throw-decision reasoning verbatim across all remaining steps. Examples:
- **Slant**: "WR will reach (20.3,63.5) as the ball arrives" repeats at t=2.7, 2.8, 2.9, 3.0 — while the WR visibly overruns the spot.
- **Zig**: Same sentence at t=1.3, 1.4, 1.5 — QB claims "CB is not closing" while the CB is actively closing to within 0.5 yd.
- **Post_corner**: Identical string 4 times post-throw.

The QB does not update its projection as the ball travels, does not reassess whether the CB is closing, and cannot adapt.

---

### S6 — Parse errors at critical moments (MEDIUM, MOST ROUTES)

| Route | Agent | Steps | Impact |
|-------|-------|-------|--------|
| comeback | QB | t=2.2–2.7 (6 consecutive) | QB blind for entire call-to-throw window |
| curl | QB | t=0.7, 0.8, 1.5 | t=1.5 delays throw evaluation after call |
| go | QB | t=0.6 | mid-play reliability failure |
| zig | QB | t=0.9, 1.0 | during the cut window — most critical |
| zig | WR | t=1.1 | post-cut, can't adapt heading |
| post_corner | QB | t=2.5 | one step after WR call — delays throw |

The QB 6-consecutive-error streak on comeback is the worst: QB was offline during the entire call-to-throw window.

---

## WR-SPECIFIC ISSUES

### W1 — WR calls for ball before completing the route cut (CRITICAL)

| Route | Call timing | Speed at call | What went wrong |
|-------|------------|---------------|-----------------|
| in | t=0.8, heading=0° | 6.46 yd/s | Still on stem, never made 90° in-break |
| curl | t=1.3, heading=270° | 2.09 yd/s | Called at start of 180° turn, not after completing it |
| zig | t=1.2, heading=90° | 2.71 yd/s | In cut recovery from double-cut at t=0.9–1.0 |
| corner | t=2.3, heading=290° | 8.17 yd/s | Called one step into cut, still recovering |

The **in route** is the most damaging: WR confused longitudinal gap (CB was 2.7 yd upfield) with lateral separation. CB was directly in the throw lane. Called, QB threw straight upfield, CB intercepted.

---

### W2 — WR changes heading after calling for ball (CRITICAL)

- **Curl**: Called at t=1.3 heading=180°. At t=1.6 during ball flight shifted to 150° "to deceive CB's intercept projection." QB threw to [16.4, 57.2] on the 180° path; WR was at [16.94, 57.32] on 150° path. DROP.
- **Zig**: Spurious boilerplate at t=0.9 aborted the left fake mid-hold, creating a double cut penalty that left WR at 2.71 yd/s at call. PBU.

---

### W3 — WR never executes the actual route (HIGH)

| Route | Required | Actual |
|-------|---------|--------|
| in | Stem upfield → hard 90° inside cut | Ran straight 0° entire play, called on stem |
| double_move | Commit first cut → snap back | Ran pure 270° for 2.1s, broke out of bounds |
| go | Straight speed route with go-route sells | Pure 0° stem, no variation, never called |
| drag | Stem upfield → 90° break across | Pivoted to 90° at t=0.2 — essentially no stem |

Structural failures where the WR doesn't understand the route shape, not just execution errors.

---

### W4 — WR jab fakes too shallow to affect CB (HIGH, ALL ROUTES)

All WR fakes during stems are 20–30° deviations from the stem heading. A real jab that forces CB hip commitment needs 60–90° lateral deviation held for 2+ steps. At 20–30°, the CB doesn't need to react — and doesn't. On every route where the WR attempted jabs, CB heading was within 5° of its default backpedal heading during those steps.

---

## CB-SPECIFIC ISSUES

### C1 — CB never runs lateral coverage during stem phase (HIGH, ALL ROUTES)

The CB's x-position moves < 1.5 yards during the entire stem phase on every route. It is exclusively backpedaling upfield. When the WR cuts, the CB is in no lateral position to contest.

**Comeback**: CB ended 9.36 yards away because it backpedaled straight upfield while the WR ran back toward it. The CB's only "coverage" was running in the wrong direction for 2.8 seconds.

---

### C2 — CB react delay: 2–6 steps after WR cut before adjusting (HIGH)

| Route | WR cut at | CB first reacts at | Delay |
|-------|----------|-------------------|-------|
| comeback | t=2.2 | t=2.8 | 6 steps (0.6s) |
| corner | t=2.2 | t=2.5 | 3 steps (0.3s) |
| post_corner | t=2.4 | t=3.0 (END) | too late |
| curl | t=1.3 | never | CB kept backpedaling away from the play |

Curl is the clearest case: CB was 0.88 yards from WR when the curl cut fired. It continued backpedaling away rather than flipping and chasing. Blown coverage assignment.

---

### C3 — CB intent randomly assigned, not position-aware (MEDIUM)

The `cb_intent` field (play_man/swat/go_for_pick) is set at ball-in-air time. The in-route interception happened because CB drew `go_for_pick` and positioned correctly. The drag-route swat was geometrically impossible — CB was 4 yards from the landing zone with 0.084s remaining. Intent is not calibrated to CB position or geometry.

---

### C4 — CB speed locked at 6.75 yd/s in backpedal (LOW)

On comeback, corner, post_corner, in: CB speed field shows 6.75 for 15–20 consecutive steps with zero variation. Looks like a hard ceiling from backpedal mode rather than dynamic physics.

---

## QB-SPECIFIC ISSUES

### Q1 — QB throws without WR call on go route (HIGH, PERSISTENT — P1 from Round 1)

Go: `wr_call_t: null`. QB threw at t=0.8 without a call. The WR never called because the go route has no designed cut moment and the WR never judged itself open. Freelance throw had 1.0-yd lateral error (targeted x=17.5, WR at x=16.46 heading 0°). This is Round 7 and this problem is unchanged from Round 1.

---

### Q2 — QB throw geometry errors on angled routes (HIGH)

| Route | QB target | WR actual position | Error | Outcome |
|-------|----------|--------------------|-------|---------|
| slant | (20.3, 63.5) | (20.3, 64.38) — overran by 0.9 yd | WR accelerating post-cut, QB didn't account for it | PBU |
| post_corner | (16.1, 71.6) | (15.56, 72.11) — ran 315° past target | WR heading was decreasing y, not increasing | PBU |
| go | (17.5, 56.4) | (16.46, 57.46) — 1.0 yd lateral miss | WR heading was 0°, not rightward | INC |

---

### Q3 — QB lead calc ignores WR cut-recovery speed arc (MEDIUM)

After a cut, the WR decelerates through a recovery arc before rebuilding. The QB calculates the throw target assuming constant speed, producing a lead that is too long (WR still slow) or too short (WR re-accelerating past the spot). Neither slant nor post_corner QB reasoning acknowledges the WR's changing speed state.

---

### Q4 — QB template-locked during broken play (HIGH)

Double_move: After `BROKEN_PLAY` fired at t=2.1, QB repeated "BROKEN PLAY: wait for WR to call for ball" for 20+ steps. Never evaluated geometry. Let sack clock expire. WR did call at t=2.1 but QB ignored it. The QB needs broken-play decision logic: if WR calls during broken play and geometry supports a throw, evaluate and throw.

---

## PHYSICS VALIDATION

### P1 — cut_recovery system is working but invisible to agents

Speed drops on cuts are clean and consistent:
- ~40% drop on 60–90° cuts
- ~78% drop on 180° cuts
- Recovery arc: 2–4 steps to full speed

But `cut_recovery` does not appear as a field in per-player JSON. Agents reference `rec` in reasoning but cannot be verified from replay output. This needs to be fixed for agents to act on physics signals.

### P2 — Dynamic burst is working correctly

WR acceleration curves are smooth: 1.4→9.5 yd/s over ~0.5s in open-field stems. No issues.

### P3 — detected_cut_t fires on jabs (PERSISTENT)

- In: `detected_cut_t: 0.7` on a 20° jab
- Slant: `detected_cut_t: 0.1` on a minor jab
- Drag: `detected_cut_t: 0.2` on immediate pivot

Cut detection threshold is still too permissive for micro-jabs.

---

## ROUTE-BY-ROUTE SUMMARY

**SLANT — PBU (sep=1.24):** WR alternated 0°/40° every step for 2.4s, no heading held >1 step. QB waited 0.3s after call then targeted (20.3, 63.5) but WR moving at 7.44 yd/s overran the spot by 0.9 yd.

**COMEBACK — CATCH (sep=9.36) — misleading success:** 9.36 yd gap is CB failure, not WR success. CB backpedaled away from the play for 2.8s. WR jabs (20°–30°) produced zero CB reaction. QB had 6 consecutive parse errors covering the call-to-throw window.

**GO — INCOMPLETE (sep=2.26):** WR never called (`wr_call_t: null`). Fabricated "left jab" reasoning at t=0.0. QB freelanced at t=0.8, targeted x=17.5 when WR was at x=16.46 heading 0°. P1 from Round 1 — unchanged after 7 runs.

**CURL — DROP (sep=2.31):** WR called at t=1.3 with speed 2.09 (mid-cut minimum). Changed heading to 150° at t=1.6 after signaling 180°. QB threw to [16.4, 57.2] on 180° path; WR on 150° path. CB used identical reasoning for 7+ steps including after ball was in the air.

**ZIG — PBU (sep=0.75):** Best WR deception of the run — genuine 3-step 270° left fake at t=0.6–0.8. Boilerplate at t=0.9 aborted the fake (spurious 0° step), double-cut penalty, WR at 2.71 yd/s at call. CB was 0.75 yd away — PBU.

**DRAG — CATCH (p=0.723, sep=4.02):** WR pivoted to 90° at t=0.2 — no stem. Claimed to be "faking toward right sideline" while heading was 90° the entire time. CB frozen 3 steps gave free release. Catch was due to CB slow start, not WR skill.

**CORNER — CATCH (p=0.866, sep=6.66):** WR cut to 290° (slightly backward) instead of proper corner direction 315°–330°. CB used template reasoning for 14/29 steps, never reacted to cut, ended 6.66 yd away. Stem reasoning fabricated left jabs that never occurred.

**POST_CORNER — PBU (sep=1.54):** WR fabricated jabs throughout stem. 45° fake at t=2.0–2.3 was real; CB showed zero response. QB threw to (16.1, 71.6) but WR was moving 315° (decreasing y) and overran the landing zone. CB ended up at the landing zone by accident through straight backpedaling.

**IN — INTERCEPTION (sep=0.45):** WR never ran the in-route. Called for ball at t=0.8 heading 0° because CB was "2.7 yd ahead" — confused longitudinal distance for lateral separation. CB was in the throw lane. QB threw straight upfield. CB drew `go_for_pick` intent and was at the landing zone. INTERCEPTION.

**DOUBLE_MOVE — SACK (clock expired):** WR ran a pure 270° horizontal stem for 2.1s — not a double move. Broke to 0° from near the sideline ([1.35, 50.0]) — triggered `heading_out_of_bounds`. QB repeated "BROKEN PLAY: wait for WR call" for 20+ steps with zero clock urgency. Sack clock expired at t=5.0.

---

## MASTER ISSUES TABLE

| ID | Problem | Routes Affected | Severity | Status |
|----|---------|----------------|----------|--------|
| S1 | WR hallucinates deception / boilerplate "jabbed left" at t=0 | ALL | CRITICAL | NEW — first full characterization |
| S2 | CB template-locked reasoning throughout | ALL | CRITICAL | OPEN — unchanged |
| S3 | CB frozen 3 steps at pre-snap | ALL | HIGH | OPEN — confirmed all 10 routes |
| S4 | No agent reads cut_recovery data; field absent from replay JSON | ALL | CRITICAL | NEW — physics working, agents blind |
| S5 | QB reasoning copy-pasted post-throw | ALL | MEDIUM | OPEN |
| S6 | Parse errors at critical moments | MOST | MEDIUM | OPEN |
| W1 | WR calls for ball pre-cut or mid-cut | in, curl, zig, corner | CRITICAL | OPEN — in route caused INT |
| W2 | WR changes heading after calling for ball | curl, zig | CRITICAL | OPEN |
| W3 | WR never executes the actual route | in, double_move, go, drag | HIGH | OPEN |
| W4 | WR jab fakes too shallow (20–30°) — CB never reacts | ALL | HIGH | OPEN |
| C1 | CB no lateral coverage during stem | ALL | HIGH | OPEN |
| C2 | CB 2–6 step react delay after cut | ALL | HIGH | OPEN |
| C3 | CB intent randomly assigned — not position-aware | ALL | MEDIUM | OPEN |
| C4 | CB speed locked at 6.75 in backpedal | SOME | LOW | NEW OBSERVATION |
| Q1 | QB throws without WR call — go route (P1 from Round 1) | go | HIGH | OPEN — Round 7, still unfixed |
| Q2 | QB throw geometry errors on angled routes | slant, post_corner, go | HIGH | OPEN |
| Q3 | QB lead calc ignores WR cut-recovery speed arc | slant, post_corner | MEDIUM | OPEN |
| Q4 | QB template-locked during broken play | double_move | HIGH | NEW |
| P1 | cut_recovery absent from replay JSON per-player output | ALL | HIGH | NEW — blocks verification |
| P3 | detected_cut_t fires on jabs | in, slant, drag | MEDIUM | PERSISTENT |

---

## WHAT'S WORKING

1. **Dynamic burst acceleration** — WR speed ramps correctly (1.4 → 9.5 yd/s). Smooth and realistic.
2. **Speed shed on cuts** — Hip-turn penalty produces correct drops proportional to cut angle. 180° cuts ≈78%, 90° cuts ≈40%.
3. **QB holds for WR call** — 8/10 routes QB correctly waited for the WR call before throwing.
4. **Ball-in-air heading lock** — 8/10 routes WR maintained heading after calling (failures: curl, double_move).
5. **CB intent switching** — When CB draws `go_for_pick`, it actually positions to intercept. Intent system works when triggered.
6. **Zig fake execution** — WR held the 270° fake for 3 steps (t=0.6–0.8) before the real break. Proves the LLM can sustain multi-step fakes when the boilerplate bug doesn't fire.

---

## ROOT CAUSE HIERARCHY

**Tier 1 — blocks everything else:**
1. **WR boilerplate ghost memory** (S1) — The "jabbed left last step" string appears at t=0.0 and fires mid-fake, suggesting the WR prompt injects a scratchpad whose initial value or update logic is wrong. Fix this and hallucinated deception goes away.
2. **cut_recovery not in replay JSON** (S4/P1) — Agents can't react to signals they can't see. The field needs to be written to the replay and surfaced in the observation builder.

**Tier 2 — major behavioral failures:**
3. **CB pure backpedal template** (S2) — CB observation needs more information to break out of the cushion-maintenance loop: WR lateral position delta, cut history, route phase signals.
4. **WR pre-cut call gate** (W1) — Hard gate needed: WR cannot call unless (a) heading is within X° of the route's designed break heading AND (b) speed is above Y% of max.

**Tier 3 — geometry accuracy:**
5. **QB lead calculation ignores recovery arc** (Q3) — Post-cut, QB should factor in WR's current speed (which may be in recovery) rather than assuming constant max speed.
6. **Route shape injection** (W3) — WR on go, in, double_move doesn't understand the route structure. Scenario files need to inject the route shape more explicitly into the WR pre-snap observation.
