# Left Off
Date: 2026-06-08

## What We Worked On
Round 8 run with Ollama qwen3:8b (all 10 routes), parallel subagent analysis of all 10 replay JSONs, and synthesis into problems.md.

## What Got Done

### Round 8 Ollama Run
- Ran `python run_all_routes.py --ollama --seed 42` overnight (~6 hours).
- **6 routes completed cleanly**: comeback (DROP), go (DROP), double_move (PBU), curl (PBU), zig (PBU), post_corner (CATCH).
- **4 routes errored** mid-run: slant, drag, corner, in — caused by Windows console encoding bug (Unicode chars like `°` and `→` in print statements crash stdout with charmap codec). Replay JSONs for these 4 are from Round 7.
- Round 8 score (6 new routes): **1C / 2D / 3PBU**

### Analysis
- Dispatched 10 subagents in parallel, one per route, each reading its replay JSON and assessing WR/CB/QB performance.
- Synthesized all 10 reports into `problems.md` — full replacement with Round 8 findings, old Round 7 analysis moved to appendix.

### problems.md Updated
- 3 issues marked FIXED (S3, S4, S5)
- 8 new issues added (N1–N8)
- All old issues updated with Round 8 evidence

## What's Fixed (confirmed R8)
- **S3**: CB freeze removed — CB acts from t=0.0. Confirmed every R8 route.
- **S4 / P1**: cut_recovery field in replay JSON — agents cite it and act on it. WR on double_move / zig / post_corner correctly waited for CB rec > 0 before breaking.

## What's Open / Broken

### New Critical Issues
- **N1 (=S6)**: Parse errors 10–25% per agent with qwen3:8b. No JSON mode available via Ollama. Failures land at worst moments (WR call step, pre-throw step).
- **N2**: WR executes wrong route shape on 6/10 routes (go ran a fake-cut, slant ran a seam, in ran a fly, zig body headed 180° instead of 90°, curl became a lateral drift, drag ran a sideline route). WR has freedom to choose deception but treats every route as "fake-then-break" regardless of shape.
- **N3**: WR facing hallucination during ball flight — computes QB bearing as a cardinal direction instead of actual coordinates. Comeback dropped (facing=71° instead of ~180°), zig PBU'd (body headed 180° toward CB), post_corner p_catch depressed (facing=270° instead of ~143°).
- **N4**: WR's CB-commit trigger ("wait for CB rec > 0") references a field that isn't in WR's observation space. WR infers from CB heading changes but the inference is unreliable.
- **N5**: WR has no escalation counter — loops fake indefinitely. Comeback: 16-step lateral drift. Curl: 9-step lateral drift (5.5 yards). Each step the cheap fake beats the real cut commitment.
- **N6**: QB one-step delay costs completions. Double_move: max sep=5.02 yd at t=0.8, threw at t=1.1 (parse error at t=1.0). CB closed from 3.7 to 0.58 yd. PBU.
- **N7**: CB over-commits to fake direction after N consecutive steps. "Confirmed cut" declared after 2–3 steps; no hedge for double-move. No route anticipation at any step.
- **N8**: CB geometric hallucinations — invents WR lateral drift that doesn't exist in position data (post_corner t=0.2: x frozen at 16.0, CB responds to "drift").

### Persisting from Round 7
- W1: WR calls before completing cut (in, zig)
- W2: WR heading/facing wrong post-call (comeback, zig, post_corner)
- W3: WR wrong route shape (see N2)
- S2: CB template-lock reasoning
- Q4: QB boilerplate hold ("route developing" / "WR hasn't called") for 7–20 steps every route

### Windows encoding bug (blocks future runs)
- `print()` in runner.py crashes on Unicode chars (`°`, `→`, `≥`) with Windows charmap. Need to either: wrap prints in try/except, or set `PYTHONIOENCODING=utf-8` as env var before running.

## NEXT STEP
**Fix Windows console encoding bug first** (so all 10 routes can complete in Round 9):
- Option A: `set PYTHONIOENCODING=utf-8 && python run_all_routes.py --ollama`
- Option B: add `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')` in run_all_routes.py

Then tackle the highest-impact open issues:
1. **N2 (WR wrong route shape)** — inject explicit per-phase heading constraints into WR observation (not as prescriptions, as context: "this is a go route: no cut, straight upfield, call when open and fast").
2. **N3 (WR facing hallucination)** — inject QB bearing explicitly as a computed value in the observation so the WR doesn't estimate it.
3. **N5 (WR escalation loop)** — inject step count on current heading from simulation side so WR can't miscount ("you have been on heading 270° for 9 consecutive steps").
