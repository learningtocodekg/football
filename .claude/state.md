# Build State
Current phase: A4 in progress (all three agents live; physics overhaul added dynamic acceleration + hip-turn recovery; CB freed from prescriptions; WR gets CB reaction MOVE LOG with rec columns; 10 routes run 3x — Ollama + OpenAI; new physics untested end-to-end)

## Built
- engine/physics.py — PlayerState (+ cut_recovery field), apply_action (dynamic burst, cut recovery, speed shed), cut_recovery_steps(), BACKPEDAL_SPEED_FRACTION=0.75, CUT_RECOVERY_BASE_STEPS=4, CUT_ANGLE_THRESHOLD=35°, CUT_SPEED_THRESHOLD=3.0
- engine/ball.py, field.py, resolution.py, state_machine.py
- engine/resolution.py — facing+arm-reach geometry for PBU/INT; CB_ARM_REACH=1.0, CB_HALF_REACH=0.5, CB_FACING_CONE=60°; play_man proximity bonus; WR facing multiplier (x1.15/x1.0/x0.80); optional CB (None in A3)
- replay/recorder.py
- agents/qb_agent.py (two-pass: hold/thinking → concrete options)
- agents/cb_agent.py (three-pass: pre_snap / decide_movement / decide_intent)
- agents/wr_agent.py (three-pass: pre_snap / decide / ball_in_air; call-for-ball state machine; locked heading; broken play)
- agents/scripted.py — ScriptedWR (4 routes), ScriptedCB (legacy), ScriptedQB (route-aware lead throw)
- agents/observation.py — _accel_status() helper; build_qb_observation (CB burst/recovery lines, WR burst, extended history table with rec columns, separation trend alerts); build_cb_observation (WR/CB burst lines, WR-hip-turned alert, extended history table with rec columns); build_wr_observation (WR/CB burst lines, CB-hip-turned alert, extended history table with rec/spd columns); build_wr_pre_snap_observation, build_cb_pre_snap_observation, build_cb_intent_observation, _wr_facing_modifier
- agents/schema.py — QB parsers + CB parsers + WR parsers (parse_wr_pre_snap, parse_wr_live)
- agents/llm_client.py (OpenAI + Ollama)
- agents/prompts/ — qb_system (physics/burst/recovery scenarios), qb_pass1, qb_pass2, cb_system (physics + patience doctrine), cb_pre_snap, cb_pass1 (burst-aware decision framework), cb_pass2, wr_system (physics + three deception patterns), wr_pre_snap, wr_live_free (burst-aware framework), wr_live_committed, wr_live_broken, wr_ball_in_air
- sim/runner.py — A2 + A3 + A4 modes; WR pre-snap; per-step WR decide; call-for-ball one-step delay; OOB broken play trigger; heading lock; cut_recovery in move_history entries
- sim/seeds.py, rosters/default.yaml
- sim/scenarios/ — a1_*, a2_cb_slant, a3_wr_slant, a3_wr_comeback, a4_wr_{slant,comeback,curl,go,zig,drag,corner,in,double_move,post_corner}
- run_all_routes.py — runs all 10 A4 scenarios; --ollama / --model flags for Ollama provider
- render/renderer_pygame.py
- main.py
- tests/test_e2e.py
- article.md

## Architecture

**Physics (new):**
- `cut_recovery` steps penalize burst acceleration after any turn >35° at speed >3 yd/s
- Burst = `peak_accel * (1 - speed/max_speed)` — explosive from rest, tapers near top speed
- Speed shed on turn = `speed * (turn/90°) * 0.80 / agility_factor`
- Recovery reduces burst: `burst *= max(0.1, 1.0 - recovery_fraction * 0.75)`
- Braking clears recovery (plant-and-go footwork)

**QB agent (two-pass):**
- Pass 1: read field → hold or thinking+rough_target
- Pass 2: concrete options at target (bullet/hard/medium/soft/lob), WR projected at arrival

**CB agent (three-pass):**
- Pre-snap: choose offset_yards + side
- LIVE (per step): heading + facing + mode (normal/backpedal/brake)
- BALL_IN_AIR (once): intent = play_man / swat / go_for_pick; facing in subsequent movement steps is intent-aware

**WR agent (three-pass):**
- Pre-snap: reads CB alignment, outputs deception plan
- LIVE (per step): heading + facing + throttle + call_for_ball
  - Three prompt states: free (pre-call) / committed (post-call, ball held) / broken play
  - call_for_ball validated: heading must be within ±45° of cut_heading (or broken play)
  - Heading locked mechanically by runner post-call while ball held
- BALL_IN_AIR: free to chase bad throws

**Observations — burst/recovery info:**
- `_accel_status(cut_recovery)` → "FULL burst available" or "RECOVERING — X steps left, burst ~N%"
- All three agents see both players' burst status each step
- Explicit alerts: "CB HIP-TURNED — THIS IS YOUR WINDOW" / "WR HIP-TURNED — CLOSE NOW"
- Move history extended with `WR rec` / `CB rec` columns so agents can track recovery timeline

**CB observation — raw geometry, no option labels:**
- `_cb_situation()` emits a lean `GEOMETRY:` block: separation, bearing, WR projected pos in 0.5s, intercept bearing
- No option labels, no tradeoff descriptions, no wr_motion prose

## Known Issues
- **Windows console encoding bug**: Unicode chars (`°`, `→`, `≥`) in print statements crash stdout with charmap codec on Windows. 4/10 routes errored in Round 8 run. Fix: set `PYTHONIOENCODING=utf-8` before running or wrap prints in try/except.
- **N2 — WR wrong route shape**: WR ignores route geometry on 6/10 routes; defaults to generic fake-then-break. Needs per-phase heading context injected in observation.
- **N3 — WR facing hallucination**: WR computes QB bearing as cardinal direction instead of from actual (x,y). Must inject bearing as a computed value.
- **N4 — WR phantom CB rec trigger**: WR waits for "CB rec > 0" which is not in WR's observation. Needs observable proxy (CB heading delta).
- **N5 — WR escalation loop**: No step counter on current heading; WR loops fake indefinitely. Inject step count from simulation side.
- **N1/S6 — Parse error rate 10–25%** with qwen3:8b. No JSON-mode enforcement available via Ollama.
- **N6 — QB 1-step delay**: QB needs to throw same step as WR call on short-window plays. Parse error at critical step caused double_move PBU.
- **N7 — CB over-commits to fake**: CB declares "confirmed cut" after 2–3 steps with no hedge for double-move structure.
- **S2 — CB template-lock**: Boilerplate hold reasoning 7–20 steps every route. Different form than Round 7 but same pattern.
- **W1 — WR premature call**: Still calling before completing cut on in, zig.
- **W2 — WR wrong facing post-call**: Facing hallucination during ball flight (N3).
- **detected_cut_t**: Still misfires on jabs (P3).
- **CB intent variety**: C3 not addressed.

## Run History
- Round 1 (Ollama qwen3:8b): 2C/5D/1INC/1INT
- Round 2 (Ollama qwen3:8b, post-fix): 2C/5D/1INC/1INT
- Round 3 (OpenAI gpt-5-nano): 2C/6D/1PBU/1INT
- Round 4 (OpenAI gpt-5-nano): **4C/2D/3PBU/1INT** ← best full-run score
- Round 5 (OpenAI gpt-5-nano, post P-NEW + blacklist + ball-in-air fixes): 4C/1D/2PBU/1INC/1INT
- Round 6 partial (post CB redesign): slant_42 → PBU sep=1.24 (vs Run 5 DROP sep=4.83)
- Round 7 (post physics overhaul, gpt-5-nano): 3C/1D/3PBU/1INC/1INT/1SACK — down from Round 5
- Round 8 (Ollama qwen3:8b, 6 of 10 new; 4 errored): **1C/2D/3PBU** (new routes); 3C/2D/4PBU/1INT (all 10)

## Not Started
B–E phases
