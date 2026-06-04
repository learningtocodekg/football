# Left Off
Date: 2026-06-04

## What We Worked On
Phase A2 — CB agent. Full implementation from scratch.

## What Got Done

**CB Agent built (agents/cb_agent.py):**
- Three-pass structure: pre-snap alignment (one-time), per-step movement (heading/facing/mode), ball-in-air intent (intercept/swat/play_man)
- Pre-snap: LLM chooses offset_yards + side (inside/outside/press) relative to WR
- LIVE: LLM outputs heading + facing + mode each step; `apply_decision()` converts to physics
- BALL_IN_AIR: LLM locks intent once on ball release; feeds directly into resolve()

**Physics/resolution expanded:**
- `apply_action()` now accepts `new_facing` and `new_mode` — CB can face a different direction than it moves (backpedal)
- Backpedal speed capped at 75% of max_speed via `BACKPEDAL_SPEED_FRACTION`
- resolution.py: PBU/INT now require CB facing within 60° of ball + arm tip on ball path
  - PBU (swat): 1.0 yd arm reach
  - INT (go_for_pick): 0.5 yd arm reach
  - play_man: proximity bonus — closer hit at catch = higher drop chance

**Observation scaffolding (agents/observation.py):**
- `build_cb_observation()`: situation block with pre-computed RECOMMENDED action (exact heading/facing/mode), WR history, fuzzy landing zone (±4 yd at release → ±0.25 yd at arrival), arm reach readout
- `_cb_situation()`: three states — "WR approaching (backpedal)", "WR just passed (close gap)", "WR beaten (CHASE)" — each with unambiguous RECOMMENDED heading
- `build_cb_pre_snap_observation()`, `build_cb_intent_observation()`

**Prompts (agents/prompts/):**
- cb_system.txt, cb_pre_snap.txt, cb_pass1.txt, cb_pass2.txt

**ScriptedQB (agents/scripted.py):**
- Throws at fixed time, leads WR by simulating the scripted route forward using the exact same physics (ScriptedWR.move()) for eta seconds — two-pass refinement
- Wired via qb_scripted: true in scenario YAML; wr_agent/wr_attrs injected by runner

**New scenario (sim/scenarios/a2_cb_slant.yaml):**
- Scripted QB, no LLM calls, for CB iteration

**runner.py updated:**
- ScriptedQB wiring, CB pre-snap call + position adjustment, per-step CB movement, ball-in-air intent call, CB telemetry

**test_e2e.py updated:**
- Mock handles CB's three call types (pre-snap, movement, intent) by detecting system prompt keyword "cornerback"

## What's Broken / Open
- CB still sometimes oscillates direction on the step the WR passes it (brief wrong heading before CHASE kicks in) — not a blocker
- CB pre-snap: always picks offset=5, side=outside regardless of route — model isn't varying alignment yet; not tuned
- CB intent is almost always "swat" even when too far to actually reach the ball — geometry feedback in observation helps but model is conservative
- ScriptedQB throws right at t=throw_t even if the WR is mid-cut; could add a cut-aware delay but not needed yet

## NEXT STEP
Run multiple seeds and routes (post, out, comeback) with `a2_cb_slant.yaml`-style scripted scenarios to stress-test CB coverage. Look at replays to see if the CB is actually contesting at arrival — the swat intent fires but does the facing/arm geometry actually pass the resolution check? Add a debug line in resolution.py to print whether `cb_arm_pbu` was True or False so we can tell if the CB's swat attempts are valid or just whiffing silently.
