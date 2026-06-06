# Build State
Current phase: A4 in progress (all 3 LLM agents live; 10 routes run and analyzed twice)

## Built
- engine/physics.py — PlayerState, apply_action (backpedal mode, new_facing/new_mode params), BACKPEDAL_SPEED_FRACTION=0.75
- engine/ball.py, field.py, resolution.py, state_machine.py
- engine/resolution.py — facing+arm-reach geometry for PBU/INT; CB_ARM_REACH=1.0, CB_HALF_REACH=0.5, CB_FACING_CONE=60°; play_man proximity bonus; WR facing multiplier (x1.15/x1.0/x0.80); optional CB (None in A3)
- replay/recorder.py
- agents/qb_agent.py (two-pass: hold/thinking → concrete options)
- agents/cb_agent.py (three-pass: pre_snap / decide_movement / decide_intent)
- agents/wr_agent.py (three-pass: pre_snap / decide / ball_in_air; call-for-ball state machine; locked heading; broken play)
- agents/scripted.py — ScriptedWR (4 routes), ScriptedCB (legacy), ScriptedQB (route-aware lead throw)
- agents/observation.py — build_qb_observation (CB optional, WR call one-step delay, WR facing modifier, sideline distances), build_cb_observation (fuzzy zone, situation block, intercept heading, intent-aware facing), build_wr_observation (phase-gated: pre-cut/cut-window/post-cut, CB exact info, sideline warning), build_wr_pre_snap_observation, _wr_facing_modifier
- agents/schema.py — QB parsers + CB parsers + WR parsers (parse_wr_pre_snap, parse_wr_live)
- agents/llm_client.py (OpenAI + Ollama)
- agents/prompts/ — qb_*, cb_*, wr_system, wr_pre_snap, wr_live_free, wr_live_committed, wr_live_broken, wr_ball_in_air
- sim/runner.py — A2 + A3 modes; WR pre-snap; per-step WR decide; call-for-ball one-step delay; OOB broken play trigger; heading lock; ScriptedQB isinstance dispatch
- sim/seeds.py, rosters/default.yaml
- sim/scenarios/ — a1_*, a2_cb_slant, a3_wr_slant, a3_wr_comeback, a4_wr_{slant,comeback,curl,go,zig,drag,corner,in,double_move,post_corner}
- run_all_routes.py — runs all 10 A4 scenarios; --ollama / --model flags for Ollama provider
- render/renderer_pygame.py
- main.py
- tests/test_e2e.py
- article.md

## Architecture

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
  - Phase-gated: pre-cut (run 0°, jab fakes) / cut window (execute break + call) / post-cut
  - call_for_ball validated: heading must be within ±45° of cut_heading (or broken play)
  - Heading locked mechanically by runner post-call while ball held
- BALL_IN_AIR: free to chase bad throws

**CB observation SITUATION block — 4 states:**
1. CB upfield, WR approaching → backpedal (heading ~0°, facing ~180°)
2. CB upfield, WR running BACK toward QB → flip hips, CHASE downfield (comeback fix)
3. WR just passed CB (0–2 yd ahead) → close gap immediately
4. WR >2 yd ahead → CHASE (intercept heading, not just current bearing)

**Deception mechanics (WR):**
- CB intercept calculation projects WR forward 0.5s along current heading/speed
- WR jabs (1-step heading deviation) make that projection wrong → CB overcommits → separation on real cut
- Jab pattern: 1 step off, snap back to 0°. Holding the jab heading = readable to CB.

**CB SITUATION block — 5 states (updated):**
5. WR going lateral (heading 45–135° or 225–315°) → DRIVE LATERALLY to intercept (not backpedal)

**Observation additions (this session):**
- WR observation: "YOUR RECENT ACTIONS" with heading + throttle per step
- CB observation: "YOUR RECENT ACTIONS" with heading + mode per step
- QB LEAD HINT: y-direction labeled explicitly (DECREASING/INCREASING)
- QB detected_cut_t: labels whether it matches expected cut time or is likely a jab

## Known Issues
- **N2**: WR jab template is 330°/30° on every route regardless of coaching. Self-action history
  may help; not yet verified. Approach TBD.
- **N5**: Curl WR drifts sideways during ball-in-air free phase. Broader ball-in-air tracking
  question — don't patch curl-specifically.
- **N6**: QB throw speed selection — tends to lob horizontal routes. Fundamental QB question.
- CB pre-snap alignment not varying by route type.
- CB intent is almost always "swat."

## Not Started
B–E
