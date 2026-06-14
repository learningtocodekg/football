# Build State
Current phase: A4 — 3D. **WR route execution rebuilt as a SOFT RAIL (2026-06-14 s3)** — the long-standing
"WR ignores route geometry" problem is RESOLVED. All 6 routes the user flagged (go, comeback, curl, zig,
double_move + corner) now run with CORRECT SHAPES, not lucky catches. Judge plays by route/accuracy/coverage/
air-play, NOT the catch/PBU label (memory feedback-outcome-vs-quality). Lone open item: post_corner QB
deep-throw accuracy on multi-break routes (WR is open).

## WR soft rail + QB throw-timing — 2026-06-14 (session 3) — CURRENT WR DESIGN
- **Why:** the WR's one `heading` output carried two fighting jobs (run the route AND juke); no prompt could
  do both, so it abandoned the route. Split them: engine guarantees the route SHAPE; juke/read/call stay free.
- **`RouteRail` (agents/scripted.py).** govern() corrects the WR's decision each tick as a backstop; status()
  narrates it (ROUTE STATUS obs line). Depth-gated stem (`_burst_distance(stem_dur)`, early read >70%);
  duration-held fakes; early break only from leg0; STEM_CONE=25° feint limit (wide weave sheds ~40% speed/turn
  and dawdles the stem — was the curl/double_move killer); positional leash (LEASH_DISTANCE 2.0 / BACK_TOL
  0.75) on final leg & go; settle stop (comeback/curl) at SETTLE_DISTANCE 1.5.
- **Call gate** (user-approved; otherwise no-phase-gate stands): call HELD until the final break; settle routes
  fire the call AS THE WR HOOKS (ball arrives while CB carried past). Deferred early calls auto-fire.
- **QB window-filter** (qb_agent._meeting_options): pass2 only offered arcs arriving inside pass1's open
  window; none → hold (enforces deep-ball cushion discipline). DISABLED for settle routes.
- **QB lob heuristic** (qb_pass2): CB between WR and QB (in lane) → lob/loft over his head, not a flat bullet.
- WR prompt slimmed (juke/read/call only). tests/test_route_rail.py = 11 deterministic tests, all pass.
- Results (seed 42): go C2.29(lob), comeback C2.1, curl C1.79, zig C2.92, double_move C7.02, corner C1.81,
  slant/drag/in C. post_corner: route perfect/WR open, one run INCOMPLETE on QB deep-corner placement.
- SUPERSEDES the s2 "go/comeback fix" below and the project-wr-broken memory.

## Go + comeback fix — 2026-06-13 (session 2)
- **Go QB understanding.** QB was bulleting into the CB's downfield cushion (read sep as "open" when the
  CB was in front). qb_system.txt + qb_pass1.txt now teach: sep with the CB in FRONT is a cushion, not a
  beaten man; a deep ball is "over the top" only once the WR is EVEN WITH/PAST the CB; a SHRINKING sep
  with the CB in front is the cushion closing (not a window). Scoped to "ball thrown BEYOND the CB" so it
  does NOT bleed into underneath/settle routes. Validated 5/5 hold on the failing geometry + live CATCH;
  suite go sep GROWS in flight 2.14->3.52 (true over-the-top throw).
- **Comeback = settle-aware solver.** `_meeting_options` accepted in-stride projection only, so on a stop
  route it placed the ball where the WR would be if he kept running (the known settle-route caveat). Added
  `SETTLE_ROUTES={"comeback"}` + `SETTLE_DISTANCE=1.5` in qb_agent.py: for a settle route every arc meets
  the WR at the FIXED settle spot (break point + 1.5yd), only arrival time varies. `route` threaded through
  `QBAgent.decide()` + runner. Comeback route description (scripted.py) rewritten so the WR brakes/settles;
  QB geometry hint (observation.py) says bullet the settle spot. Live: WR settles ~1.5yd back, QB bullets it.
- **Open:** corner PBU (deep 315° contest) is the lone remaining loss. curl NOT in SETTLE_ROUTES yet
  (works, didn't want to regress it). No WR call-timing code gates were added (memory no-phase-gate).

## Air-phase + solver mechanical fix — 2026-06-13 (current ball-placement design)
- **WR air-phase throttle REMOVED.** Runner drives the WR at full speed to the catch point in
  BALL_IN_AIR and clamps it against overshoot (freeze at closest approach). LLM keeps heading/facing.
  Killed the "WR brakes to match landing timing → CB closes" bleed. Brake/required-speed math deleted
  from `wr_ball_in_air.txt`. [`sim/runner.py` move block]
- **QB meeting-point solver projects WR in-stride.** `_proj_distance()` (`qb_agent.py`) replaces the
  old constant-instantaneous-speed projection: ramps from current speed to top speed, lengthened by
  cut-recovery time, scaled by conservative `safety=0.9`. `wr_max_speed`+`wr_cut_recovery` threaded
  from `decide()`. Conservative on purpose — over-projection = ball out of reach (INCOMPLETE);
  under-projection = brief early arrival (contested, still often a catch). Fixes BOTH the early-freeze
  (PBU) and the overshoot (INCOMPLETE) failure modes.
- **Telemetry:** `sep_at_throw` / `sep_at_catch` added (decisive numbers); `max_separation` is the
  play-peak and does not track the outcome. `run_all_routes.py` prints sep@throw -> sep@catch.
- **Open blocker:** multi-break routes (drag/corner/post_corner/double_move) throw before the WR's
  final cut — solver can't foresee a second cut after release. WR-call-timing problem, next up.

## QB redo + realistic routes — 2026-06-12 (this is the current QB design)
- **Routes redefined by real NFL depth, cut TIMES derived from the run physics** (`scripted.py ROUTES`):
  slant 5yd/1.0s, post 10yd/1.8s, curl 10yd/1.8s/180, comeback 12yd/1.9s/225, out 1.6s/270, corner 1.8s/315,
  in 1.6s/90, drag 4yd/0.9s, zig/double_move/post_corner retimed; out/corner headings fixed (were swapped).
  `_est_yards` rewritten to the exponential burst-accel model (was overstating depth ~25%).
- **QB system prompt** = timeless context only (field/good-throw/separation@1.8&1.0 center-to-center/route
  frame/arc basics). **LEAD HINT + DIRECTION CHECK deleted.** Lean factual observation (no pre-chewed verdict).
- **QB gated on the WR call** (`runner.py`): LLM QB not invoked until the WR calls; ScriptedQB unaffected.
- **Two-step flow:** PASS 1 = the QB's own read — raw facts only, outputs `open_window [t_from,t_to]` (sec from
  now) or hold; judging openness is the QB's job, NO sep handed to it. PASS 2 = landing physics only —
  `_meeting_options` (qb_agent.py) solves per arc for the self-consistent point where a ball released now meets
  the WR's locked line (bisection on arrival time tau s.t. flight_time(dist to W(tau))==tau); shows meeting
  coord + arrival(+s) + range, **no CB/sep**. QB picks arc + target_coord. Resolves the deep-ball catch-22
  (arc↔timing↔coordinate) the model can't solve mentally. **Caveat: assumes constant WR speed → exact for
  verticals, wrong for settle routes (curl/comeback) until a decel model is added.**
- schema: `parse_qb_pass1` requires `open_window` (target_area dropped); `parse_qb_pass2` = arc + target_coord.
- **~~Open blocker~~ FIXED 2026-06-13:** WR air-phase brake (`required_speed=dist/ETA`) + early-arrival
  freeze + solver constant-speed projection — all resolved mechanically. See top section.

## Realism work — 2026-06-11 (merged to main)
- **P1 WR plan cadence**: WRAgent emits a PLAN of 1–4 per-step actions (`schema.parse_wr_plan`), consumed
  from a queue with no LLM call until exhausted; aborts only when the ball is thrown. Runner unchanged.
  **2026-06-12: plan is now TIMESTAMPED + Pydantic structured output** (`WRStep`/`WRPlan` via
  `chat.completions.parse`, OpenAI path; Ollama keeps lenient `parse_wr_plan`). Each step carries absolute
  `t` (window `[T+0.1, T+0.4]`) + its own reasoning — this is what finally made the WR hold its stem to the
  cut window (t≈0.9 on the slant) instead of breaking at t=0.2.
- **P2 deterministic three-zone catch** (`resolution.resolve`): sep≥1.8 → CATCH; sep≤1.0 → CB win (INT if
  go_for_pick+arm/facing else PBU); 1.0–1.8 = the only rolled band (attrs/intent weight one roll). Removed
  the sigmoid/floor and the catch-rating-multiplies-everything bug. CB intent autonomy + INT preserved.
- **P3**: removed WR right-of-way pushout (bodies overlap now) + mid-flight lane-contest RNG from runner.
- **WR prompt**: `wr_live_free.txt` rewritten 160→~33 lines; observation `CUT TARGET` line (cut time/depth
  with ±0.4s/±2.5yd tolerance); STEM (fake-and-return, no early call) vs FINAL BREAK phases; break heading
  must be the FINAL direction even if >90° from current (fixes curl running an out instead of hooking to 180).
- **eval/metrics.py** added (P5); PRD.md deleted (P4); dead `WRAgent.record_heading` removed.
- **KNOWN INTERACTION**: realism WR assumes a QB that waits for the WR call. main's anticipation QB (d376c1e)
  throws early → slant PBU / curl INCOMPLETE. Realism gains need the QB to wait. (QB rollback 83c4e26 was
  testing-only and reverted before merge.) See left_off.md.

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
- agents/schema.py — QB parsers + CB parsers + WR parsers (parse_wr_pre_snap, parse_wr_live, parse_wr_plan); Pydantic WRStep/WRPlan + wr_plan_steps() for structured-output WR plans
- agents/llm_client.py (OpenAI + Ollama; call_llm_structured() = chat.completions.parse with a Pydantic response_format)
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

## WR early-break — FIXED 2026-06-12 (timestamped structured-output plan)
- Long-standing "WR ignores route geometry / breaks at t=0.2" is resolved on the slant + go stem. Root
  cause was a blind batched plan (break+call baked into the first t=0.0 plan, served from the queue with no
  fresh CB look) + cloned per-step reasoning that masked it. Prompt-only fixes failed (REQUIRE language
  broke the freedom principle and was reverted; factual reframe and a "tick-math" fact both still broke
  early — the model even rationalized a 0.3–0.4s stem from the tick fact). The fix that stuck: force each
  plan step to carry its absolute `t` via a Pydantic structured-output schema, so the model can't pretend a
  4-step (0.4s) plan reaches the 1.0s break. slant = CATCH sep 4.35, WR held stem to t=0.9. Freedom intact
  (it re-plans each tick and chooses to hold). **Not yet run across the full 10-route suite.**
- **Loft hang-time / WR air overshoot (open, QB thread)**: go ended INCOMPLETE (sep 2.34) NOT from the stem
  — QB lofted 17.6yd (~1.9s hang), WR reached the fixed landing spot too early then thrashed
  brake/accelerate and overshot. Parked for the QB thread.

## Known Issues (post-R15 regression fixes, full re-run pending)

### R15 regression root cause + fixes (not yet re-run at scale)
- **Window A heading lock bug** (caused R15 regression from 8C/2INC → 4C/1PBU/5INC): WR was calling `call_for_ball` with stem heading (0°) instead of break heading. Heading is mechanically locked at call time → QB throws to wrong trajectory. Fixed via `CRITICAL — HEADING WHEN CALLING` in `wr_live_free.txt`.
- **CB WR-ETA check**: cb_pass2.txt + cb_intent_observation now include WR dist/ETA to landing zone. CB compares sprint_time vs wr_eta before choosing swat/pick over play_man.
- **WR ball-in-air brake guidance**: wr_ball_in_air.txt shows REQUIRED SPEED = dist/ETA. Observation injects current speed + required speed. Curl still overshoots (behavioral).

### 3D-specific
- **QB arc choice is high-variance**: smoke test picked loft on a quick slant (INCOMPLETE); identical re-run picked bullet with correct reasoning (CATCH). One sample each way — single runs can't distinguish prompt effects from model variance.
- **CB flip-flops cut detection — partially fixed**: detected_cut_t now exposed in CB observation; CB smoke test (slant) printed CUT CONFIRMED correctly. Stem-phase check in cb_pass1 may still override it on early steps.
- gen_demo.py still emits legacy ball_speed_mph format.

### Route-specific
- **Curl — FIXED (CATCH)**: lead-hint now projects off the locked `wr_call_heading` (not the noisy physical heading at the cut). curl_42 = CATCH, throw_t=2.7s, sep=5.02. Long-standing curl INCOMPLETE resolved.
- **Go — straight-route fix applied, UNVERIFIED**: QB took a SACK with 6.62 yd separation because the DIRECTION CHECK logic waited for a route "break" that never comes on a go route. Added a `straight_route` branch in `build_qb_observation` (all phases upfield → direction confirmed at snap; openness = WR overtaken CB). Committed; re-run was killed before completing.
- **Comeback WR bug**: WR calls at heading=0° before executing 180° break → heading locks wrong direction. Pre-existing, lowest priority.

### QB autonomy (this session)
- QB doctrine reframed from "wait for the WR call" to **a throw is a prediction**: route design = expectation; real position/heading/velocity history = confirmation; "open" = direction confirmed AND separation predicted at arrival. Observation reports facts (DIRECTION CHECK), QB makes the openness call. See `qb_system.txt` "WHAT 'OPEN' MEANS" + `observation.py` direction-check block.

### QB autonomy — DECISION: REDO THE QB PROMPTING (2026-06-11, latest session)
- Distance-frame fix landed (WR DOWNFIELD DEPTH line in QB obs, throw-distance relabel, qb_system "two
  distances" block, wr_start plumbed through runner). It PARTIALLY worked — go re-run had the QB HOLD at
  t=0.5 citing "1.7 yards depth" — but the QB still threw early one step later: **go seed 42 = INT,
  sep=0.96, throw_t=0.6, 15yd bullet.**
- ROOT CAUSE is NOT the distance frame. At the throw, the WR (y=53.0) had NOT overtaken the CB (y=55.1).
  The early throw is caused by the QB observation itself: (1) the LEAD HINT hands the QB a pre-computed
  "throw to the projected coord" deep spot that always looks open on a vertical even when the WR is
  behind the CB; (2) the obs never surfaces the decisive go fact — has the WR passed his man. Plus the
  same full observation (LEAD HINT included) is sent in BOTH QB pass 1 and pass 2, so pass 1 isn't a
  clean self-read.
- **Decision (user): completely redo the QB prompting next session, working with an AI.** Ground-truth
  reference written to repo root: `QB_step_example.txt` / `WR_step_example.txt` / `CB_step_example.txt`
  (full per-step prompts reconstructed from the real go replay). Design goals: feed facts not answers
  (kill/relegate the LEAD HINT), surface WR-vs-CB depth, genuinely separate pass1/pass2. Gating the QB
  on the WR call (memory project_qb_call_gated) is still on the table but may be made moot by the redo.

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
- Round 14 (GPT-5-nano, seed 42, post QB lead fix): **8C/2INC** — slant CATCH sep=4.77, corner CATCH sep=5.34 (fixed from INCOMPLETE), go INCOMPLETE (WR late call t=3.7 model variance), comeback INCOMPLETE (pre-existing WR bug)
- CB overhaul (code+prompts, smoke tested): slant smoke CATCH sep=5.52 — CB correctly computed sprint_time > ETA → play_man. CUT CONFIRMED line working.
- Round 15 (GPT-5-nano, seed 42, CB changes): **4C/1PBU/5INC** — regression from R14. Root cause: Window A heading lock bug (WR calling with stem heading 0° instead of break heading). R15 fixes landed: wr_live_free.txt heading note, wr_ball_in_air.txt brake guidance, cb_pass2.txt WR-ETA check. Two-route sanity: slant INT→PBU (improved), curl still INCOMPLETE (overshoot). Full re-run with fixes pending.
- QB autonomy session (GPT-5-nano, seed 42, two-route sanity): **curl CATCH** (throw_t=2.7s, sep=5.02 — lead-hint call-heading fix + prediction doctrine) / **go SACK** (sep=6.62, QB never threw — straight-route fix added afterward, UNVERIFIED). Full suite not run.
- Go + comeback session (GPT-5-nano, seed 42): **9C/1PBU** (was 6C/3PBU/1DROP). go CATCH (sep grows in
  flight 2.14->3.52 = over-the-top deep ball), comeback CATCH (WR settles ~1.5yd back, bullet to spot),
  curl/post_corner/zig/slant/double_move/drag/in all CATCH; only loss corner PBU (deep 315° contest).
  go validated 5/5 hold deterministically on the failing cushion geometry.
- WR stem-fix session (GPT-5-nano, seed 42, timestamped structured-output plan): **slant CATCH sep=4.35** — WR held stem to t=0.9, broke at cut window (was t=0.2), 0 parse errors. **go INCOMPLETE sep=2.34** — early-deep-throw FIXED (held stem, called t=0.9, throw t=1.5 not t=0.2) but lost to a separate loft hang-time/WR-overshoot issue (QB thread). Full suite not yet run.

## Not Started
B–E phases
