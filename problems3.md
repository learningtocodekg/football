# Problems Found — Round 3 (seed=42, OpenAI gpt-5-nano)

Results: slant→DROP, comeback→CATCH, go→INTERCEPTION, double_move→PBU,
curl→DROP, zig→DROP, drag→DROP, corner→DROP, post_corner→DROP, in→CATCH

Score: 2 CATCH (comeback, in), 1 PBU (double_move), 1 INTERCEPTION (go), 6 DROP

Comparison vs Round 2 (Ollama):
| Route | Round 2 | Round 3 | Change |
|-------|---------|---------|--------|
| slant | DROP | DROP | same |
| comeback | INCOMPLETE | **CATCH** | FIXED ✓ (N3 fix) |
| go | DROP | **INTERCEPTION** | WORSE ✗ |
| double_move | INTERCEPTION | **PBU** | BETTER ✓ |
| curl | INCOMPLETE | DROP | same category |
| zig | DROP | DROP | same |
| drag | CATCH | **DROP** | WORSE ✗ |
| corner | CATCH | **DROP** | WORSE ✗ |
| post_corner | DROP | DROP | same |
| in | DROP | **CATCH** | FIXED ✓ |

---

## O1 — Ball-in-air heading abandonment (HIGH)

**Affected routes:** curl, zig, drag (all DROP)

All three routes dropped because the WR changed its body heading during ball flight, running away
from the ball's landing zone.

- **Curl**: WR called at t=1.5 heading 270° (sideways), then kept heading 270°–273° and
  accelerated to 9.44 yd/s through ball flight. Ball landed at (12.3, 56.9); WR ended at
  (11.37, 56.95) — 0.94 yd positional miss, but 4.29 yd effective separation due to WR running
  at full speed away from the catch point.
- **Zig**: WR cut to 90° at t=0.8 (throw time), then reversed to 180° at t=0.9 while ball was
  in flight. WR needed to move laterally (decreasing x) toward target (15.7, 51.3) but instead
  ran vertically upfield, ending with wrong trajectory.
- **Drag**: WR heading was 90° at throw time (t=0.6). At t=0.7 (ball still in air), WR switched
  to heading 0° (upfield), abandoning the lateral cut entirely. Ball target (16.8, 52.5); WR
  drifted to (16.98, 51.73) — 3.07 yd separation at resolution.

In all three cases, the WR's reasoning shows it attempting to "navigate toward the landing zone"
during ball flight — but it changed its heading (body direction) instead of just its facing. The
WR's movement is governed by heading, not facing, so re-orienting toward the landing zone by
changing heading causes the WR to run past or away from the target.

This is a generalization of N5 (curl only in Round 2). It affects all short breaking routes
where the WR's post-cut heading is not 0°.

**Root cause:** WR conflates heading (movement direction) with facing (body orientation toward
ball). During ball-in-air, WR should freeze heading at the cut angle and only use facing to track
the ball.

---

## O2 — Corner route: WR abandons the real break (HIGH)

**Affected routes:** corner → DROP (throw at t=4.8, 55 steps, throw distance 46.1 yd)

The WR executed the 290° break at t=2.2–2.6 (correct) but only reached 1.73 yd separation before
reverting to stem (heading 0°) at t=2.7. The WR's own reasoning at t=2.7 logged: "last step
jabbed left (290°), returning to 0°" — it treated the actual corner cut as another jab.

From t=2.7–4.4, both WR and CB ran nearly identical straight-upfield paths at max speed. The WR
opened separation only through its speed advantage (9.5 vs CB's 9.0 yd/s), gaining ~0.04 yd/step
for 17 steps. Separation finally crossed 2.0 yd at t=4.5 and WR called at t=4.7.

**Separation timeline during the failed cut (t=2.2–2.7):**
| t | sep | WR heading |
|---|-----|-----------|
| 2.2 | 0.93 yd | 290° (cut starts) |
| 2.5 | 1.54 yd | 290° (growing) |
| 2.6 | 1.73 yd | 290° (peak during cut) |
| 2.7 | 1.38 yd | 0° (ABANDONED) |

The break was working — separation was growing. WR quit because 1.73 yd was below its ~2 yd
openness threshold, not understanding that: (a) the trajectory advantage continues to grow after
the cut, and (b) returning to stem after a real break gives the CB an easy straight-line chase.

**Root cause:** WR has no concept of "this is the terminal move" vs "this is a deception jab."
Both involve heading changes; the WR treated the 290° break as another jab that failed to open
>2 yd immediately, then abandoned it.

---

## O3 — Go route: QB threw to a spot behind the CB (HIGH)

**Affected routes:** go → INTERCEPTION

At throw time (t=1.0):
- CB position: y = 58.53 (backpedaling upfield, ahead of WR)
- Throw target: y = 58.1 — **0.43 yd short of the CB's current position**
- The ball was aimed behind the CB, not past it

Additional problem: WR called at t=0.8 with 2.40 yd separation. QB waited until t=1.0 (one full
step too long). By throw time, separation had dropped to 1.85 yd as the CB continued closing.
QB should have thrown at t=0.9.

The CB intent was `go_for_pick` throughout. With CB already past the throw target and only 1.85 yd
of WR-CB separation, the interception was automatic.

**Root cause:** On a GO route, the CB plays ahead of the WR by design (cushion technique). QB
must throw past the CB — the target should be beyond where the CB currently is, not just to the
WR's projected spot. The LEAD HINT helps QB compute where the WR will be, but it doesn't
account for where the CB is and whether the target is already behind the CB.

---

## O4 — Slant: WR cut to wrong angle (MEDIUM)

**Affected routes:** slant → DROP

WR's "slant cut" executes at heading 40° (slightly right-of-upfield, northeast). A slant from
the right hash should cross toward the middle of the field diagonally, at approximately 270–315°
(leftward / northwest). The WR cut in almost exactly the wrong horizontal direction.

The cut happened on schedule (~t=1.8s) and the throw lead was geometrically correct for 40°, but
the route shape was never a slant. The WR ran a shallow out-and-up with slight right lean instead
of a crossing route.

Note: at t=2.4 the WR was only 0.39 yd from the ball's landing spot, but the final reported
separation was 3.65 yd — the ball continued past the landing point between t=2.4 and t=2.5,
suggesting a possible resolution timing window issue in the engine.

**Root cause:** The WR agent interpreted the slant prompt as "run near-upfield with a slight
angle" rather than "cross the formation diagonally at ~45° toward the interior." Route definition
in the prompt needs to specify cut direction more precisely.

---

## O5 — Double move: WR runs east during fake phase (MEDIUM)

**Affected routes:** double_move → PBU (not CATCH)

During the 90° fake phase (t=1.5–2.1), the WR was physically running east at heading 90° at
full speed — it moved from x=16.79 to x=22.39 (5.6 yards east). The CB tracked this east
movement, moving from x=16.03 to x=19.34 (4.2 yards east).

When WR broke real to 0° (north) at t=2.3, the CB was already in a parallel east position, only
2.1 yd behind and inside. The fake committed the CB laterally but WR had also traveled east
alongside it. Effective lateral gap at real break: ~2.1 yd — not enough for a clean window.

WR also added an extra jab at t=2.2 (heading 60°) instead of snapping cleanly to 0°, costing
0.1s and giving CB extra time to begin recovery.

Final: sep=1.53 yd at resolution, CB chose swat → PBU.

**Root cause:** An ideal double move keeps WR near its stem track so the CB's lateral commitment
is a pure over-reaction. Here, WR ran east during the fake — both players moved east together,
so the "misdirection" advantage was minimal. When WR broke north, the CB was already positioned
east and quickly pivoted north in parallel pursuit.

---

## O6 — Post_corner: WR delayed call 0.7s after real break (MEDIUM)

**Affected routes:** post_corner → DROP

Real break to 315° at t=2.4. WR_CALL_FOR_BALL at t=3.1 — a 0.7 second delay. During those 7
steps, CB recovered from the fake (had committed inside at 64°–90°) and ran a tight parallel
shadow line at 311°–313°. By call time, CB was back in close pursuit at 9.0 yd/s.

QB threw at t=3.2 to (9.5, 72.5). The throw was slightly over-led (~0.68 yd too far
outside/deep). WR maintained correct 315° heading during ball flight. At resolution: sep=2.58 yd,
CB intent = swat → DROP.

**Root cause:** WR's ~2 yd separation threshold prevented calling immediately after the break.
Separation at t=2.4 (break) was only 1.24 yd, growing slowly post-break. The 0.7s wait gave
CB full time to recover from the fake — essentially erasing the deception advantage of the
45° fake that had committed the CB inside.

---

## O7 — N2 (cookie-cutter jabs) PERSISTS across all 10 routes (HIGH)

**Affected routes:** all 10

Self-action history (N7 fix) made the pattern visible to the WR but did not break it. The
330°/30° alternation persists on every route:

| Route | Dominant jab angles | CB lateral effect |
|-------|--------------------|--------------------|
| slant | 330° (×5), 30° (×1) | 0.0 yd |
| comeback | 330° (×11), 300° (×2) — **all leftward, no rightward** | 0.0 yd |
| go | 330° (×2), 20° (×1) | 0.0 yd |
| double_move | 330°/30° alternating ×8 in stem | 0.0 yd |
| curl | 330°/30°/0° cycle | 0.0 yd |
| zig | 330° (×2), 30° (×1), 270° | killed WR speed |
| drag | 330°/30°/60° alternating | 0.0 yd |
| corner | 330° (×9), 300° (×2) | CB ignored entirely |
| post_corner | 330° (×9), 30° (×4) | 0.0 yd |
| in | 330°/30° strict alternation | 0.0 yd |

In comeback, the WR used ONLY leftward jabs (330°/300°) for 28+ steps — no rightward fake at
any point. In corner, the CB was running intercept geometry and ignored the fakes entirely; WR
continued 330° jabs for 40+ steps with zero CB reaction.

The CB is never displaced by WR deception. All separation comes from route geometry (CB
backpedaling out of position), not from effective fakes.

**Root cause:** The LLM has a deeply ingrained template of "small alternating angle jabs" as
the safe deception move. Textual guidance to "vary" and self-history both fail to override this
template because the LLM always reaches for the same specific angles (330°, 30°) as the
default "safe" fake size.

---

## O8 — QB lead direction error on lateral routes (MEDIUM)

**Affected routes:** drag (contributed to DROP)

On drag, WR was running heading 90° (pure lateral, eastward) at 5.59 yd/s at throw time. QB
placed the throw at (16.8, 52.5), which is 1.16 yd upfield (+y) of WR's position but only
~0.18 yd behind WR's x. For a WR running east (increasing x), the lead should have been further
east (+x direction), not upfield (+y).

This means even if WR had maintained heading 90° during ball flight (not the O1 reversal), WR
would have ended up around x=17.74 while the ball landed at x=16.8 — a 0.94 yd horizontal miss.
The O1 heading reversal made things worse, but the QB's lead direction was also wrong.

**Root cause:** QB LEAD HINT likely decomposed WR velocity incorrectly for non-0° headings,
computing upfield lead instead of the lateral component.

---

## Summary Table

| # | Problem | Routes | Severity | Root Cause |
|---|---------|--------|----------|------------|
| O1 | WR changes heading during ball-in-air | curl, zig, drag | HIGH | WR conflates heading (movement) with facing (orientation) |
| O2 | WR abandons corner break, returns to stem | corner | HIGH | No concept of terminal cut vs jab |
| O3 | Go: QB target already behind CB at throw | go | HIGH | QB doesn't check if target clears CB's current y |
| O4 | Slant: WR cut to 40° instead of ~315° interior | slant | MEDIUM | WR route knowledge gap on slant direction |
| O5 | Double move: WR runs east during fake phase | double_move | MEDIUM | Fake = actual travel, not directional signal |
| O6 | Post_corner: 0.7s call delay after real break | post_corner | MEDIUM | 2yd threshold prevents early post-break call |
| O7 | N2 cookie-cutter 330°/30° jabs on all 10 routes | all 10 | HIGH | LLM template overrides vary-fakes guidance |
| O8 | QB lead direction wrong for lateral-heading WR | drag | MEDIUM | Lead computed upfield not laterally |

---

## Improvement Ideas for Unresolved Problems

### N2 / O7 — WR Cookie-Cutter Jabs

**Current state:** Self-action history (N7 fix) made the pattern visible but didn't break it.
330°/30° alternation persists. CB is never displaced. The LLM overrides all textual guidance.

**Idea 1 — Explicit angle blacklist per-step (strongest):**
In the observation, replace the generic self-history table with a live prohibition:
> "JABS USED THIS PLAY: 330° (×4), 30° (×3). DO NOT use 330° or 30° for the rest of this play.
> The CB has seen these angles and is no longer reacting. Pick an angle NOT in this list."
This is a constraint, not a suggestion. LLMs respect explicit prohibitions more than "try to vary."

**Idea 2 — CB reaction feedback per jab:**
After each jab, show whether the CB reacted:
> "LAST JAB: 330° → CB lateral shift: 0.0 yd (ignored). Your deception is not working. Try a
> different approach: (a) larger angle (60°–120°), (b) speed change (coast → burst), (c) stem
> pause."
Outcome-tied feedback ("not working") is more compelling than lists of options.

**Idea 3 — Sector diversity requirement:**
> "Deception requirement: your jabs must cover at least 2 angle sectors. Sectors: LEFT (271–349°),
> RIGHT (11–89°), BACK (91–269°). You have used: LEFT only. You must include a RIGHT or BACK jab."
Formalizes variety as a rule rather than a preference.

**Idea 4 — Show CB's position relative to WR's jab direction:**
> "You jabbed LEFT (330°) 4 times. CB did NOT shift left. CB is at your RIGHT shoulder (+x side).
> A LEFT jab will not draw CB away from your cut direction. Try a jab toward CB's current side."
This connects the jab direction to the CB's actual alignment — spatial reasoning the LLM can use.

---

### N5 / O1 — Ball-in-Air Heading Abandonment

**Current state:** Now confirmed across curl, zig, drag (all 3 routes with non-0° cut headings).
WR treats ball-in-air as a navigation problem and re-orients body heading toward landing zone,
running away from where the QB threw. Affects any route where cut heading ≠ 0°.

**Idea 1 — Explicit heading lock instruction (strongest):**
In the ball-in-air observation header:
> "BALL IS IN THE AIR. DO NOT change your heading. The QB threw to your projected position based
> on your current heading [X°] and speed. If you change heading now, you will run away from the
> ball. Maintain heading [X°]. You may adjust FACING to track the ball, but heading must stay [X°]."
This directly names the mistake and the allowed vs prohibited action.

**Idea 2 — Show that current heading leads to landing zone:**
> "Ball landing zone: (X, Y) in T seconds. At your current heading [X°] and speed [S yd/s],
> you will arrive at approximately (X', Y'). This is [dist] from the landing zone. Hold your
> heading — do NOT re-navigate."
Makes the math explicit: your current heading is already correct.

**Idea 3 — Distinguish heading vs facing in observation explicitly:**
Add a note to the observation schema definition visible in every ball-in-air prompt:
> "HEADING = your movement direction (changes where you go). FACING = where your body faces
> (used for catching, not movement). During ball-in-air, only change FACING. Never change HEADING."

---

### N6 — QB Throw Speed Selection

**Current state:** QB sometimes throws lob/slow speeds for short horizontal routes where CB can
close during flight. Also QB holds 0.2s too long after WR calls on some routes.

**Idea 1 — Route-type throw speed rule in observation:**
> "ROUTE TYPE: horizontal crossing (WR heading ~90° or ~270°). CB closure rate at current speed:
> ~X yd/s toward landing zone. Use FASTEST throw speed. Every 0.1s of extra flight gives CB an
> additional [X×0.1] yd of closure. ETA at bullet speed: [T]s. ETA at lob: [T+delta]s."
Makes the CB closure math concrete so QB picks fast automatically.

**Idea 2 — Post-call urgency prompt:**
> "WR called at t=[X]. Sack clock: [Y]s remaining. Each additional step costs ~0.7 yd of
> separation (CB closing at 9 yd/s). Recommended: throw NOW unless coverage forces a hold."
Frames every delay step as a cost rather than a neutral pause.

**Idea 3 — Throw speed default table in QB prompt:**
> "DEFAULT THROW SPEEDS: Short (<15 yd) → bullet. Horizontal crossing → bullet. Comeback/curl
> (<20 yd) → regular. Deep (>25 yd) → lob acceptable. When in doubt for short routes, use bullet."
A rule table the LLM can apply without computing CB closure rates from scratch.

**Idea 4 — Explicitly flag the go-route case: throw past the CB:**
> "GO ROUTE ONLY: CB is running ahead of WR (cushion technique). Your throw target must be
> FURTHER UPFIELD than the CB's current position, not just at the WR's projected position.
> If CB is at y=[Y_cb], throw to y>[Y_cb]."
This addresses O3 (the go INTERCEPTION root cause) directly.
