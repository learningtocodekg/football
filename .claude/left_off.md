# Left Off
Date: 2026-06-08

## What We Worked On
WR observation quality session. The WR was reading a vague, poorly-ordered observation that buried the route description mid-prompt and used loose timing/yardage numbers. Goal: make the WR observation concrete, well-structured, and give the WR what it needs to know WHEN to call for the ball.

Also created `show_wr_obs.py` — a diagnostic script that renders the exact text the WR reads at any step with synthetic data, so we can debug the observation without running the full sim.

## What Got Done

### Observation restructure (`agents/observation.py`)
- **Route description moved to top** — first thing WR reads, always. Route description was previously buried after play state / CB data; WR was reading its own position before knowing what it was supposed to do.
- **Phase X of Y removed** — replaced with `YOUR HEADING NOW: Xdeg — [final break / ~Xs remaining, then cut to Ydeg]`. Cleaner and unambiguous.
- **SNAP POSITION** added — WR always sees `(x, y)` from t=0 as a reference for gauging how far into the route it is.
- **History window: 10 steps → 20 steps** (1s → 2s of context).
- **`rec` legend added** to move log header: `free=full burst available; Nrec=hip turned, N more steps until full burst returns`.
- **`_phase_instruction()` helper** — generates specific mechanics text dynamically from `route_phases`: "Head 0° for ~14 yards (~2.0s). Around t=2.0s — when you feel a 45° cut would give you enough separation — cut to 45° and continue through the catch."
- **`_est_yards()` helper** — physics-accurate yardage estimate from route phase duration (accounts for acceleration from rest for phase 1, max speed for subsequent phases).
- **`wr_start` parameter** — passed from `runner.py` to `build_wr_observation`.
- **"max separation" → "enough separation (body gap >= 1.5 yd)"** — corrects the signal: WR doesn't need 5 yards, just 1.5.
- Removed Δ/°/² Unicode characters from move log (Windows terminal compat).

### Route timings fixed (`agents/scripted.py`)
Old timings were wrong vs real football routes. New:
- slant: 2.0s / ~14 yd / 45°
- post: 4.0s / ~31 yd / 30°
- curl: 2.5s / ~19 yd / 180°
- in: 2.0s / ~14 yd / 90°
- drag: 1.0s / ~6 yd / 90°
- zig: 1.0s stem + 0.5s jab (270°) + break (90°)
- ROUTE_DESCRIPTIONS cleaned up — removed timing numbers from text (now generated dynamically), kept "why it works" context.

### WR prompt rewrite (`agents/prompts/wr_live_free.txt`)
- **Strategic framework block at top**: 6-point checklist (field position, CB position, current phase, deception frequency, 1.5yd sufficiency, call timing).
- **Note format standardized**: `[deception: done/needed/not needed yet] | [current action] | [next plan]`.
- **Call timing updated**: signal when you expect enough separation in next 0.1-0.3s — either just before or just after the final cut.
- Removed duplicate "DECEPTION SERVES YOUR FINAL CUT" block (was repeated twice).
- Deception mechanics consolidated.

### runner.py
- Captures `wr_start_pos` before the game loop and passes it to both `build_wr_observation` calls (LIVE and BALL_IN_AIR phases).

### Diagnostic tool
- `show_wr_obs.py` — renders two snapshots (stem phase + break phase) of the slant route with synthetic data. Run with `.venv\Scripts\python show_wr_obs.py` to see the exact WR observation without running the full sim.

## What's Open / Broken

### Carried forward
- **WR still hasn't been run** with the new observation structure — no empirical results yet. This entire session was scaffolding improvements.
- **Core problem unresolved**: WR tends to run 0° the entire play, never executing route phases. With the route description now at the top and the phase instruction immediately after, it should help — but unverified.
- **PHASE CHECK not implemented**: The NEXT FIX from Round 9 (inject real-time "you are at (x,y), route expects you at (x', y'), you are ON/OFF COURSE") was deprioritized in favor of the observation restructure. Still open.
- All other issues from Round 10 prep (W1/W2 premature calls on curl/post_corner, N7 CB over-commits, N8 CB hallucinations) still open.

## NEXT STEP
**Run all routes** (`run_all_routes.py`) to get a baseline with the new observation structure. See if the WR actually executes route phases now. If WR still ignores phases, the next fix is the PHASE CHECK: inject per-step "you are at y=X, you should have traveled ~Y yards in this phase, you are [ON/OFF COURSE]" into `build_wr_observation`.
