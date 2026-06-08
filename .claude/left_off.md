# Left Off
Date: 2026-06-07

## What We Worked On
Full round 7 post-mortem. problems.md had 19 issues from a 10-route run (3C/1D/3PBU/1INC/1INT/1SACK). Analyzed all of them, planned 4 parallel sub-agents to fix them, and dispatched.

## What Got Done

### WR Prompts (S1, W1, W2, W3, W4)
- **S1 NOTE GROUNDING**: Added explicit rule to `wr_live_free.txt` — wr_note must be verified against the move log; if log is empty, no actions have occurred, do not fabricate history. Breaks the t=0.0 hallucination feedback loop.
- **W1 call criteria**: Strengthened in both `wr_system.txt` and `wr_live_free.txt` — call only after completing the final cut (not mid-cut or on stem); longitudinal gap ≠ open on breaking route.
- **W2 post-call lock**: Made absolute in `wr_live_committed.txt` — no heading changes between call and catch, no exceptions before ball is in air.
- **W3 route fidelity**: Added "THE ROUTE IS YOUR DECEPTION TOOL" section to `wr_system.txt` — route phases are the geometric setup, not suggestions.
- **W4 jab depth**: Added explicit minimum (60–90° off stem) and compass anchors (~270° left / ~90° right) to `wr_system.txt` and `wr_live_free.txt`.

### CB Prompts (S2, C1, C2)
- **DANGER MODEL**: Added to `cb_system.txt` — 3+ yd separation on break heading + ball in air = catch. CB now has a failure anchor.
- **LATERAL MIRRORING**: Backpedal only when WR is heading ~0° (approaching). If WR x drifts 1–2 yd away, close laterally.
- **FLIP TRIGGER**: After confirmed cut (heading held 2+ steps), flip to normal mode immediately, close at full speed.
- **STEP 0** added to `cb_pass1.txt` decision framework: check lateral gap before anything else.
- **CONFIRMED CUT CHECK**: If WR held non-upfield heading 2+ steps, close hard.

### QB Agent (Q2, Q3)
- **_build_options** now takes `wr_cut_recovery`, `wr_max_speed`, `cb_x`, `cb_y`.
- **Recovery-aware projection**: When WR is in cut_recovery, shows two WR-at-arrival estimates: current speed (conservative) and projected rebuilt speed (optimistic). Previously assumed constant speed, which caused post-cut lead errors.
- **CB context flag**: Each option now tagged `CB in throw lane` / `CB may contest` / `CB behind WR`.
- **runner.py** passes the 4 new args to `qb_agent.decide()`.
- **qb_pass2.txt** updated with guidance on reading recovery range and CB flags.

### Code Fixes (S3, S4, S5, S6)
- **S3**: Removed `t >= 0.3` guard in `runner.py` — CB now acts from step 1 (was a hardcoded code gate, not a prompt issue).
- **S4**: `cut_recovery` added to `_player_snap()` — now appears in replay JSON. `[CUT_REC]` transition logs added. `# TODO S4` tracking comment in runner.py.
- **S5**: `actions["QB"] = {"action": "hold", "reasoning": "ball in air"}` set immediately after throw — replay no longer shows stale throw reasoning for every in-air step.
- **S6**: Empty-response retry added to `call_llm` — retries once if content is whitespace/empty.

## What's Open / Known Issues
- **None of these fixes have been run yet** — no Round 8 data
- C3 (CB intent not position-aware), C4 (CB speed locked 6.75), P3 (detected_cut_t fires on jabs) not addressed
- Q1 (QB throws without WR call on go route) — intentionally left: user said QB freelancing is fine
- S4 TODO: next run will show if agents are actually citing cut_recovery in reasoning
- CB observation still doesn't pre-compute the lateral gap as an explicit field — CB must subtract x-coords itself (noted by CB agent as a possible improvement)

## NEXT STEP
**Run Round 8** (all 10 routes) and compare against Round 7 scorecard (3C/1D/3PBU/1INC/1INT/1SACK). Look specifically for:
1. CB starting to move at t=0.0 (no more 3-step freeze)
2. `[CUT_REC]` log lines appearing in output — confirms physics is logging
3. WR not outputting "jabbed left last step" at t=0.0
4. CB heading changing laterally during stem phase (not pure 0°)
5. QB options table showing two WR projections when cut_recovery > 0

Run: `.venv\Scripts\python run_all_routes.py`
