# Left Off — 2026-06-18

## Branch: `freedom` (NOT main). Started this session.
Goal: cut the heavy scaffolding, give the LLMs real freedom — the agent becomes a **Madden-style
input controller** on top of the kept physics/ball engine. Contract: `.claude/freedom_design.md`.

## What we did
- **New foundation (`81da43f`)** — rebuilt the agent/control layer:
  - `engine/endroute.py`: deterministic WR `end_route` (`run` / `settle`) + `solve_lead` (the QB
    lead solver — bisection meeting-point on the WR's locked future path).
  - WR runs free, then `call_for_ball` locks an `end_route`; engine drives him deterministically
    until the throw, then he comes alive in the air. **No rail** (route shape is prompt context).
  - QB is call-gated (0.2s delay), only picks **bullet vs lob** + timing; engine places the ball.
    Added `lob` arc (=loft 45°) to `engine/ball.py`.
  - CB intent collapsed to `play_man` / `go_for_pick` (`swat` removed; PBU is an effect of man).
  - Split `observation.py` → `observation_{wr,qb,cb}.py` + `observation_common.py`; rewrote
    `runner.py`, `schema.py`, all prompts; deleted the rail, dead prompts, rail test.
- **Catch (subagent):** kept the 3-zone resolver (sound), removed the dead `swat` branch +
  unreachable `DROP`.
- **WR (`9bb7e8f`):** break-depth anchor in obs + "one decisive break, call on the break" prompt.
  Slant: 21yd throw → ~11yd, sep@catch 9.6 → 2.31.
- **CB (`8e936b7`,`6e1e8df`,`6f9d402`):**
  - Skip the CB on step 0 (give it 1 tick of WR movement before deciding — fixed snap-charge).
  - Structural **vertical-commit signal**: runner stamps "straight+fast, no cut" and the obs injects
    "no break left, foot race" (prompt-only commitment had failed — stateless re-litigation).
  - **Straight-backpedal MECHANIC** (`apply_decision` takes `wr_state`): backpedal forces facing=WR,
    heading=directly away from WR. No sideways/charging backpedal; to move at an angle the CB must run.
  - Rewrote `cb_system` tight: leverage/optionality over proximity, concrete speed tradeoff
    (backpedal 6.75 vs run 9.0 vs WR 9.5).
- **Go WR-call cue:** obs tells the WR when it's even-with/past the CB → call. Go was *sacking*
  (WR never called); now calls reliably.

## Current behavior (gpt-5-nano, seed 42; slant + go only — NOT the full suite)
- **Slant:** crisp route, CB backpedals straight then drives the break. Good when the WR breaks at
  depth + QB bullets (sep ~2.3). Bad runs balloon (see open issues).
- **Go:** WR calls; CB backpedals away (no charge), commits to the run on the vertical; beaten deep
  by ~8yd (was 24yd). Realistic-ish, still a touch generous.

## Broken / open
- **WR slant break-timing variance:** breaks t=0.4–0.7 (sometimes ~2yd not the ~5yd anchor).
- **QB picks `lob` on a short slant** sometimes (should bullet). With a `run` end_route the WR then
  accelerates away under the long lob → sep balloons (still a CATCH, unrealistically open).
- **CB residual flips** on the vertical (~20%, reduced not gone — stateless variance).
- Only slant + go tested. QB not separately refined (works). Legacy tools (`run_all_routes.py`,
  `gen_demo.py`, viewers) likely broken by the refactor — **untested**.
- Subagent infra note: worktree isolation branches off the DEFAULT branch (main), not the current
  branch — commit WIP before any worktree fan-out or subagents land on stale code.

## NEXT STEP
Nudge **QB to prefer `bullet` on short/quick routes** and **WR to hold the slant stem to its ~5yd
break depth**, then re-run slant + go and confirm separation stays realistic (slant ~2–3yd, no balloon).
