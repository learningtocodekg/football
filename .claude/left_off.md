# Left Off
Date: 2026-06-11

## What We Worked On
Tried the SMALLER fix before reverting to a gated QB: the handoff theory was that the QB throws
early on the go route because it confuses "10 yards deep" (WR's downfield progress from his snap
spot) with a 10-yard THROW distance. So we made the WR-relative depth frame explicit everywhere the
QB sees a distance, re-ran the go route, and — when it failed again — stopped to actually READ the
prompts instead of guessing. Decision for next session (user): **completely redo the QB prompting
with an AI.**

## What Got Done (changes in the tree)
- **Distance-frame fix** (`agents/observation.py` + `qb_system.txt`):
  - `build_qb_observation` now takes `wr_start` and prints `WR DOWNFIELD DEPTH: X yd past the snap`,
    explicitly labeled as the frame for all route distances (NOT throw distance).
  - The ARC FLIGHT TIMES line is relabeled `THROW DISTANCE (QB→WR) is X yd (distinct from WR depth)`.
  - The straight-route DIRECTION CHECK now cites the WR's ACTUAL depth and whether he's past ~10 yd.
  - `_ROUTE_GEOMETRY["go"]` clarified: "~10 yards DOWNFIELD OF THE SNAP (the WR's depth, not your
    throw distance)".
  - `qb_system.txt` got a "TWO DIFFERENT DISTANCES — DO NOT CONFUSE THEM" block (WR DEPTH vs THROW
    DISTANCE), with the concrete "a 12-yd THROW is not the WR being 12 yd deep" example.
  - `sim/runner.py` passes `wr_start=wr_start_pos` into `build_qb_observation`.
- **Three reference files written to repo root** (scratch, not wired into anything — delete anytime):
  `QB_step_example.txt`, `WR_step_example.txt`, `CB_step_example.txt`. Each is the FULL per-step
  prompt that agent receives (system prompt + freshly-built observation + step instruction),
  reconstructed from the real go-route replay (`replays/play_42.json`) at t=0.5s. Built by
  `$CLAUDE_JOB_DIR/tmp/dump_step_prompts.py` (uses `build_*_observation` directly, no LLM/sim run).

## FAIL — go route still throws early
Re-ran go (seed 42, gpt-5-nano): **INTERCEPTION, sep=0.96, throw_t=0.6s, 15-yd bullet to y=58.5.**
The depth fix PARTIALLY worked — at t=0.5 the QB explicitly HELD citing "1.7 yards depth" (the new
depth signal doing its job) — but one step later it threw anyway.

## ROOT CAUSE (found by reading the actual prompt, not the distance frame)
At the throw step the WR was at y=53.0 and the **CB was at y=55.1 — i.e. the WR had NOT overtaken his
man** (he was 2.1 yd behind the CB). Two things in the QB prompt CAUSED the early throw, neither of
which is the distance frame:
1. **The LEAD HINT lies on a go route.** The observation hands the QB a pre-computed `WR will be
   ≈(16.0, 59.8) — throw to the projected coord`. That projection assumes the WR keeps his current
   speed and the CB keeps crawling, so it ALWAYS shows the WR pulling deep/open on a vertical — even
   while he's still behind the CB. We spoon-fed it a deep target it hadn't earned.
2. **We never surface the one fact that decides a go route: has the WR passed the CB?** The obs shows
   both y-values but never says "WR is 2.1 yd BEHIND the CB — he hasn't beaten his man yet."
Plus the whole observation is pre-chewing the decision (LEAD HINT, options table `sep@arr` +
`CB clear/contested`, editorial DIRECTION CHECK), AND the same observation — LEAD HINT included — is
sent in BOTH QB pass 1 and pass 2 (`qb_agent.py:241,271`), so "pass 1 = read it yourself" isn't real.
The user's reaction: the QB prompting has been vibecoded into a mess and needs a clean redo.

## NEXT STEP
**Completely redo the QB prompting (next session, with an AI).** Use the three `*_step_example.txt`
files as the ground-truth picture of what the QB currently sees. Design goals to carry in:
- Feed the QB FACTS, not pre-computed answers — especially kill/relegate the LEAD HINT and the
  "throw to the projected coord" spoon-feed; let the QB do the projection.
- Surface the decisive go-route fact: WR-vs-CB depth (has he overtaken his man, by how much).
- If keeping two passes, genuinely separate them: pass 1 = QB forms its own read from raw facts;
  pass 2 = here is the computed arc math for the spot you chose. Don't leak the projection into pass 1.
- Open question still on the table: whether to gate the QB on the WR's call (memory
  project_qb_call_gated) — the prompt redo may make gating unnecessary, or confirm it's needed.

## Open / Future
- Decide which distance-frame changes survive the QB-prompt redo (the WR DOWNFIELD DEPTH line and the
  throw-distance relabel are honest facts and likely keep; the editorial straight-route DIRECTION
  CHECK paragraph is the kind of pre-chewing the redo aims to remove).
- Contested curl still PBU (WR decelerates through the hook). Pre-existing.
- LLM nondeterminism: single runs aren't proof.
