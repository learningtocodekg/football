# Build State
Current phase: A2 (CB agent built, under iteration)

## Built
- engine/physics.py — PlayerState, apply_action (backpedal mode, new_facing/new_mode params), BACKPEDAL_SPEED_FRACTION=0.75
- engine/ball.py, field.py, resolution.py, state_machine.py
- engine/resolution.py — facing+arm-reach geometry for PBU/INT; CB_ARM_REACH=1.0, CB_HALF_REACH=0.5, CB_FACING_CONE=60°; play_man proximity bonus
- replay/recorder.py
- agents/qb_agent.py (two-pass: hold/thinking → concrete options)
- agents/cb_agent.py (three-pass: pre_snap / decide_movement / decide_intent)
- agents/scripted.py — ScriptedWR (4 routes), ScriptedCB (legacy), ScriptedQB (route-aware lead throw)
- agents/observation.py — build_qb_observation, build_cb_observation (fuzzy zone, situation block), build_cb_pre_snap_observation, build_cb_intent_observation
- agents/schema.py — QB parsers + CB parsers (parse_cb_pre_snap, parse_cb_pass1, parse_cb_pass2)
- agents/llm_client.py (OpenAI + Ollama)
- agents/prompts/ — qb_system, qb_pass1, qb_pass2, cb_system, cb_pre_snap, cb_pass1, cb_pass2
- sim/runner.py — A2 runner: ScriptedQB wiring, CB pre-snap, per-step CB movement, intent decision
- sim/seeds.py, rosters/default.yaml
- sim/scenarios/ — a1_basic, a1_local, a1_1st10_slant, a1_2nd25_post, a1_3rd10_comeback, a1_3rd3_out, a2_cb_slant
- render/renderer_pygame.py
- main.py
- tests/test_e2e.py (mock QB + CB, passes)
- article.md

## Architecture

**QB agent (two-pass):**
- Pass 1: read field → hold or thinking+rough_target
- Pass 2: concrete options at target (bullet/hard/medium/soft/lob), WR projected at arrival

**CB agent (three-pass):**
- Pre-snap: choose offset_yards + side
- LIVE (per step): heading + facing + mode (normal/backpedal/brake)
- BALL_IN_AIR (once): intent = play_man / swat / go_for_pick

**CB observation key feature — SITUATION block:**
- Three states with RECOMMENDED action (exact heading/facing/mode values):
  1. CB upfield of WR → backpedal (heading ~0°, facing ~180°)
  2. WR just passed CB → close gap immediately
  3. WR >2 yd ahead → CHASE (sprint at bearing to WR)

**ScriptedQB:**
- Simulates WR forward via ScriptedWR.move() for eta seconds (two-pass refinement)
- No linear projection — uses exact same physics as game loop
- Activated by qb_scripted: true in scenario YAML

## Known Issues
- CB intent is almost always "swat" regardless of geometry; swat often fails silently (arm not on lane)
- CB pre-snap alignment not yet varying by route — always picks off-coverage outside
- QB still throws slightly early on developing routes (A1 carryover)
- Ollama local runs functional but slow; qwen3 parse error rate ~73% without json_object constraint

## Not Started
A3 (WR agent), A4 (all three live), B–E
