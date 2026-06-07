# Problems Found — Route Tree Analysis (seed=42, Ollama qwen3:8b, post-fix run)

Results: slant→DROP, comeback→INCOMPLETE, go→DROP, double_move→INTERCEPTION,
curl→INCOMPLETE, zig→DROP, drag→CATCH, corner→CATCH, post_corner→DROP, in→DROP

Score: 2 CATCH, 5 DROP, 1 INCOMPLETE, 1 INTERCEPTION, 0 SACK

---

## N1 — detected_cut_t threshold still fires on t=0.5 jabs (HIGH)

**Affected routes:** all 10  
**Symptom:** detected_cut_t=0.5 in every single replay — still a false positive in 9 of 10 routes.

The fix raised the gate to `t >= 0.5`, but the WR jabs at exactly t=0.5 on every route, so the condition is still met. In corner_42 the WR jabs to 290° (same angle as the cut heading) at t=0.7, which also fires the detector 1.5s before the real cut.

The detector fires on single-step jabs. A real cut is sustained: the WR holds the new heading for multiple steps. A jab snaps back to 0° in 1 step.

**Fix needed:** Require the heading to persist for at least 2 consecutive steps before recording a cut, OR raise the threshold to t >= 0.9 (which still catches zig's real cut at t=0.9 and is above all observed jabs).

---

## N2 — WR jab template is cookie-cutter across all routes (HIGH)

**Affected routes:** all 10  
**Symptom:** Every route shows the same alternating 330°/30° pattern. 330° appears 4–7 times per route in a 2-second stem. Prompt and observation changes did not break the habit.

In post_corner: 330° at t=0.0, 0.3, 0.5, 0.7, 1.0, 1.3, 1.6, 1.8 (8 times) plus 30° at t=0.4, 1.1, 1.7. In corner: 9 jabs in 2.2s, 330° repeated 4 times. Across all routes the WR uses an identical template regardless of route design or CB alignment.

The LLM ignores the "vary your fakes" guidance in the prompt. The observation-level warning (checking recent headings) was removed. The template produces zero net deception: CB adapts within 3–4 reps.

**Fix needed:** Track recent jab angles in the observation and explicitly call out repetition with the specific angles used. E.g. "You have jabbed 330° 4 times this play — the CB has pattern-read it. Do NOT use 330° again."

---

## N3 — Comeback: QB throw direction inverted (HIGH)

**Affected routes:** comeback → INCOMPLETE (ball_offset=2.44 yd)

WR called for ball at t=2.2 with heading 180° (running back toward QB, decreasing y). QB threw at t=2.3 to target y=63.7. At throw time the WR was at y=63.35 with speed 3.71 yd/s heading 180° — so WR is moving toward lower y. The correct target was y ≈ 63.35 − 3.71×0.26 ≈ 62.4. QB threw to y=63.7, which is upfield from where the WR was — the ball was thrown behind the direction of travel. WR ended at y=62.19 at resolution, ball landed at y=63.7 — 1.51 yd miss.

The LEAD HINT in the observation shows the projected position using WR's heading direction, but the QB calculated the lead as if the WR were still running upfield.

**Fix needed:** The LEAD HINT calculation already computes the correct projection. This appears to be the QB LLM misreading heading 180° as upfield. The observation should explicitly label a heading-180° WR as "running BACK TOWARD QB (decreasing y)" in the lead hint so the QB can't confuse it.

---

## N4 — Double-move: fake phase ended 0.3s early; resulted in interception (HIGH)

**Affected routes:** double_move → INTERCEPTION

The fake-right phase (90°) is specified to run from t=1.5–2.2. The WR held 90° from t=1.5–1.8 (0.3s) and snapped back to 0° at t=1.9 — 0.3s ahead of schedule. At t=1.9 the CB was only 1.8 yd away (not yet committed to the wrong direction). When the WR broke upfield, the CB was close enough to stay with it. Combined with the CB's `go_for_pick` intent and the WR running directly into the CB's zone at t=2.0–2.1, this produced an interception.

**Fix needed:** The intermediate phase enforcement in the observation says "HOLD this heading for the FULL duration." But the WR LLM exited early anyway. The phase timing needs to be re-emphasized — possibly show a countdown ("X steps remaining in fake phase") and state explicitly that exiting early telegraphs the real break to the CB.

---

## N5 — Curl: WR reverses heading after calling for ball (HIGH)

**Affected routes:** curl → INCOMPLETE

WR called at t=1.4, heading=180° (correct, fully turned toward QB). Heading was locked. But during ball-in-air phase: at t=1.5 WR heading=180°, then at t=1.6 WR heading=90°, facing=0°. The WR drifted sideways instead of staying put or tracking the ball. Ball landed at (14.5, 56.4); WR ended at (14.84, 54.92) — 1.5 yd short.

The heading lock in `apply_decision` only applies when `ball_in_air=False`. During ball-in-air the WR is free to adjust. The LLM chose a heading of 90° — seemingly trying to "move to the landing zone" — but moved laterally rather than slightly upfield to the landing zone.

**Fix needed:** The ball-in-air prompt needs to remind the WR that a curl's catch point is slightly upfield of where the WR is standing (QB is throwing back toward the WR), so the WR should hold near-stationary or step slightly back toward QB (heading 180°), not drift sideways.

---

## N6 — In route: QB threw a lob at 26.9 mph and waited 0.2s after the call (HIGH)

**Affected routes:** in → DROP (separation=1.67)

QB threw at 26.9 mph for a 15-yard throw — ETA=0.39s vs. 0.19s at regular speed. This gave the CB nearly double the time to close. At throw time the CB was only 0.1 yd laterally from the WR; the extra flight time allowed the CB to contest the catch. The QB also waited 0.2s after the WR called (call at t=1.6, throw at t=1.8), further helping the CB.

QB reasoning at t=1.7: "WR window isn't open enough on the projected arrival." This is incorrect — the in-route was already open with 3+ yd separation at the call.

**Fix needed:** For horizontal routes (in, drag) where the CB can close laterally, the QB should prefer fast throws. The observation could note "horizontal routes close quickly — prefer bullet/regular speed." Also the QB holding 0.2s extra cost the play.

---

## N7 — CB oscillates between backpedal and lateral pursuit (MEDIUM)

**Affected routes:** in (t=2.0), corner (t=0.8, 1.3)

In the in route, the CB correctly pivoted to pursue at t=1.7 (heading=90°), then reverted to backpedal at t=2.0 (heading=0°, facing=180°), then pivoted again at t=2.1. This oscillation is a stability bug in the CB agent's decision-making — it appears to re-evaluate the situation each step without memory of having just committed to a pursuit, allowing the backpedal heuristic to win out again when the situation metrics momentarily look like "WR approaching."

In the corner route the CB reacted to the WR's 290° jab at t=0.7 as if it were the real cut, drove laterally (t=0.8), then likely recovered when the WR snapped back. The CB is too reactive to single-step heading changes — it needs to require 2+ steps of heading persistence before committing to a pursuit direction.

**Fix needed:** Add a "commitment" mechanism to the CB observation: once the CB decides to pursue laterally, the observation should reinforce that decision for the next 2–3 steps unless the WR clearly reverses direction.

---

## N8 — Zig: WR call heading event inconsistent with physical heading (MEDIUM)

**Affected routes:** zig

At t=0.9, `WR_CALL_FOR_BALL` event has `heading: 90.0`, but the player record at that step shows `heading: 180.0`. The WR was physically facing back toward QB (180°) while the call reported 90°. At t=1.0 the WR corrects to 90°. This appears to be the WR deciding to call while mid-rotation — the decision function returns heading=90° but `apply_decision` hasn't applied it yet when the event is logged.

This is a one-step timing artifact but produces misleading telemetry and could confuse the QB (who sees heading=90° in the call event but sees the WR at 180° in the step data).

**Fix needed:** Log the call event heading from the actual physical heading (from the step's player state) rather than from the decision output, OR ensure the call event fires one step later when the heading has been applied.

---

## N9 — Post_corner: post fake only 0.2s instead of 0.4s (MEDIUM)

**Affected routes:** post_corner → DROP (separation=2.41)

Post fake phase is spec'd at t=2.0–2.4 (0.4s). WR held 45° at t=2.0 and t=2.1 (two steps = 0.2s), then broke to 315° at t=2.2 — 0.2s early. A 0.2s fake is too brief to commit a CB. The CB was still driving toward the post fake direction at t=2.1 (heading=90°, facing=152°), suggesting the fake was working, but the early break gave insufficient time for the CB to fully overcommit.

Additionally, the QB had a parse error at t=2.3, delaying the throw to t=2.4. Combined with the short fake, the DROP resulted from slightly tight coverage and WR overrunning the target by ~0.5 yd.

**Fix needed:** The intermediate phase enforcement should add a minimum step count. The observation could say "hold fake heading for AT LEAST {min_steps} steps" computed from the phase duration.

---

## N10 — Go route: WR overran landing spot (MEDIUM)

**Affected routes:** go → DROP

WR called at t=1.2, heading=0° at speed ~9.5 yd/s. QB threw at t=1.3 to (15.2, 60.9), ETA=0.22s. Projected WR position: y ≈ 59.15 + 9.5×0.22 = 61.24 yd. Ball landed at y=60.9, WR ended at y=61.05 — the WR overran the target by 0.15 yd. The throw was slightly under-led (target 0.35 yd behind WR's actual arrival point). With the ball arriving before the WR, the WR ran through the catch point.

This is a small margin but the DROP is real. The LEAD HINT in the observation provides the correct projection, but the QB's target was computed slightly short.

**Fix needed:** Minor — the QB should target slightly further upfield for a full-sprint go route where the WR shows no deceleration. The LEAD HINT already provides the math; the QB just needs to use it more precisely.

---

## Summary Table

| # | Problem | Routes Affected | Severity | Root Cause |
|---|---------|----------------|----------|------------|
| N1 | detected_cut_t still fires at t=0.5 jabs | all 10 | HIGH | threshold `t>=0.5` met by WR jabs; need persistence check or higher threshold |
| N2 | WR jab template is identical across all routes | all 10 | HIGH | LLM ignores vary-fakes guidance; need live history-based callout |
| N3 | Comeback QB throws upfield for a downfield-running WR | comeback | HIGH | QB misreads 180° heading; LEAD HINT not explicit enough |
| N4 | Double-move fake phase ended 0.3s early | double_move | HIGH | WR exits intermediate phase early; need step countdown |
| N5 | Curl: WR drifts sideways during ball-in-air | curl | HIGH | ball-in-air free-heading lets WR choose wrong direction |
| N6 | In: QB threw lob (26.9 mph) + 0.2s hold after call | in | HIGH | QB undervalued speed; needs guidance for horizontal routes |
| N7 | CB oscillates between backpedal and pursuit | in, corner | MEDIUM | no commitment memory; re-evaluates each step |
| N8 | Zig: call event heading ≠ physical heading | zig | MEDIUM | call logged before apply_decision runs |
| N9 | Post_corner: post fake only 0.2s (spec: 0.4s) | post_corner | MEDIUM | WR exits fake phase 2 steps early |
| N10 | Go: WR overran landing spot (small margin) | go | MEDIUM | QB lead slightly short for full-sprint WR |
