# Problems — Full Run Analysis (seed=42, gpt-5-nano / A4 prompts)

## Run 5 Results (latest run, post P-NEW + angle-blacklist + ball-in-air-lock + QB judgment fixes)

| Route | Outcome | Notes |
|-------|---------|-------|
| slant | DROP | WR called at t=1.9 (post-cut ✓), QB used medium speed, but ball arrived 4.83 yd from WR — QB threw to wrong geometry |
| comeback | CATCH | QB waited through 6 parse errors but still connected (9.36 yd sep, p=0.886) ✓ |
| go | INCOMPLETE | QB threw WITHOUT a WR call, at t=0.8 — P-NEW fix did not help here (WR never called) |
| double_move | CATCH | WR held 90° fake t=1.5–1.7, QB threw at t=1.8 without WR call, ball to (20.1,61.3), sep=4.83, p=0.794 ✓ |
| curl | DROP | WR called at t=1.3 heading 270° mid-rotation, then went to 150° during ball flight — heading abandonment |
| zig | PBU | WR executed 270° fake well (t=0.6–0.8) then broke 90°, called t=1.2, CB barely missed, sep=0.75 |
| drag | CATCH | WR executed long stem w/ 0°/90°/40° jabs, finally called at t=1.5 heading 90°, sep=6.39 ✓ |
| corner | CATCH | WR broke 290° at t=2.2, called at t=2.3 — first time corner actually completed the real cut ✓ |
| post_corner | PBU | Post fake held 45° for 5 steps (t=2.0–2.4), real break to 315°, sep=1.54 — CB barely in range |
| in | INTERCEPTION | WR called at t=0.8 STILL ON STEM (heading 0°), CB had `go_for_pick` intent, CB picked it off |

**Score: 4 CATCH/1 DROP(slant miss)/2 PBU/1 INCOMPLETE/1 INTERCEPTION = 4 catches out of 10**

Comparison vs Round 4 (A4r4, GPT-5-nano): A4r4 was 4C/2D/3PBU/1INT. This run is approximately equivalent with mixed changes — corner improved, in got worse (INT not PBU).

---

## 1. WR DECEPTION PATTERNS

### R1 — WR still calls based on current separation, not projected separation (CRITICAL, OPEN)

**Affected routes:** in (most damaging — INTERCEPTION), slant, drag, zig  
**What we fixed:** P-NEW prompt said "anticipate future separation" before calling.  
**What actually happened:**

- **In route:** WR called at t=0.8 heading 0° with current separation 2.65 yd from the CB. The WR was still on its upfield stem — it had NOT yet executed the 90° cut. The WR judged "open by >2 yd" on the stem and called immediately. The real cut (90° in-break) never happened. QB threw to a go-route-style projection. CB with `go_for_pick` intent had already positioned for the ball — INTERCEPTION.
- **Slant:** WR called at t=1.9 heading 40° (correct post-cut), but the stem-phase call habit means WR is often not anticipating the post-cut window — it just fires when current separation > 2 yd.
- The prompt fix (anticipate trajectory, call after cut) worked for routes that have explicit cut windows. It failed for the in route because the WR decided the current situation was already open enough to call.

**Root cause:** WR measures current Euclidean distance to CB, not projected post-cut gap. The stem phase keeps the WR upfield of the CB and separation appears ">2 yd" before the cut even happens.

**Impact:** In-route: INTERCEPTION. Zig: nearly a PBU due to calling too early during rotation.

---

### R2 — WR jab pattern: some improvement but still template-heavy (HIGH, PARTIALLY IMPROVED)

**Affected routes:** slant, comeback, go, double_move, curl, post_corner, in, corner  
**Previous state:** Pure 330°/30° alternation on ALL routes.

**What changed in Run 5:**
- More routes show **actual jab variation** (20°, 30°, 40°, 340° in addition to 330°):
  - `in`: jabbed 340° (t=0.1), 340° (t=0.5, t=0.7), 20° (t=0.6) — varied leftward micro-jabs
  - `curl`: jabbed 30° (t=0.2), 30° (t=0.8) — showing rightward fakes too
  - `comeback`: 30° (t=0.9), 20° (t=1.2), 30° (t=1.8) — some right variation
- Some routes like corner went **pure straight stem** with no micro-jabs at all (0° throughout until t=2.2 real cut)
- The angle blacklist (from O7/N2 fix) appears to have **broken the strict 330°/30° lock** somewhat

**What's still wrong:**
- The jabs **never produce CB displacement**. Looking at CB heading changes across all 10 routes: CB heading ΔHdg is ≤ 5° in response to WR jabs on every single route. The CB effectively ignores all pre-cut fakes.
- Post-corner: WR held a full 45° post fake for **5 consecutive steps** (t=2.0–2.4) — this is the **best fake execution** we've ever seen. But the CB still backpedaled straight at heading ~5° the entire time (never moved laterally to bite on the post fake). sep=1.54 at resolution.
- Comeback: WR's fakes are all leftward small angles (20°–30°) — no variation toward field-away side.
- The **fundamental problem remains**: small angle jabs (even varied ones) do not trigger the CB's lateral pursuit logic. The CB is only doing straight backpedal unless it detects a sustained cut.

**LLM freedom assessment:** The WR is now showing *more creative reasoning* — it explains jab direction choices, references CB's previous reactions, and varies angles. But the LLM is not generating truly large deception moves (45°–90° committed fakes during the stem) unless the route spec demands it (like post_corner's 45° phase). This is a prompt guidance gap, not an LLM incapability.

---

### R3 — CB never reacts to WR stem-phase jabs: pure deterministic backpedal (HIGH, OPEN)

**Affected routes:** All 10  
**Symptom:** CB heading during stem phase is almost always within 5–10° of straight upfield (0°–5°) regardless of WR lateral movement. Even when the WR holds a direction for 2+ steps, the CB doesn't track it. CB reasoning consistently says "WR is approaching, keep cushion while watching for the cut" — a rote template response.

**Evidence from Run 5:**
- **post_corner**: WR held 45° fake for t=2.0–2.4 (5 steps). CB heading: 5°, 5°, 5°, 5°, 5° throughout. CB never laterally responded.
- **double_move**: WR held 90° fake t=1.5–1.7 (3 steps). CB moved from x=15.64 to x=15.23 — that's leftward (270°), moving AWAY from WR's rightward fake. CB was already at x=15.6 before the fake and ended at x=15.2 — it actually retreated from the fake direction.
- **corner**: WR broke 290° at t=2.2. CB at t=2.2 was at x=15.86, y=61.7. At resolution x=14.38, y=65.15 — CB moved upfield-leftward (toward sideline, heading ~326°). CB was pursuing after the throw was in air, not before.
- **zig**: The 270° fake (t=0.6–0.8) shows the CB's best response: CB moved from x=15.79 to x=15.2 (heading 270°) — following the WR leftward. But this was because the WR had actually physically moved to x=14.05, not because the CB was "fooled."

**Is the CB just copying deterministic guidance?**  
The CB uses an LLM, so it's not deterministic in the strict sense — but its reasoning chain is: "WR approaching → maintain cushion → backpedal." The LLM always reaches for this template when the WR is running straight. The CB only breaks this pattern when:
1. Ball is in the air (it actively pursues landing zone)
2. WR makes a sustained multi-step lateral break (like the zig's 270° phase)

The CB's prompt likely doesn't give it enough "signal" from small jabs to justify committing to a lateral direction. It's playing conservatively — which is actually correct CB technique — but it means WR micro-jabs are useless. We need to ask: **should we help CB respond to fakes more, or help WR create deception that actually threatens CB's positioning?**

---

## 2. QB BEHAVIOR: DOES QB WAIT FOR WR TO BE OPEN OR THROW IMMEDIATELY AFTER PRE-CUT CALL?

### R4 — QB judgment on calls: showing good restraint in some cases (MEDIUM, MIXED)

**Evidence from Run 5:**

**Good QB judgment (waited appropriately):**
- **Comeback:** WR called at t=2.2. QB had 6 consecutive parse errors (t=2.2–2.7). Threw at t=2.8. Despite being forced to wait by parse errors, the throw was good (9.36 yd sep, CATCH).
- **Slant:** WR called at t=1.9. QB threw at t=2.0 (1 step later). Short wait was appropriate.
- **Corner:** WR called at t=2.3. QB threw at t=2.4 (1 step later). Appropriate.

**Bad QB judgment (threw too soon or without call):**
- **Go route:** QB threw at t=0.8 WITHOUT any WR call. `wr_call_t: null`. This is the same P1 problem from Round 1 — the go route WR never called, but QB just threw anyway at t=0.8 when it saw the WR's t=0.7 jab-right (30°). QB reasoning: "medium option ensures ball arrives when WR is at (17.5,56.4)." WR was at y=55.56 heading 0°. The projected catch point (17.5,56.4) was never reached — ball landed 1.49 yd away (INCOMPLETE).
- **Double_move:** QB threw at t=1.8 WITHOUT WR call (`wr_call_t: null`). QB judged the WR was open during the fake phase (heading 90°). In this case it worked (CATCH) because WR stayed on 90° — but it was luck not coordination.
- **In route:** WR called pre-cut at t=0.8 heading 0° (still on stem). QB waited 1 step (t=0.9: "no clear open window yet"), then threw at t=1.0 leading WR to (15.7, 57.4) — a go-route-style target. The QB tried to exercise judgment but the underlying call was wrong (WR called on stem, QB threw to a stem-trajectory target). INTERCEPTION.

**Key finding:** The QB judgment-after-call fix (from left_off.md) IS working in some cases — QB does evaluate whether to throw when WR calls. But it breaks down when: (a) go route has no call at all and QB freelances, (b) double_move QB also freelances.

---

## 3. WR POST-CUT CALLING: ANTICIPATION OF FUTURE POSITION

### R5 — WR calls mid-rotation or on-stem, not after completing cut (HIGH, PARTIALLY FIXED)

**Affected routes:** curl, in, zig (partially)

**What's improved:**
- Slant: WR called at t=1.9 heading 40° — this is AFTER the cut to 40°. The WR held the cut heading for at least 1 step before calling. ✓
- Corner: WR called at t=2.3 heading 290° — called while executing the cut. ✓  
- Post_corner: WR called at t=2.4 heading 315° on the first step of the real break. ✓ (slightly early but acceptable)
- Drag: WR called at t=1.5 heading 90° — at least 2 steps into the cut. ✓
- Comeback: WR called at t=2.2 heading 270° (mid-rotation to 180°). Still mid-turn, but the QB saw heading=180° in the call event (intended heading) and the eventual 180° execution was clean.

**Still failing:**
- **In route:** WR called at t=0.8 heading 0° — still on upfield stem, **never executed the in-break cut**. The P-NEW fix was supposed to prevent this but the WR reasoned "open >2 yd" and called immediately. This is the most damaging case.
- **Curl:** WR called at t=1.3 with physical heading 270° (mid-rotation). The event header reported heading=180° (intended), but the body was sideways. The 150° ball-flight heading drift (O1 issue) then lost the ball.
- **Zig:** WR went from 270° fake to 0° at t=0.9 (parse error), then back to 90° at t=1.0 and 1.2. Called at t=1.2 heading 90°. Reasonably timed but the route was chaotic.

---

## 4. BALL-IN-AIR HEADING MANAGEMENT

### R6 — Ball-in-air heading lock: significantly improved but one failure (MEDIUM, MOSTLY FIXED)

**Routes where heading stayed locked during ball flight:**
- Slant: held 40° throughout ball flight ✓
- Comeback: held 180° throughout ball flight ✓  
- Double_move: held 90° throughout ball flight ✓
- Corner: held 290° throughout ball flight ✓
- Drag: held 90° throughout ball flight ✓
- Post_corner: held 315° throughout ball flight ✓
- Zig: held 90° throughout ball flight ✓

**Still failing:**
- **Curl:** WR called at t=1.3 heading 270° (mid-turn). At t=1.6 during ball flight WR heading changed to 150° — the WR drifted laterally despite the ball-in-air lock instructions. The WR's reasoning at t=1.6: "sharp 30° cut left to deceive CB's intercept projection" — the WR was STILL executing deception moves during ball flight. Outcome: DROP, sep=2.31.

The ball-in-air lock is now working for 9/10 routes. The curl failure is a special case because the WR called mid-rotation (heading 270° not 180°), so the lock anchored on the wrong heading.

---

## 5. CB SHADOWING QUALITY

### R7 — CB backpedal is pure vertical, never laterally pursues during stem phase (HIGH, OPEN)

**All 10 routes:** CB heading during stem phase is 0°–10° (nearly pure upfield backpedal), mode="backpedal", reasoning="WR is still approaching and I want to keep cushion while watching for the cut" — this **exact phrase appears verbatim across almost every step of every route**. It is a reasoning template.

**CB positional analysis at cut time:**
| Route | CB heading at WR's cut | CB lateral displacement from WR? |
|-------|------------------------|----------------------------------|
| slant | 5° (backpedal) | CB x=16.87 vs WR x=19.97 at cut — CB inline/left |
| comeback | 5° | CB 4+ yd upfield of WR at cut — completely out of position ✓ |
| go | 5° | CB was ahead of WR the whole time (cushion technique) — correct |
| double_move | 5° | CB behind WR despite 90° fake |
| curl | 5° | CB 1.67 yd upfield when WR cut back |
| zig | 270° following WR | CB actually tracked the 270° fake laterally ✓ |
| drag | 5° | CB 6+ yd upfield at ball arrival — completely gone ✓ |
| corner | 1° | CB 7+ yd behind WR at ball arrival ✓ |
| post_corner | 5° | CB ~1.5 yd from WR at resolution (tight) |
| in | 0° backpedal → then goes for pick | CB was 0.34 yd from catch point — INTERCEPTION |

**Notable:** The `go_for_pick` intent on the in route gave the CB specific instructions to position for an interception, not just backpedal. This is what produced the INT — it wasn't CB route reading, it was CB intent mode. The CB's random intent selection apparently chose `go_for_pick` for the in route and the CB specifically played the interception angle.

**LLM freedom question (CB):** The CB is clearly over-constrained. Its reasoning is a near-identical template step after step. A real CB would show: foot fire at the LOS, press or off coverage decisions, reading WR hips for cut anticipation, driving on the ball. Our CB does none of this during the stem phase. The CB needs more freedom + better context to make coverage decisions.

---

## 6. OVERALL QUALITY ASSESSMENT

### Route Running Quality
- **Good:** Comeback (clean 180° cut + acceleration), Double_move (held 90° fake for 3 steps), Post_corner (held 45° fake for 5 steps — best fake execution in any run)
- **Mediocre:** Zig (chaotic but recovered), Corner (stem was clean, cut was executed)
- **Bad:** Curl (mid-rotation call, wrong heading during flight), In (called on stem, never ran the route), Slant (right cut direction but QB aimed wrong), Go (QB freelanced, WR never signaled)
- **Detected cut threshold still fires early:** `detected_cut_t: 0.1` for slant, `0.3` for curl, `0.8` for go/drag, `0.7` for in. The persistence-check fix from N1 is not eliminating all false positives.

### QB Accuracy
- Comeback: 9.36 yd sep, led perfectly downfield ✓
- Double_move: 4.83 yd sep, lateral lead correct ✓
- Drag: 6.39 yd sep, clean lateral lead ✓
- Corner: 6.66 yd sep ✓
- **Slant: 4.83 yd separation but DROP** — the geometry was wrong. QB targeted (19.5, 67.7) but WR ended at (19.97, 68.25) — off by ~0.7 yd. The WR overran the landing point.
- **Go (INCOMPLETE):** QB targeted (17.5, 56.4), ball_offset=1.49 yd. WR was at (16.46, 57.46) — WR was past the target point y-wise but wrong x-wise. Freelance throw with wrong geometry.
- **In (INTERCEPTION):** Target (15.7, 57.4) was reasonable given WR's heading 0°, but the WR had not cut yet. Ball and CB arrived at the same spot.

### CB Quality
As noted in R7: pure vertical backpedal template on 9/10 routes (only zig showed lateral tracking). The CB is not a realistic defender — it can't press, doesn't read hips, doesn't react to jabs, and only pursues after the real cut is sustained for 2+ steps. The `go_for_pick` intent mode is the only mechanism that makes the CB dangerous.

---

## PRIOR PROBLEMS — TRACKING STATUS

### From Round 1 (P-series) — Status Update

| # | Problem | Status |
|---|---------|--------|
| P1 | Go: no call trigger (no cut = no call) | **STILL OPEN.** Go route WR never called in Run 5. QB freelanced and missed. |
| P2 | False-positive cut detection | **PARTIALLY FIXED.** Persistence check helps but `detected_cut_t` still fires early on curl (0.3), slant (0.1). |
| P3 | WR repetitive left-jab pattern | **PARTIALLY FIXED.** Angle variation improved. Pure 330° lock broken. But CB still unaffected. |
| P4 | Multi-phase routes skipped/garbled | **IMPROVED.** Post_corner held 45° fake for 5 steps (best ever). Double_move held 90° for 3 steps. |
| P5 | Corner: wrong cut heading geometry (315° should be ~290°) | **FIXED.** Corner now uses 290° and WR successfully executed it in Run 5. Outcome: CATCH. |
| P6 | WR abandons route mid-play | **FIXED.** Corner no longer abandoned. WR held 290° all the way to the call. |
| P7 | CB no lateral pursuit on horizontal routes | **STILL OPEN.** CB backpedals straight upfield even on drag/in routes. |
| P8 | Curl: QB throws before WR completes 180° turn | **STILL OPEN.** WR called at 270° (mid-rotation). Curl remains a DROP. |
| P9 | QB lead miscalculation | **PARTIALLY FIXED.** Comeback fixed. Slant still missed by ~0.7 yd. Go freelance miss. |
| P10 | Drag stem too short | **FIXED.** Drag now runs a long stem (15 steps) before cutting at t=1.5. CATCH. |

### From Round 2 (N-series) — Status Update

| # | Problem | Status |
|---|---------|--------|
| N1 | detected_cut_t fires on jabs | **PARTIALLY FIXED.** Persistence check implemented. Still fires early on some routes. |
| N2 | WR cookie-cutter 330°/30° jabs | **PARTIALLY FIXED.** More variation in Run 5. Angle blacklist is working. But CB unaffected. |
| N3 | Comeback: QB throw direction inverted | **FIXED.** Comeback CATCH, ball went to correct downfield target. |
| N4 | Double-move fake phase ended early | **IMPROVED.** Fake held 3 steps in Run 5, better than 0.3s in Round 2. |
| N5 | Curl: WR drifts sideways during ball-in-air | **STILL OPEN.** Run 5: WR went to 150° during ball flight. Different heading, same failure mode. |
| N6 | In: QB lob throw + delay | **CHANGED.** Run 5: QB threw bullet (54.3 mph) immediately (0 delay after call at t=0.8). But the call was wrong — WR hadn't cut yet — so speed didn't help. INTERCEPTION. |
| N7 | CB oscillates between backpedal and pursuit | **IMPROVED.** In Run 5 CB didn't oscillate. Backpedal was more consistent. But it's consistently ignoring fakes. |
| N8 | Zig: call event heading ≠ physical heading | **CLOSED.** Not observed as a problem in Run 5. |
| N9 | Post_corner: post fake only 0.2s | **IMPROVED.** Run 5: 5 steps (0.5s) of fake. But CB didn't bite anyway. |
| N10 | Go: WR overran landing spot (0.15 yd) | **NEW VARIANT.** Go route: QB freelanced, ball 1.49 yd off. Different cause. |

### From Round 3 (O-series) — Status Update

| # | Problem | Status |
|---|---------|--------|
| O1 | WR changes heading during ball-in-air | **MOSTLY FIXED.** 9/10 routes held heading. Curl still fails (called at wrong heading). |
| O2 | WR abandons corner break | **FIXED.** Corner executed cleanly in Run 5. |
| O3 | Go: QB target behind CB | **CHANGED.** Go QB freelanced at t=0.8 — wrong geometry entirely. |
| O4 | Slant: WR cut to 40° instead of ~315° | **CHANGED.** Slant WR now cuts to 40° and calls — but QB missed. Slant cut direction is still shallow-right, not a true crossing slant. |
| O5 | Double move: WR runs east during fake | **IMPROVED.** CATCH in Run 5. WR stayed in bounds. |
| O6 | Post_corner: 0.7s call delay after real break | **IMPROVED.** Called immediately at break (t=2.4). |
| O7 | Cookie-cutter 330°/30° jabs | **PARTIALLY FIXED.** Same as N2. |
| O8 | QB lead direction wrong for lateral routes | **IMPROVED.** Drag CATCH with correct lateral lead. |

---

## NEW PROBLEMS — Run 5 Specific

### A1 — In route: WR called pre-cut on stem, QB threw to wrong geometry, INTERCEPTION (CRITICAL)

**Route:** in → INTERCEPTION  
**What happened:** WR stem at heading 0°, CB 2.65 yd ahead at y=57.19 vs WR y=54.53. WR decided "open >2 yd" and called at t=0.8 heading 0°. The in-route cut (90° toward center) was never executed. QB held 1 step ("no clear open window"), then threw at t=1.0 leading WR on a 0° (upfield) trajectory to (15.7, 57.4). CB had `go_for_pick` intent and was positioned exactly at the ball's landing zone. INTERCEPTION.

**Root cause:** WR measured current vertical separation (CB behind and above), thought it was open, and called before the 90° cut. The "anticipate future trajectory" prompt guidance was not internalized — the WR didn't project: "After I cut 90°, where will I be vs. the CB?"

**Why it wasn't caught by our fixes:** The prompt says "call AFTER the cut." But the WR reasoned it was already past the CB (it was, vertically) and called. The distinction between "upfield of CB on a stem" and "actually open after breaking across" wasn't made.

---

### A2 — Slant: QPB targeted wrong leading point despite WR calling post-cut (MEDIUM)

**Route:** slant → DROP  
**What happened:** WR cut to 40° at t=1.9, called heading 40°, QB threw at t=2.0 to (19.5, 67.7). WR reached (19.97, 68.25) — 0.69 yd past the landing point with the ball arriving at the wrong angle. The throw was too short for the WR's actual trajectory. `separation: 4.83` at END (ball was 4.83 yd from WR, not WR from ball — ball overshot or WR overran).

**Note from telemetry:** `max_separation: 5.02` — this field equals the separation at resolution in every replay, suggesting the max was never higher than the end state. Ball flew past the WR's catch window.

---

### A3 — Go route: QB threw without WR call, freelanced to wrong target (HIGH)

**Route:** go → INCOMPLETE  
**What happened:** WR never called for ball (`wr_call_t: null`). At t=0.7 WR jabbed right to 30°. QB interpreted this as a throw signal and threw at t=0.8 to (17.5, 56.4) with 40.6 mph. WR was at (16.46, 55.56) heading 0°, and the ball_offset was 1.49 yd. The WR was still accelerating upfield and had not broken to any route direction.

**This is P1 from Round 1, still not fixed.** The go route WR never calls because (a) the stem phase is `cut_time=999.0` and (b) the WR keeps jab-returning and never judges a clean open window. Worse, the QB now freelances after seeing a jab, treating it as a directional signal.

**Additional issue:** QB logic that was supposed to throw only when WR calls is being overridden when the QB thinks it sees an opening. The "use your own judgment" block in the QB observation may be too permissive.

---

### A4 — detected_cut_t still misfires (MEDIUM, PERSISTENT)

**Observed in Run 5:**
- Slant: `detected_cut_t: 0.1` — jab at t=0.0 (heading 30°) triggered detector
- Curl: `detected_cut_t: 0.3` — jab at t=0.2 (heading 30°) triggered detector
- Go: `detected_cut_t: 0.8` — WR jab at t=0.7 (30°) triggered detector (this is when QB threw)
- In: `detected_cut_t: 0.7` — jab at t=0.7 (340°) triggered detector
- Zig: `detected_cut_t: 0.6` — first 270° step (may be correct here)
- Drag: `detected_cut_t: 0.8` — jab at t=0.7 (90°, real cut start actually)

The go route case is particularly damaging: detected_cut_t fired at 0.8 (the jab moment) and this correlates exactly with when the QB decided to throw.

---

## FUNDAMENTAL DESIGN QUESTIONS (for experiment steering)

### Q1 — LLM freedom: are we too restrictive?

**Current state:** We have:
- Prompt guidance for cut timing, anticipation, fake variety
- Structural blacklists (angle blacklist in observation)
- Ball-in-air heading lock (observation)
- Self-action history (observation)

**Where the LLM is showing genuine spatial reasoning (good):**
- Post_corner: WR held the fake for 5 steps, reasoning about the CB's commitment — this was NOT scripted, the WR evaluated and chose to hold
- Comeback: WR and QB coordinated cleanly on a comeback despite 6 QB parse errors
- Double_move: QB freelanced a throw during the WR's fake phase and it worked (the WR maintained heading through ball flight)
- Drag: WR executed a long stem with varied jabs (40°, 90°, 330°, then cut 90°), showed adaptive reasoning

**Where the LLM is failing from lack of physical intuition:**
- WR calling pre-cut because current Euclidean distance looks large
- WR ignoring the heading-lock during ball flight (one failure left)
- QB interpreting a jab as a call signal (go route)
- CB never physically committing to a pursuit direction during stem phase

**Verdict:** The guidance level is appropriate for the cuts and phases. The failure modes are mostly about **spatial projection** (WR thinking about current state not future state, CB thinking about cushion maintenance not pursuit angles). More freedom would not help here — more precise *context* (show WR its projected position post-cut vs CB position) would.

### Q2 — CB: is it just copying deterministic guidance?

**Yes, partially.** The CB's step-by-step reasoning is a near-identical template: "WR approaching → backpedal → maintain cushion." This appears on 80%+ of stem-phase steps. It is LLM behavior (not hardcoded) but the LLM always resolves to the same strategy because the observation context doesn't give it enough information to do otherwise:
- CB doesn't know the route type
- CB doesn't see WR's cut history contextually
- CB doesn't have explicit guidance on when to fire on the ball vs. maintain cushion

The `go_for_pick` intent is the only non-backpedal behavior, and it is randomly assigned. A real CB would have these tools: press coverage, jam at LOS, drive on ball, hip-flip, backpedal. Ours only does backpedal + a random intent. **The CB needs more behavioral richness if this experiment is to test real separation quality.**

---

## SUMMARY TABLE

| ID | Problem | Routes | Severity | Status |
|----|---------|--------|----------|--------|
| R1 | WR calls on stem (pre-cut), not after cut | in, drag, slant | CRITICAL | OPEN |
| R2 | WR jab variation improved but CB unaffected | all 10 | HIGH | PARTIALLY FIXED |
| R3 | CB pure backpedal template — no real coverage | all 10 | HIGH | OPEN |
| R4 | QB judgment on calls: mostly good but freelances on go | go, in | MEDIUM | PARTIALLY FIXED |
| R5 | WR post-cut calling: improved for most, still failing for in/curl | curl, in | HIGH | PARTIALLY FIXED |
| R6 | Ball-in-air heading: mostly fixed, curl still fails | curl | MEDIUM | MOSTLY FIXED |
| R7 | CB no lateral pursuit during stem phase | all 10 | HIGH | OPEN |
| A1 | In route: pre-cut call caused INTERCEPTION | in | CRITICAL | NEW |
| A2 | Slant: QB targeted wrong leading point post-cut | slant | MEDIUM | NEW |
| A3 | Go route: QB freelanced without WR call, missed | go | HIGH | NEW |
| A4 | detected_cut_t still misfires on jabs | slant,curl,go,in | MEDIUM | PERSISTENT |
| P1 | Go route: WR never calls (cut_time=999) | go | CRITICAL | OPEN |
| P7 | CB no lateral pursuit on horizontal routes | drag, in, corner | HIGH | OPEN |
| P8 | Curl: WR calls mid-rotation (270° not 180°) | curl | MEDIUM | OPEN |
| O4 | Slant: WR cuts shallow-right (40°) not crossing (315°) | slant | MEDIUM | OPEN |
