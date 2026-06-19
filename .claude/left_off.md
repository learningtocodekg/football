# Left Off — 2026-06-19

## Branch: `freedom` (NOT main).
Madden-style input controller on the kept physics/ball engine. Contract: `.claude/freedom_design.md`.

## What we did this session — CB rebuilt + WR/QB reasoning-steps
- **WR (prompt-only, freedom):** rewrote `wr_free.txt` around 3 reasoning steps (what have I done? /
  what does the route call for now? / have I earned the break?). Gave all 12 routes a vague,
  intent-flavored `purpose` in `scripted.py` ROUTE_DESCRIPTIONS (renamed key `description`→`purpose`);
  obs labels it `PURPOSE`. RESULT: WR holds the slant stem to ~5yd and breaks at depth (was t=0.4–0.7).
- **QB throw-character (built, then PAUSED):** `solve_lead` now returns apex `peak_z`; new
  `ball.arc_clearance()` = ball height as a throw passes over a defender (loops over CBs later). QB obs
  gained hang/apex/clears-the-CB columns + a low-now-vs-high-over-the-top framing; `qb_system` trimmed
  of the now-duplicated prose. **It BACKFIRED on the short slant (see open).** Paused per "fix CB first."
- **CB REBUILT (the main work):**
  - **Removed the forced-backpedal mechanic** — `cb_agent.apply_decision` no longer overrides heading;
    backpedal is just a mode (engine still caps speed at 75%, `apply_action`). Removed the orphaned
    `wr_state` plumbing (apply_decision sig + 2 runner call sites) and the now-dead `import math`.
  - Rewrote `cb_system.txt` + `cb_move.txt` the WR way: info (obs already has WR/CB history) + context
    (what it means to play CB, the goal, move-mode/physics tips) + 3 reasoning steps. No hard rules,
    no rails, lean.
  - **Fixed a phantom-cut bug** (`runner.py` cut detection): a fake's snap-back toward upfield was
    counted as a NEW cut-to-vertical → false `CUT CONFIRMED` in the CB obs AND it suppressed the
    `vertical_committed` foot-race signal. Now a cut must deviate AWAY from the 0° stem (dev increasing).
  - **Fixed CB backpedal direction** (`cb_system.txt` context): the CB was backpedaling at heading 180°
    (toward the QB) — walking INTO its own cushion on a go. Re-added main's geometry: retreat = move
    upfield (~0°, the way the WR runs) while facing back at him; 180° closes the cushion.

## Current behavior (gpt-5-nano, seed 42; judge COVERAGE, not catch/PBU)
- **Slant:** CB contested — `sep_at_throw` 1.59yd (was **8.48** with the mechanic), correct inside commit.
- **Go (after both fixes):** CB holds its cushion, retreats upfield (hdg 0), forces the WR to stem to
  t=2.2, **`sep_at_throw` 0.83yd (glued)**, reads `go_for_pick` correctly. Was: cushion collapsed,
  beaten deep ~8yd. Verified via positions (CB y 55→60.6, cushion held +3.8 at t=0.6 vs 0.0 before).

## Broken / open
- **QB lobs short routes** (the new clearance feature). "clears the CB at z=X (in his reach)" makes the
  QB lob a short slant to clear a *trailing/beaten* CB's head — but clearance only matters for an
  UNDERNEATH (in-lane) defender; against a trailing man it's a foot race → bullet it. Fix: qualify the
  clearance by underneath-vs-trailing. PAUSED until the CB is solid across more routes.
- **CB residual one-step wobbles** (e.g. a brief hdg=270/brake biting an inside fake) — minor, self-corrects.
- Only slant + go tested. Other 10 routes + legacy tools (run_all_routes, viewers) untested.

## NEXT STEP
Run the rebuilt CB across more routes (out, curl, in, post, corner) at seed 42 to see whether the
reasoning-step prompt + the two fixes hold coverage generally; fix the next failure the LLM's own
reasoning reveals — prompt/observation only, no rails.
