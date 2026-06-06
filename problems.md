# Problems Found — Route Tree Analysis (seed=42)

Results: slant→DROP, comeback→CATCH, go→SACK, double_move→CATCH, curl→CATCH,
zig→CATCH, drag→CATCH, corner→DROP, post_corner→CATCH, in→CATCH

---

## P1 — Go route: WR never calls for ball (CRITICAL)

**Affected routes:** go  
**Outcome impact:** SACK (entire play held, QB sacked at t=5.0s)

The WR call-for-ball logic is cut-gated: `_can_call()` returns True only when the WR's heading is
within `call_tolerance` degrees of `cut_heading`. For the go route, `cut_time=999.0` so the cut
window never opens and the call condition never fires. The WR ran 51 steps straight upfield without
ever signaling the QB. QB waited the entire play and was sacked.

**Fix needed:** For routes with no cut (`cut_time >= 9.0`), the WR should call for the ball when
it has sufficient separation from the CB (e.g., > 2 yards) after a minimum stem time (e.g., 1.0s
upfield). The separation-based call trigger should replace the cut-heading check for go routes.

---

## P2 — False-positive cut detection: detected_cut_t fires on first jab step (HIGH)

**Affected routes:** comeback, curl, zig, drag, double_move, post_corner, in (7 of 10)  
**Symptom:** `detected_cut_t: 0.1` or `0.2` in replay telemetry; the cut is recorded on the first
jab step, not the actual route break.

The cut-detection logic triggers on the first lateral heading change (the WR's habitual t=0.0/0.1
left-jab at 330°), recording the cut at t≈0.1 instead of the real break time. This corrupts the
QB's timing signal: the QB receives a `detected_cut_t` that is 1–2 seconds too early, which can
cause premature throw decisions or bad lead calculations.

**Fix needed:** Raise the cut-detection threshold: ignore heading changes before t=0.5s, or require
a minimum lateral displacement before registering a cut, or filter out heading changes that return
to near-0° within the next step (jab reversals vs. real breaks).

---

## P3 — WR repetitive left-jab pattern: same 330° fake every route, every step (HIGH)

**Affected routes:** all routes with stem phase (comeback, slant, curl, zig, double_move,
post_corner, corner, in — at least 8 of 10)

The WR LLM has adopted a fixed micro-deception pattern inherited from A3 route running: it jabs
left to 330° on nearly every step throughout the stem phase (t=0.0, 0.2, 0.5, 0.6, 0.8, 1.0,
...). The CB agent never bites on this pattern because:
1. It repeats identically — no variation in angle, timing, or intensity.
2. The CB's backpedal logic is purely vertical; lateral micro-jabs don't affect it.
3. A real CB would pattern-read three identical jabs in 1 second and stop reacting.

Side effects:
- Contaminates the stem phase of multi-phase routes (double_move, zig, post_corner) with
  noise that has nothing to do with the designed fake.
- Triggers P2 (false-positive cut detection).
- Artificially inflates "separation earned" metrics — the jabs aren't creating separation,
  the CB's cushion is.

**Fix needed:** The WR prompt or observation should discourage repeating the same move more than
once per route. Consider adding a note in the stem-phase observation that warns against mechanical
repetition and encourages varied timing.

---

## P4 — Multi-phase routes: intermediate fake phases skipped or garbled (HIGH)

**Affected routes:** post_corner (Phase 2 skipped), double_move (Phase 2 noisy), zig (phases
interleaved)

### post_corner
The WR jumped directly from stem (0°) to the real break (315°) at t=2.3s, skipping the 45° post
fake entirely. The post fake was never executed — the route became a simple corner, so the CB had
nothing to bite on. The catch succeeded only because of the CB's large pre-existing cushion (7.44
yd separation).

### double_move
Phase 2 (90° right fake, t=1.5–2.2s) was inconsistently executed. The WR oscillated between 0°,
60°, and 90° during the fake window rather than committing to a clean 90° break. The WR's
reasoning labeled some steps as "jab left (330°)" while actually heading 0° — the stem-phase jab
pattern bled into the fake phase. `detected_cut_t=0.1` confirms cut-detection fired on a stem jab.
The CB never committed to the fake and was not out of position at the real break.

### zig
Phase execution was garbled from step 0. The WR was already jab-oscillating at t=0.0 before the
stem was even established. The designed sequence (stem 0.6s → jab left 0.3s → cut right) was
replaced by continuous 330°/0° oscillation from t=0. The actual 270° jab appeared at t=0.6–0.7
and the 90° cut at t=0.9, but the stem phase was contaminated throughout.

**Fix needed:** The observation for multi-phase routes needs to more strongly enforce phase
sequencing — especially for the intermediate fake phase. Consider requiring the WR to hold the fake
heading for a minimum duration (1–3 steps) before the real break, rather than just passing through
it.

---

## P5 — Corner route: wrong geometry for left-side WR alignment (MEDIUM)

**Affected routes:** corner → DROP

The `corner` route uses `cut_heading=315°` (upfield-left diagonal), which is hardcoded in
`agents/scripted.py`. But the WR lines up at x=16 on a field that runs from x=0 (left sideline) to
x=53. For a WR at x=16, the outside corner is toward the left sideline, requiring decreasing x —
meaning the cut heading should be closer to 270–300° (more lateral, less upfield), not 315°.

At 315°, the WR only drifts x by ≈0.7 per yard of travel; starting at x=16, the WR reached
x≈14–15 — not near the sideline. A proper corner should end near x=4–6, forcing the CB to run
with the WR toward the boundary.

Secondary problem: the WR abandoned the corner cut at t=2.7s and reverted to heading 0° (go
route), running upfield until the QB finally threw at t=3.8s. The WR's own reasoning said
"not open, CB ~1.1–1.8 yd separation" through t=3.7s despite telemetry showing max 5.02 yd
separation, suggesting the WR's spatial reasoning was off during the route.

**Fix needed:** Change `corner` cut_heading from 315° to ~285°–300° to push toward the sideline.
Also address WR abandoning routes mid-play (see P6).

---

## P6 — WR abandons route and reverts to go route mid-play (MEDIUM)

**Affected routes:** corner → DROP (WR reverted at t=2.7 to heading 0°)  
Also seen: zig WR never cleanly transitioned between phases

After executing the corner cut (315°) for 3–4 steps, the WR reversed back to 0° (straight upfield)
and stayed there until t=3.8s when it finally called for the ball. The WR's own justification was
"not open yet" — it essentially judged the route had failed and improvised a go route.

This is a behavior issue: the WR should complete the designed route arc and call for the ball at
the geometry the play expects, not unilaterally convert to a different route because it doesn't
read separation clearly in the moment.

**Fix needed:** The observation should reinforce that once the cut is executed, the WR must
maintain the cut heading and call for the ball (within the route's call tolerance window). A WR
should not reverse heading mid-route.

---

## P7 — CB fails to pursue lateral routes: no hip-flip on horizontal cuts (HIGH)

**Affected routes:** drag, in (worst), corner, zig  
**Symptom:** CB backpedals away from WR on horizontal routes; separation is "gifted," not earned.

### drag
The WR executed a horizontal drag (heading 90°) from t=0.1. The CB backpedaled straight upfield
(heading 0°, facing 180°) from t=0.3 through the end of play — moving in the exact opposite
direction of the WR. The CB's intent was logged as "swat" but its behavior was purely vertical
backpedal. Separation at resolution: 6.39 yd (mostly the pre-existing gap widening). p_catch=0.97.

### in
WR cut cleanly to 90° at t=1.7. CB continued backpedaling straight upfield (heading 0°) for the
remainder of the play, ending at y=65.3 while WR caught at y=59.8 — 5.5 yards behind. CB never
transitioned to lateral pursuit.

The CB agent's coverage algorithm does not handle horizontal routes. The backpedal-to-maintain-
cushion heuristic is correct for vertical stems but produces the wrong behavior once the WR breaks
laterally. The CB needs a trigger that fires on WR lateral breaks and switches from vertical
backpedal to lateral pursuit (hip-flip / drive on ball).

**Fix needed:** CB observation/logic needs a lateral pursuit mode: when WR heading deviates > 45°
from vertical (0°), the CB should drive to the WR's projected catch point, not continue backpedaling
upfield.

---

## P8 — Curl: WR still rotating when ball arrives (MEDIUM)

**Affected routes:** curl → CATCH (p_catch=0.785, below expected for a clean curl)

The WR's heading at the cut step (t=1.1) was 270° (lateral), not yet 180° (back to QB). The
`WR_CALL_FOR_BALL` event fired at t=1.1 with `heading: 180.0` in the event fields, but the WR's
actual sim heading that tick was 270°. The QB threw at t=1.2 (one step after call), and the ball
arrived while the WR was still rotating from 270° to 180°. The WR was mid-rotation at catch.

A clean curl should have the WR fully facing the QB (heading ≈180°) at catch, creating a high
catch probability. Mid-rotation catch depresses p_catch and risks a dropped ball.

**Fix needed:** Either (a) add a 1-step delay to the QB's throw on a curl (wait for WR to complete
the turn) so the ball arrives when the WR is set, or (b) adjust the call-for-ball logic to fire one
step earlier so the WR has time to turn before ball arrival.

---

## P9 — QB lead calculation: under-leading and over-leading WR (MEDIUM)

**Affected routes:** slant → DROP (under-led), corner → DROP (over-led by ~1 yd)

### slant
A parse error on the first LLM call delayed QB decision by 1 tick. This caused the throw to target
[16.8, 63.7] but the WR ended at [17.3, 64.1] — ball arrived behind the WR. The WR had already
passed the landing spot when the ball arrived.

### corner
QB targeted [14.8, 85.0], estimating WR would be at y≈83.8 at arrival. WR reached y=83.96
(froze there in final frames). Ball landed ~1 yard beyond. QB over-led by roughly one step.

Both errors trace to the QB's lead formula not correctly accounting for either (a) the tick delay
from parse errors, or (b) the WR freezing/decelerating at route's end.

**Fix needed:** The QB lead calculation should be audited against the WR physics. The formula needs
to account for WR speed at throw time, not just average route speed. Parse errors that delay the
decision must cause the QB to recalculate based on the new WR position.

---

## P10 — Drag route: stem phase not executed (MINOR)

**Affected routes:** drag

The drag route spec is `[(0.3, 0.0), (999, 90.0)]` — 0.3s upfield stem before the horizontal
break. In the replay, the WR's heading was already at 90° by t=0.1 (one step in). The upfield
displacement at cut time was ≈0.2 yards instead of the ~1.5 yards a proper 0.3s stem would produce.
The drag route became essentially a pure horizontal route from snap.

This may be because the WR's first reasoning step (t=0.0) was spent on a left-jab (the P3 pattern)
rather than an upfield step, which immediately ate the 0.3s stem budget. The stem phase evaporated.

**Fix needed:** The short 0.3s drag stem is too small to survive the jab-pattern noise. Either
extend the stem to 0.6–0.8s, or address the root jab problem (P3) which eliminates the stem.

---

## Summary Table

| # | Problem | Routes Affected | Severity | Root Cause |
|---|---------|----------------|----------|------------|
| P1 | Go route: no call-for-ball trigger | go | CRITICAL | call logic is cut-gated; no cut = no call |
| P2 | False-positive cut detection at t=0.1 | 7/10 | HIGH | jab at t=0.0 triggers cut detector |
| P3 | Repetitive same left-jab every stem step | 8/10 | HIGH | WR LLM defaults to 330° jab pattern |
| P4 | Multi-phase fake phases skipped/garbled | post_corner, double_move, zig | HIGH | WR substitutes jab pattern for designed fake |
| P5 | Corner: wrong cut heading geometry | corner | MEDIUM | 315° wrong for x=16 WR; should be ~285–300° |
| P6 | WR abandons route mid-play | corner | MEDIUM | WR converts to go route when not immediately open |
| P7 | CB no lateral pursuit on horizontal routes | drag, in, corner, zig | HIGH | CB backpedal logic doesn't trigger on lateral cuts |
| P8 | Curl: mid-rotation catch | curl | MEDIUM | QB throws before WR completes 180° turn |
| P9 | QB lead miscalculation | slant, corner | MEDIUM | parse error delay + no WR decel accounting |
| P10 | Drag stem too short to survive jab noise | drag | MINOR | 0.3s stem eaten by P3 jab on first step |

---

# Round 2 — Ollama qwen3:8b run (seed=42, post-fix)

Results: slant→DROP, comeback→INCOMPLETE, go→DROP, double_move→INTERCEPTION,
curl→INCOMPLETE, zig→DROP, drag→CATCH, corner→CATCH, post_corner→DROP, in→DROP

Score: 2 CATCH, 5 DROP, 1 INTERCEPTION, 1 INCOMPLETE

---

## N1 — detected_cut_t threshold still fires on t=0.5 jabs (HIGH)

**Affected routes:** all 10  
**Symptom:** detected_cut_t=0.5 in every replay — still a false positive in 9 of 10 routes.

The fix raised the gate to `t >= 0.5` but the WR jabs at exactly t=0.5 on every route, so the condition is still met. In corner the WR jabbed to 290° (same as the cut heading) at t=0.7, firing the detector 1.5s before the real cut.

The detector fires on single-step jabs. A real cut is sustained — the WR holds the new heading for multiple steps. A jab snaps back to 0° in 1 step.

**Fix:** Implemented — 2-step heading persistence required before confirming a cut. Jab snap-backs (heading returns within 20° of pre-jab heading) are discarded.

---

## N2 — WR jab template is identical across all routes (HIGH)

**Affected routes:** all 10  
**Symptom:** Every route shows the same alternating 330°/30° pattern. 330° appears 4–8 times per route. Prompt and observation changes did not break the habit.

post_corner: 330° at t=0.0, 0.3, 0.5, 0.7, 1.0, 1.3, 1.6, 1.8 (8 occurrences). corner: 9 jabs in 2.2s, 330° repeated 4 times. In every route the WR uses the same template regardless of route design or CB alignment.

**Status: OPEN — not yet solved. Need to think about how to upgrade WR deception fundamentally. Self-action history (N7 fix) may help the WR notice its own pattern. Further approach TBD.**

---

## N3 — Comeback: QB throw direction inverted (HIGH)

**Affected routes:** comeback → INCOMPLETE (ball_offset=2.44 yd)

WR called at t=2.2 heading 180° (running back toward QB, decreasing y). QB threw to target y=63.7. At throw time WR was at y=63.35 moving toward lower y. Correct target: y ≈ 63.35 − 3.71×0.26 ≈ 62.4. QB threw to y=63.7 — upfield from where the WR was. WR ended at y=62.19, ball at y=63.7 — 1.51 yd miss in wrong direction.

**Fix:** Implemented — LEAD HINT now explicitly labels y-direction ("y is DECREASING toward QB" vs "y is INCREASING upfield") so the QB cannot confuse heading 180° as upfield motion.

---

## N4 — Double-move: fake phase ended 0.3s early; resulted in interception (HIGH)

**Affected routes:** double_move → INTERCEPTION

Fake-right phase (90°) specified t=1.5–2.2. WR held 90° from t=1.5–1.8 and snapped back at t=1.9 — 0.3s early. At t=1.9 the CB was only 1.8 yd away, not yet committed to the wrong direction.

**Status: SKIP for now. This is AI decision-making — we guide, not enforce. The AI should decide when to break based on the situation.**

---

## N5 — Curl: WR drifts sideways during ball-in-air (HIGH)

**Affected routes:** curl → INCOMPLETE

WR called at t=1.4 heading 180° (locked). During ball-in-air at t=1.6: WR heading changed to 90°, drifting away from the ball. Ball landed 1.5 yd from WR.

**Status: SKIP — part of a larger open question about ball-in-air tracking behavior across all routes. Do not patch curl specifically.**

---

## N6 — In route: QB threw a lob (26.9 mph) and waited 0.2s after call (HIGH)

**Affected routes:** in → DROP (separation=1.67)

QB threw at 26.9 mph (ETA=0.39s vs. 0.19s at regular speed), giving the CB nearly double time to close. QB also waited 0.2s after the WR called.

**Status: SKIP — this is a fundamental QB decision-making question (throw speed selection, when to throw after call) that needs broader discussion.**

---

## N7 — CB oscillates between backpedal and lateral pursuit (MEDIUM)

**Affected routes:** in (t=2.0 reversal), corner (t=0.8, 1.3 false reactions)

CB correctly pivoted to pursue at t=1.7, then reverted to backpedal at t=2.0, then pivoted again at t=2.1. No memory of having just committed to a direction.

**Fix:** Implemented — CB (and WR) now see their own recent action history in each observation step, showing headings and mode they chose. This gives both agents the context to notice their own patterns and make more consistent decisions without enforcing any particular behavior.

---

## N8 — Zig: call event heading ≠ physical heading (MEDIUM)

**Affected routes:** zig

At t=0.9, `WR_CALL_FOR_BALL` event reports heading=90.0 but physical heading was 180.0 (one step before apply_decision runs).

**Status: CLOSED — not a real problem. The event heading reflects the WR's intended heading (what it decided), and the QB uses the call to anticipate where the WR is going, not where it physically is that instant. The 1-step lag is an expected simulation artifact and does not materially affect QB decision-making.**

---

## N9 — Post_corner: post fake only 0.2s instead of 0.4s (MEDIUM)

**Affected routes:** post_corner → DROP (separation=2.41)

WR held the 45° post fake for 2 steps (0.2s) instead of the spec'd 4 steps (0.4s).

**Status: SKIP — the AI decides when to break. We can inform the WR what the route expects, but we do not force minimum phase durations. If the WR judges the CB is committed, it may break early. That is a valid decision.**

---

## N10 — Go: WR overran landing spot (MEDIUM)

**Affected routes:** go → DROP

WR ran through the catch point by ~0.15 yd.

**Status: CLOSED — not a code problem. This is the QB's and WR's spatial judgment. The simulation exists to test exactly this kind of LLM decision-making. A 0.15 yd miss is within the expected range of LLM imprecision.**

---

## Summary Table (Round 2)

| # | Problem | Routes Affected | Severity | Status |
|---|---------|----------------|----------|--------|
| N1 | detected_cut_t still fires at t=0.5 jabs | all 10 | HIGH | FIXED — 2-step persistence |
| N2 | WR jab template identical across all routes | all 10 | HIGH | OPEN — approach TBD |
| N3 | Comeback QB throw direction inverted | comeback | HIGH | FIXED — y-direction labels in LEAD HINT |
| N4 | Double-move fake phase ended 0.3s early | double_move | HIGH | SKIP — AI decision |
| N5 | Curl: WR drifts sideways during ball-in-air | curl | HIGH | SKIP — broader ball-in-air question |
| N6 | In: QB threw lob + waited after call | in | HIGH | SKIP — broader QB throw-speed question |
| N7 | CB/WR oscillates without action memory | in, corner | MEDIUM | FIXED — self-action history in observations |
| N8 | Zig: call event heading ≠ physical heading | zig | MEDIUM | CLOSED — expected 1-step artifact, not a real bug |
| N9 | Post_corner: post fake only 0.2s | post_corner | MEDIUM | SKIP — AI decision |
| N10 | Go: WR overran landing spot (0.15 yd) | go | MEDIUM | CLOSED — LLM spatial judgment, not a code bug |
