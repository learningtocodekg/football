# Left Off
Date: 2026-06-11

## What We Worked On
Attempted to fix the QB's two complaints under the autonomy/anticipation doctrine: throwing too
EARLY and inaccuracy, especially on routes with no break (go) or long-delayed breaks — WITHOUT
reverting to "wait for the WR call" and without baby-feeding the QB. Conclusion: the autonomy
approach relapsed on the go route. **Decision made this session: revert to a call-gated QB.**

## What Got Done (changes currently in the tree)
These are committed but are candidates to REVERT/RESHAPE under the call-gating rework below.
- **break_visible bug fix** (`agents/observation.py`): shallow-break routes (slant 45°, post 30°,
  out/post_corner ~315°) were reading "DIRECTION CONFIRMED" during the STEM because the stem heading
  (0°) sat within the old 50° tolerance of the break heading → QB threw early. Now confirmation
  requires the heading to sit on the break (≤35°), persist 2+ of last 3 reads, AND have departed the
  stem (a confirmed `detected_cut_t`, or heading ≥25° off the stem).
- **QB options-table accuracy** (`sim/runner.py`): the QB's arc-options table now projects the WR off
  his LOCKED call heading (when called) instead of the noisy instantaneous physical heading.
- **GO route rewrite (simple, per user)**: `_ROUTE_GEOMETRY["go"]` + `ROUTE_DESCRIPTIONS["go"]` now say:
  first ~10 yds are the stem, the "break" is just continuing straight, beat them deep with speed, and
  the WR may sell a FAKE BREAK (head/shoulder fake without turning) to flip the CB's hips while he
  keeps full speed. WR call-for-ball line branched for straight routes ("call after 10 yds when your
  pace is about to break the cushion"). QB straight-route note: "after WR is 10+ yds downfield,
  anticipate the speed gap, lead deep."
- **qb_system.txt**: added an "asymmetry of throwing early vs late" paragraph.

## FAIL — the reason we are reverting
On the go route the QB throws PREMATURELY: it threw at t=0.5s (its first legal step) a flat ~12-yard
bullet into the CB cushion. **Visually verified in the replay: the ball traveled <5 yards downfield.**
A go route is won by the WR OUTRUNNING the CB and the QB throwing it OVER the CB — out of the CB's
reach — leading the WR DEEP to catch it OVER THE SHOULDER downfield. The QB did none of that; it
grabbed the unearned pre-snap cushion as if it were separation. (The single CATCH we got was luck: the
WR's jab fake put the CB in cut_recovery, so a short throw happened to hold ~2.7 yd. Not the intent.)

This premature-throw behavior is EXACTLY why we originally gated on the WR call. The
autonomy/anticipation doctrine reintroduced it. With a weak model (gpt-5-nano), an autonomous QB
grabs the first cushion-window on every vertical.

### Distance-frame confusion (contributing cause, must fix)
When the designer says "10 yards deep" / "beat them deep," distances are ALWAYS relative to the WR's
position — i.e., the WR's downfield progress from his STARTING position (current y minus snap y). They
are NOT the QB's throw distance (QB-to-target). The observation surfaces throw distance, so the model
conflated a 12-yard THROW with the WR being "deep," when the WR had only gone ~5 yds from his snap
spot. Any go-route timing logic must anchor on WR-relative depth, and observations must state which
frame a distance is in.

## NEXT STEP
**Revert the QB to call-gated, and go further: do NOT invoke the QB agent at all until the WR has
called for the ball.** Once the WR calls, the QB agent's ONLY job is: (1) place the ball, and
(2) decide whether/when to throw. Concretely: in `sim/runner.py`, skip the QB decision block entirely
while `wr_call_visible` is False (QB simply holds). Re-shape `qb_system.txt`/`qb_pass*` around
"the WR has called — where and when do you put the ball," dropping the anticipation/"a throw is a
prediction" framing. For the go specifically, encode the correct intent: WR outruns CB → throw OVER
the CB, led DEEP (WR-relative depth), caught over the shoulder. Then re-run the go route and the suite.

## Open / Future
- Decide which of this session's changes survive the call-gating rework (break_visible fix and the
  options-table locked-heading accuracy fix are likely still useful; the QB straight-route anticipation
  note and the asymmetry paragraph are tied to the autonomy doctrine and probably get removed).
- Contested curl still PBU (WR decelerates through the hook). Pre-existing.
- LLM nondeterminism: single runs aren't proof.
