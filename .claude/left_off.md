# Left Off — 2026-06-19 (CB redesign session)

## Branch: `freedom` (NOT main).
Madden-style input controller on the kept physics/ball engine. Contract: `.claude/freedom_design.md`.
Research thesis: stateless-LLM spatial reasoning with NO rails, NO prompt-stuffing — change the TYPE of
control. WR design (not built) in `.claude/wr_agent_design.md`.

## What we did this session — CB AGENT REDESIGNED + isolated test harness
- **Reframed the CB as a per-step pursuit-control problem** (not planning — it's reactive, no plan to
  carry). The flip-flop was NOISE: re-deriving "cut?" each tick + a raw-heading output turned that noise
  into physical thrashing (+ cut-recovery penalties).
- **New CB control interface (mode + bounded tilt + rich facts):**
  - CB output is now `{mode, tilt, reasoning}` (was raw heading/facing/mode). `mode` ∈
    `shadow`/`drive`/`bail`; `tilt` ∈ ±25° (kept UNDER the 35° cut-recovery threshold so tilt-wobble is
    physically free and can't become a new flip-flop vector).
  - New `engine/coverage.py` `resolve_coverage(mode, tilt, cb, wr, drive_target)` renders each intent
    into the exact heading/facing/movement-mode from live geometry (engine owns the trig). shadow =
    mirror WR heading + backpedal + face WR; drive = close on WR-projected (or the ball in air); bail =
    run with him on his heading.
  - `observation_cb.py` adds a LEVERAGE FACTS block (cushion adequacy vs his speed, inside/outside
    hedge, commit cost in recovery steps) + keeps the runner's `detected_cut_t`/`vertical_committed`
    signal so the CB doesn't re-derive the cut.
  - `cb_system.txt` + `cb_move.txt` reframed as CONTEXT (modes, danger model, shadow intent), not a rail.
  - Files: `engine/coverage.py` (new), `agents/schema.py` (parse_cb_move), `agents/cb_agent.py`
    (apply_decision now takes `wr` + optional `drive_target`), `sim/runner.py` (2 call sites + LIVE print).
- **New CB-only test harness `run_cb_test.py`:** deterministic scripted WR with baked-in jukes +
  HARDCODED meeting-point throw (`_meeting_target` aims at the WR's deterministic position at ball
  arrival — lands ON him, miss=0.00yd). CB is the ONLY live LLM. Replays are the SAME standard JSON
  (header/steps/footer, one snapshot/0.1s) — viewer-compatible (verified). Tests slant/go/comeback ×3
  juke variants.

## Results (seed 42; judge COVERAGE, not catch/PBU) — replays/cb_*_42.json
- **Flip-flop ELIMINATED:** 2–10 mode switches per whole play (real phase changes), vs the old per-tick churn.
- **Slant — ELITE:** PBU 0.73 / INT 1.24 / PBU 0.80 (sep@catch). Holds shadow ~13 steps w/ ±5° tilts,
  reads the 45° break, drives, contests tight. Bites none of the jukes.
- **Comeback — mostly good:** INT 1.01, CATCH 2.63, and one bad miss CATCH **6.15** (outside-jab —
  inspect; likely committed the wrong way on the settle).
- **Go — beaten deep (hardest case):** sep TIGHT at throw (0.3–1.3) but GROWS over the 2.8s lob flight
  (2.35–3.69). Partly legit (WR 9.5 > CB 9.0 = losing foot race on a pure vertical) + the CB commits to
  bail/drive ~t=1.5, a touch late after backpedaling (cap 6.75) while the WR built speed.

## Broken / open
- **Go deep coverage:** CB bails slightly late + athletic speed mismatch. Open question for the user
  (acceptable as a speed mismatch, or bail earlier on the vertical-commit signal?).
- **Comeback outside-jab 6.15 miss** — one outlier to look at on tape.
- **WR: still not built** — current freedom WR juke-spams. QB: PAUSED.

## NEXT STEP
Build the WR agent per `.claude/wr_agent_design.md` — the self-authored conditional decision tree
(wall-clock-anchored, LLM-invented + LLM-evaluated conditions, pruned per node). With the CB now a
competent test partner, the WR and CB can finally be tested together.
