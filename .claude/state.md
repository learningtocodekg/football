# Build State
Current phase: A4 — 3D (arc physics + QB arc/z interface landed, commit fe02ef6; first live 3D slant = CATCH; all three viewers 3D-ready and human-verified; full 10-route 3D baseline NOT yet run — going route-by-route)

## Built
- engine/physics.py — PlayerState (+ cut_recovery field), apply_action (dynamic burst, cut recovery, speed shed), cut_recovery_steps(), BACKPEDAL_SPEED_FRACTION=0.75, CUT_RECOVERY_BASE_STEPS=4, CUT_ANGLE_THRESHOLD=35°, CUT_SPEED_THRESHOLD=3.0
- engine/ball.py — 3D projectile physics: ARC_ANGLES {bullet 15°, drive 25°, touch 35°, loft 45°}, solve_arc() (t_flight, required speed, peak), max_ball_speed(throw_power), max_range(), throw_ball(arc, target_z) → None if infeasible, advance_ball (closed-form z, final-step snap to landing), ball_z_at_xy(); G=10.7 yd/s², RELEASE_Z=2.2, target_z clamp [0.3, 3.0]. (Old 2D MPH_TO_YDS was mph→ft/s — ball was 3× too fast all of Phase A.)
- engine/field.py, state_machine.py
- engine/resolution.py — facing+arm-reach geometry for PBU/INT; CB_ARM_REACH=1.0, CB_HALF_REACH=0.5, CB_FACING_CONE=60°; play_man proximity bonus; WR facing multiplier (x1.15/x1.0/x0.80); optional CB (None in A3); 3D: WR/CB_VERTICAL_REACH=3.0, catch-height multipliers (chest 1.0, <0.9 ×0.85, >2.4 ×0.78), HIGH_BALL_Z=2.4 cuts CB swat/pick ×0.6, lane checks require ball z ≤ reach (via ball_z_at_xy)
- replay/recorder.py — ball snapshots now 3-elem pos [x,y,z], landing [x,y,z], arc field
- agents/qb_agent.py (two-pass: hold/thinking → arc options table: per feasible arc t_flight/mph/peak_z/WR+CB@arrival/lane note; outputs option label + target_z; takes throw_power)
- agents/cb_agent.py (three-pass: pre_snap / decide_movement / decide_intent)
- agents/wr_agent.py (three-pass: pre_snap / decide / ball_in_air; call-for-ball state machine; locked heading; broken play)
- agents/scripted.py — ScriptedWR (4 routes), ScriptedCB (legacy), ScriptedQB (route-aware lead throw)
- agents/observation.py — _accel_status() helper; build_qb_observation (CB burst/recovery lines, WR burst, extended history table with rec columns, separation trend alerts); build_cb_observation (WR/CB burst lines, WR-hip-turned alert, extended history table with rec columns); build_wr_observation (WR/CB burst lines, CB-hip-turned alert, extended history table with rec/spd columns); build_wr_pre_snap_observation, build_cb_pre_snap_observation, build_cb_intent_observation, _wr_facing_modifier
- agents/schema.py — QB parsers + CB parsers + WR parsers (parse_wr_pre_snap, parse_wr_live)
- agents/llm_client.py (OpenAI + Ollama)
- agents/prompts/ — qb_system (physics/burst/recovery scenarios), qb_pass1, qb_pass2, cb_system (physics + patience doctrine), cb_pre_snap, cb_pass1 (burst-aware decision framework), cb_pass2, wr_system (physics + three deception patterns), wr_pre_snap, wr_live_free (burst-aware framework), wr_live_committed, wr_live_broken, wr_ball_in_air
- sim/runner.py — A2 + A3 + A4 modes; WR pre-snap; per-step WR decide; call-for-ball one-step delay; OOB broken play trigger; heading lock; cut_recovery in move_history entries; 3D throw path (arc/target_z, infeasible→hold); mid-flight lane contest (ball ≤0.75yd from CB at z≤3.0, CB facing → tip/pick roll, once per flight, >3yd from catch point)
- sim/seeds.py, rosters/default.yaml
- sim/scenarios/ — a1_*, a2_cb_slant, a3_wr_slant, a3_wr_comeback, a4_wr_{slant,comeback,curl,go,zig,drag,corner,in,double_move,post_corner}
- run_all_routes.py — runs all 10 A4 scenarios; --ollama / --model flags for Ollama provider
- render/renderer_pygame.py — top-down + ball shadow/z + synchronized side-elevation panel (arc vs reach lines)
- render/renderer_ursina.py — 3D Madden-cam viewer (human-verified; ursina 8.x: use color.rgb32 not rgb, camera.look_at is unreliable → explicit pitch, camera anchored behind QB snap pos, ASCII-sanitized reasoning)
- viewer/debug_viewer.py — decision-log viewer with replay dropdown; 3D-aware ball draw (shadow + z label), handles legacy 2D replays
- main.py
- tests/test_e2e.py (3D assertions), tests/test_ball3d.py (arc physics unit suite)
- article.md

## Architecture

**Physics (new):**
- `cut_recovery` steps penalize burst acceleration after any turn >35° at speed >3 yd/s
- Burst = `peak_accel * (1 - speed/max_speed)` — explosive from rest, tapers near top speed
- Speed shed on turn = `speed * (turn/90°) * 0.80 / agility_factor`
- Recovery reduces burst: `burst *= max(0.1, 1.0 - recovery_fraction * 0.75)`
- Braking clears recovery (plant-and-go footwork)

**Ball (3D):**
- Throw = (target [x,y], arc, target_z). Arc fixes launch angle; physics derives t_flight + required speed; speed validated vs throw_power (infeasible arcs not offered)
- Flight times real now: 30yd bullet 1.28s / drive 1.66s / touch 2.01s / loft 2.40s; power-85 ranges: bullet ~35yd, loft ~67yd
- Mid-flight lane contest + height-aware resolution (see Built). Vertical model is STATIC REACH (3.0 yd, no jump action — jump is a planned follow-up)

**QB agent (two-pass):**
- Pass 1: read field → hold or thinking+rough_target (2D ground spot)
- Pass 2: arc options table (bullet/drive/touch/loft) with t_flight/peak_z/WR+CB@arrival/lane-height note; picks option label + target_z

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

## Known Issues (post-3D transformation)

### 3D-specific
- **QB arc choice is high-variance**: smoke test picked loft on a quick slant (INCOMPLETE); identical re-run picked bullet with correct reasoning (CATCH). One sample each way — single runs can't distinguish prompt effects from model variance.
- **CB flip-flops cut detection during long flights** (new failure mode): on the 1.2s slant flight, reasoning alternated "real cut to 45°" ↔ "still in stem" on consecutive steps; heading whipsawed, 3 self-induced recoveries, no contest. Stateless per-step re-derivation of an already-established fact. (Runner computes detected_cut_t; CB obs doesn't expose it.)
- **Flight times 3× longer than all of Phase A** (2D unit bug fixed): every timing intuition the agents were tuned on has shifted. Expect catch-rate drop initially; that's the harder, realistic test, not regression.
- 9 of 10 replays/<route>_42.json are stale pre-3D runs (flat ball); only slant_42 is 3D until Round 14 overwrites them.
- gen_demo.py still emits legacy ball_speed_mph format.

## Known Issues carried from 2D (post-Round 12 + CB prompt overhaul)

### WR — mostly fixed
- **post_corner INCOMPLETE**: Window A fires before terminal 315° break. WR calls at intermediate 45° heading, heading locks, terminal break never executes. Window A should only fire when no more cuts remain.
- **curl INCOMPLETE**: WR correct (called heading=180° after full stem). QB targeting bug — throws to y=68.4 behind a WR already at y≈67.5 running back toward QB (heading=180° = decreasing y). QB misprojects 180° heading as increasing y.
- **slant PBU**: Full stem (t=2.2), CB still swats at 1.08 yd. Likely irreducible geometry.

### CB — prompt overhaul confirmed working (Round 13)
Shadow model working: play_man on 8/10 routes, doom loop eliminated, sep at throw 2–4 yd. Residual:
- **Bearing vs heading confusion**: on curl break CB briefly reads "WR cut to 270°" instead of 180°. Self-corrects next step.
- **Pre-snap 5 yd every route**: cb_pre_snap.txt example JSON hardcodes offset_yards=5.
- **180° flip costs recovery**: unavoidable on curl/comeback reversal.

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
- Round 13 (GPT-5-nano, post CB prompt overhaul): **7C/2PBU/1DROP** — CB play_man 8/10, doom loop eliminated, sep at throw 2–4 yd (was 9+ yd)
- 3D transformation (commit fe02ef6): physics/e2e/A4-mock tests pass; live slant smoke = INCOMPLETE (QB loft, 2.4s hang, WR called pre-cut). Round 14 (full 10-route 3D baseline) pending
- 3D slant re-run (GPT-5-nano, seed 42): **CATCH sep=3.94** — QB bullet @ z=1.5 (correct flattest-arc reasoning), WR called at cut t=2.0 + clean ETA management in flight, CB flip-flopped cut detection and never contested. 0 parse errors

## Not Started
B–E phases
