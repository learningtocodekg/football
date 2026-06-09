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

## Known Issues (post-Round 12 full run)

### WR — mostly fixed
- **post_corner INCOMPLETE**: Window A fires before terminal 315° break. WR calls at intermediate 45° heading, heading locks, terminal break never executes. Window A should only fire when no more cuts remain.
- **curl INCOMPLETE**: WR correct (called heading=180° after full stem). QB targeting bug — throws to y=68.4 behind a WR already at y≈67.5 running back toward QB (heading=180° = decreasing y). QB misprojects 180° heading as increasing y.
- **slant PBU**: Full stem (t=2.2), CB still swats at 1.08 yd. Likely irreducible geometry.

### CB — BROKEN (critical)
- **Always swat intent** (10/10 routes). Repeatedly admits arm tip is 3-5 yd from ball path, still picks swat. Never picks play_man even at close range. CB is a passive observer during ball flight.
- **Always 5 yd off-coverage** pre-snap. Never presses regardless of route type.
- **Self-induces recovery** from minor tracking adjustments (2-4 times per route), killing closing burst at the worst moments.
- **Patience doctrine → passivity**: CB was broken before but masked by WR failures. WR now executes clean routes → CB weaknesses fully exposed.

## Run History
- Round 1 (Ollama qwen3:8b): 2C/5D/1INC/1INT
- Round 2 (Ollama qwen3:8b, post-fix): 2C/5D/1INC/1INT
- Round 3 (OpenAI gpt-5-nano): 2C/6D/1PBU/1INT
- Round 4 (OpenAI gpt-5-nano): **4C/2D/3PBU/1INT**
- Round 5 (OpenAI gpt-5-nano, post P-NEW + blacklist + ball-in-air fixes): 4C/1D/2PBU/1INC/1INT
- Round 6 partial (post CB redesign): slant_42 → PBU sep=1.24 (vs Run 5 DROP sep=4.83)
- Round 7 (post physics overhaul, gpt-5-nano): 3C/1D/3PBU/1INC/1INT/1SACK — down from Round 5
- Round 8 (Ollama qwen3:8b, 6 of 10 new; 4 errored): **1C/2D/3PBU** (new routes); 3C/2D/4PBU/1INT (all 10)
- Round 9 (GPT-5-nano, all 10 routes, post-encoding+JSON+geometry fixes): **2C/3D/4PBU/1INT**
- Slant-only focused session (post-separation-redesign + call-timing + parse fix): slant_42 → **CATCH sep=2.07 yd**, 0 parse errors
- Round 10 (GPT-5-nano, post obs overhaul): 4C/1INC/5PBU
- Round 11 (Ollama qwen3:8b, post call-timing overhaul): **7C/3PBU**
- Round 12 (GPT-5-nano, post CB-rec quality check + phase gate): **7C/1PBU/2INC** ← best GPT score

## Not Started
B–E phases
