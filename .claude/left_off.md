# Left Off
Date: 2026-06-09

## What We Worked On
The 3D transformation (future_3d.md), one-shot: arc physics, QB arc + 3D placement interface, height-aware resolution, mid-flight lane contests, both debug viewers, tests. Committed as `fe02ef6`.

## What Got Done

### Engine
- `engine/ball.py` rewritten: real projectile physics. Arc label = launch angle (bullet 15°, drive 25°, touch 35°, loft 45°). For a target distance the engine solves the exact parabola → t_flight, required launch speed (validated vs throw_power), peak height. `BallState` gains z/vz/origin/landing_z/arc. `ball_z_at_xy()` queries trajectory height at any ground point. Final flight step snaps to the landing point.
- **Found and fixed a 2D unit bug**: `MPH_TO_YDS = 1.46667` is mph→**ft/s**, so the 2D ball flew ~3× too fast (20yd throws "arrived" in ~0.3s). Real flight times now: 30yd bullet ≈ 1.3s, loft ≈ 2.4s. Expect outcome shifts — CB closes during flight now.
- `engine/resolution.py`: vertical reach 3.0 yd (static — no jump action, by user decision; jump is a documented follow-up). Catch-height multipliers (chest 1.0, high-point ×0.78), high balls (>2.4) cut CB swat/pick ×0.6, lane checks require ball within reach height.
- `sim/runner.py`: mid-flight lane contest — ball within 0.75 yd of CB at reachable height, CB facing it → one tip(PBU)/pick(INT) roll per flight, only >3 yd from the catch point. THROW event: arc, target_z, real eta, mph.

### QB interface
- Pass 2 options table = one row per **feasible** arc: t_flight, mph, peak_z, WR/CB projections at arrival, sep@arr, lane-clearance note ("clears CB (z=5.4)" / "TIP/PICK RISK"). Out-of-range arcs listed; none feasible → auto hold.
- QB outputs `{"option": "<arc>", "target_z": 1.5}`; target_z clamped [0.3, 3.0]. `QBAgent` now takes `throw_power` (mph plumbing removed). ScriptedQB throws by arc.

### Observations / prompts
- QB obs: arc flight times to WR + arm ranges per arc. CB/WR obs during ball-in-air: ball z now, arrival height label, reach info. QB system prompt rewritten (arcs, z placement, lane risk, anticipation); CB/WR system prompts get compact 3D sections.

### Viewers (both, per user decision)
- pygame: ball shadow + height-scaled ball + z label; new synchronized side-elevation panel (full arc profile vs player reach lines at z=3).
- `render/renderer_ursina.py` (new): Madden-cam 3D viewer, arc trail dots, HUD, playback controls. `ursina` installed in .venv + requirements.txt. **Not yet visually verified** (background session) — code/import checked only.

### Tests — all passing
- `tests/test_ball3d.py` (new): arc math, ranges, parabola integration, trajectory queries, clamps.
- `tests/test_e2e.py` updated: new pass2 mock format, asserts parabolic z + THROW arc in replay.
- A4 full-pipeline mock (QB picks touch @ z=2.6 → flight peaks 6.5 → arrives 2.6) verified.
- Live GPT-5-nano slant: ran clean end-to-end, 0 parse errors.

## What's Open / Known Issues
1. **Round 14 (full 10-route 3D suite) NOT yet run** — only the slant smoke test.
2. Smoke test signals: QB picked **loft on a quick slant** (2.4s hang → CB closed to 2.0 yd → INCOMPLETE, ball 1.4 yd off). WR called at t=1.8 on stem heading (Window A timing bug carried over from 2D). Arc-choice quality is the new QB frontier.
3. Ursina viewer needs a human eyeball: `python -m render.renderer_ursina replays/slant_42.json`.
4. Jump action (WR/CB vertical timing decision) deliberately deferred — design as follow-up once 3D baseline is stable.
5. `gen_demo.py` still emits legacy `ball_speed_mph` format (unused in main path).
6. Carried from 2D: cb_pre_snap 5yd hardcode, bearing-vs-heading 1-step confusion, post_corner Window A.

## NEXT STEP
Run Round 14: `python run_all_routes.py --seed 42` (GPT-5-nano, all 10 routes) — first full 3D baseline. Read arc choices + target_z usage in QB reasoning, lane-contest events, and how the 3× longer flight times shift outcomes before touching any prompts.
