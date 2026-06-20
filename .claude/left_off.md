# Left Off — 2026-06-19 (later session)

## Branch: `freedom` (NOT main).
Madden-style input controller on the kept physics/ball engine. Contract: `.claude/freedom_design.md`.

## What we did this session
- **Ran the FULL route suite** (all 12 routes, seed 42, gpt-5-nano) into fresh individual replays in
  `replays/`. Added two missing scenarios (`a4_wr_post.yaml`, `a4_wr_out.yaml`) + wired `post`/`out`
  into `run_all_routes.py` so the runnable set is now the full 12 (was 10).
- **Diagnosed the run with the user. Verdict: both WR and CB are broken across the board.**
  - WR doesn't run its route (stops short, cuts before the stem, or never runs the shape); over-deceives
    (a new fake almost every 0.1s); doesn't read the CB (stateless juke-spam).
  - CB is incoherent on every route: flip-flops heading/mode each tick, bites one-step jabs, backpedals
    way off, fails to turn-and-run on a real break.
- **REFRAMED the project as a research question** (user-driven): can a STATELESS LLM do real geo-spatial
  reasoning with NO rails and NO forcing mechanics? Ruled out: rails (that's `main`, known to work, not
  the goal) and prompt-stuffing (documented dead end). The lever is the **TYPE of control the LLM has**
  (action space / representation / cadence), not the prompt.
- **Co-designed the WR approach and stored it as a spec:** `.claude/wr_agent_design.md`. Core idea: the
  WR authors its own CONDITIONAL decision tree pre-play ("writes the prompt for its future self"); the
  plan IS its externalized state. Executed on a WALL-CLOCK spine (deliberate — time keeps it from
  ditching the route; nodes after a branch are timed relative to the decision). Conditions use
  LLM-invented vocab, LLM-evaluated at branches for now (future: make mechanical), pruned to the current
  node each step. NOT YET BUILT.
- **Compacted memory** to CB focus (added `project_freedom_thesis`, `project_cb_design_next`; removed 7
  stale WR/QB tactical memories — their history lives here + in state.md). Logged interesting lessons in
  `article.md` ("Full-route audit + research reframe" section).

## Broken / open
- **WR: not built yet** — the decision-tree design is a spec only. Current freedom WR still juke-spams.
- **CB: the next problem.** It's purely REACTIVE (can't pre-plan like the WR), so it needs its OWN
  stateless-coherence technique — the WR's design does not transfer. See `project_cb_design_next`.
- **QB: PAUSED** (known lob-on-short-route issue from the clearance feature).
- Coupling caveat: a chaotic WR makes the CB look broken (every tick reads as a fresh cut). The two are
  entangled; good WR testing needs a competent CB and vice versa.

## NEXT STEP
Design the CB agent's own stateless-coherence approach (it can't author a forward plan — it's reactive
to the WR). Think: durative committed reactions + event-driven re-query, and/or a self-updated belief
about what the WR is doing. Then build the WR decision-tree (`.claude/wr_agent_design.md`) so the two can
be tested together. No rails, no prompt-stuffing — change the control interface.
