# Build State
Current phase: A4 in progress (all three agents live; CB freed from prescriptions; WR gets CB reaction MOVE LOG; 10 routes run 3x — Ollama + OpenAI)

## Built
- engine/physics.py — PlayerState, apply_action (backpedal mode, new_facing/new_mode params), BACKPEDAL_SPEED_FRACTION=0.75
- engine/ball.py, field.py, resolution.py, state_machine.py
- engine/resolution.py — facing+arm-reach geometry for PBU/INT; CB_ARM_REACH=1.0, CB_HALF_REACH=0.5, CB_FACING_CONE=60°; play_man proximity bonus; WR facing multiplier (x1.15/x1.0/x0.80); optional CB (None in A3)
- replay/recorder.py
- agents/qb_agent.py (two-pass: hold/thinking → concrete options)
- agents/cb_agent.py (three-pass: pre_snap / decide_movement / decide_intent)
- agents/wr_agent.py (three-pass: pre_snap / decide / ball_in_air; call-for-ball state machine; locked heading; broken play)
- agents/scripted.py — ScriptedWR (4 routes), ScriptedCB (legacy), ScriptedQB (route-aware lead throw)
- agents/observation.py — build_qb_observation (CB optional, WR call one-step delay, WR facing modifier, sideline distances), build_cb_observation (fuzzy zone, situation block, intercept heading, intent-aware facing, CB self-action history), build_wr_observation (phase-gated: pre-cut/cut-window/post-cut, CB exact info, sideline warning, side-by-side MOVE LOG), build_wr_pre_snap_observation, _wr_facing_modifier
- agents/schema.py — QB parsers + CB parsers + WR parsers (parse_wr_pre_snap, parse_wr_live)
- agents/llm_client.py (OpenAI + Ollama)
- agents/prompts/ — qb_*, cb_*, wr_system, wr_pre_snap, wr_live_free, wr_live_committed, wr_live_broken, wr_ball_in_air
- sim/runner.py — A2 + A3 modes; WR pre-snap; per-step WR decide; call-for-ball one-step delay; OOB broken play trigger; heading lock; ScriptedQB isinstance dispatch; cb_mode in move_history
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

**CB observation SITUATION block — contextual, not prescriptive:**
- Shows positional geometry (separation, bearing, WR motion) and three movement options (backpedal / intercept / mirror) with tradeoffs and heading numbers for each.
- No RECOMMENDED action is emitted — CB decides based on context.
- Comeback/lateral states still described via `wr_coming_back` / `wr_going_lateral` flags as plain context.

**Deception mechanics (WR):**
- CB intercept calculation projects WR forward 0.5s along current heading/speed
- WR jabs (1-step heading deviation) make that projection wrong → CB overcommits → separation on real cut
- Jab pattern: 1 step off, snap back to 0°. Holding the jab heading = readable to CB.

**Observation additions (A4r2 session):**
- QB LEAD HINT: y-direction labeled explicitly (DECREASING/INCREASING)
- QB detected_cut_t: labels whether it matches expected cut time or is likely a jab
- CB: "YOUR RECENT ACTIONS" showing own heading + mode history per step

**Observation additions (A5 session):**
- WR: side-by-side MOVE LOG (WR hdg/spd + CB hdg/mode/Δhdg per step) — WR can now see whether its jabs moved the CB
- CB: `mode={cb.mode}` added to WR's current CB snapshot line

## Known Issues
- **P-NEW (FIXED in code, untested)**: Hard heading gate added to wr_agent.py decide() — call_for_ball suppressed if heading >45° from cut_heading. WR prompts updated to anticipate future separation. Run 5 will validate.
- **N2/O7 (PARTIALLY FIXED in code, untested)**: Live angle blacklist now emitted in WR observation — heading buckets used 3+ times with zero CB ΔHdg are listed as prohibited. Run 5 will show if model respects it.
- **O1 (FIXED in code, untested)**: wr_ball_in_air.txt rewritten to lock heading; observation block reinforces "DO NOT CHANGE HEADING." Run 5 will validate.
- **O4 (DEPENDENT on P-NEW fix)**: If slant WR now has to execute the cut before calling, it may still cut to wrong angle (40° instead of ~315°). Watch Run 5.
- **O3/N6 (PARTIALLY FIXED)**: QB go-route hint expanded — throw must clear CB's current y. QB "own judgment" block added post-call.
- **O2 (OPEN)**: Corner WR still abandons break and returns to stem. No concept of "terminal cut."
- detected_cut_t fires on first heading hold, not necessarily the real route break.
- CB pre-snap alignment not varying by route type.
- CB intent almost always "swat".

## Run History
- Round 1 (Ollama qwen3:8b): 2C/5D/1INC/1INT
- Round 2 (Ollama qwen3:8b, post-fix): 2C/5D/1INC/1INT
- Round 3 (OpenAI gpt-5-nano): 2C/6D/1PBU/1INT
- Round 4 (OpenAI gpt-5-nano): **4C/2D/3PBU/1INT** ← current best

## Not Started
B–E phases
