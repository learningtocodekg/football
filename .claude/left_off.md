# Left Off
Date: 2026-06-14 (session 4)

Short session. Mostly verification + a UI ask. The user now considers the project **essentially done**
(Phase A4: all 10 routes run with CORRECT SHAPES; the two non-catches are open-WR losses to LLM
nondeterminism, which the user accepts as "regular LLM hallucination").

## What got done
- **Setup:** the venv is `.venv` (NOT `venv`) — `./.venv/Scripts/python.exe`. (Saved to memory.)
- **curl earlier-throw hint VERIFIED.** Re-ran curl: throw now fires at **throw_t=2.0 "as he hooks"**
  (was 2.2) — the qb_pass2 hint took effect. Outcome this run was **PBU** (CB in play_man closed the
  settle window to sep 0.5 at catch) vs last session's CATCH 1.79 — same route, different CB roll, pure
  nondeterminism. ⚠️ **This re-run OVERWROTE `replays/curl_42.json`** — the repo copy is now the PBU, not
  the CATCH. Re-run curl if you want a catch replay to view.
- **post_corner cause CORRECTED — the old handoff note was WRONG.** left_off (s3) blamed "the solver
  can't foresee the second cut." The replay disproves it: the WR's 2nd cut to the corner happened at
  t=2.0, the throw was at t=2.5 with the WR's heading **already locked on the final 315° leg** — so the
  solver's projection *direction* was correct. The real loss: at **t=3.3 mid-flight the WR's air-phase LLM
  turned to heading 225° (back toward the QB) and braked to 0** while a catchable deep ball was still
  3.5yd ahead; the runner's overshoot-freeze clamp then locked him there. He re-accelerated too late and
  finished **2.55yd from the ball → INCOMPLETE**, despite being open (sep 3.28 at throw). Secondary: the
  solver projected ~9.2yd of air travel, leaving no reach margin to absorb the stall. User: leave it,
  it's regular LLM hallucination.
- **Answered "why does the WR look so much faster than the CB?"** Two reasons: (1) attributes are NOT
  equal — WR 9.5/14/85 (speed/accel/agility) vs CB 9.0/13/80; (2) the dominant effect is the **backpedal
  speed cap** `BACKPEDAL_SPEED_FRACTION=0.75` — a backpedaling CB tops out at 9.0×0.75 ≈ **6.75 yd/s**
  while the WR sprints at 9.5. Confirmed in the go replay (WR ramps to 8.5, CB flatlines ~6.0). Not a bug
  — coverage physics working as designed.
- **NEW: backpedal indicator in all three viewers.**
  - 3D `render/renderer_ursina.py` (the "game" the user watches): body **tints cyan** while
    `mode=="backpedal"` + a floating **"BP"** billboard tag; reverts to team color when he turns to run.
  - 2D `render/renderer_pygame.py` + `viewer/debug_viewer.py`: cyan **ring + "BP" label** (+ legend line
    in the pygame sidebar).
  - First attempt only touched the 2D viewers → user saw nothing because they watch the 3D ursina one;
    added it there too. All three compile.

## Broken / Open
- **3D backpedal indicator NOT YET VISUALLY CONFIRMED.** User was going to run
  `./.venv/Scripts/python.exe -m render.renderer_ursina replays/go_42.json` and report. If it shows up,
  this session is fully closed. (User also offered the option of a ground ring instead of the body tint.)
- `replays/curl_42.json` is now a PBU (overwrote the CATCH). Cosmetic — route shape is still correct.
- post_corner INCOMPLETE stands, accepted as nondeterministic LLM hallucination (route correct, WR open).

## Suite status (seed 42, by SHAPE not label)
8 CATCH (slant, drag, go, in, zig, comeback, corner, double_move) + curl PBU + post_corner INCOMPLETE —
all 10 routes run correct shapes; both non-catches are open-WR losses to CB/WR LLM nondeterminism.

## NEXT STEP
**Confirm the 3D backpedal cyan-tint/BP-tag renders correctly** (user to run the ursina viewer). If good,
the project is at its done state. Nothing else is queued — the user believes we're done.
