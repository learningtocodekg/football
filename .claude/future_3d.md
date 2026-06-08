# Future: 3D Viewer (Ursina) + Ball Arc Physics

## Change Log — What Has Changed Since This Plan Was Written

This document was first written when the codebase was significantly simpler. Since then:

- **Physics overhaul**: `engine/physics.py` now has full dynamic burst mechanics (`PlayerState.cut_recovery`, `PlayerAttrs.agility`), speed-scaled acceleration, hip-turn recovery penalties, and backpedal mode. None of this existed in the original plan.
- **State machine**: `engine/state_machine.py` defines `PlayPhase` enum with four named phases: `PRE_SNAP`, `LIVE`, `BALL_IN_AIR`, `RESOLUTION`, `END`.
- **Agent architecture expanded**: There are now six WR prompt files (pre_snap, live_free, live_committed, live_broken, ball_in_air), four CB prompt files (system, pre_snap, pass1, pass2), and a two-pass QB architecture. `WRAgent` and `CBAgent` have full `apply_decision()` methods using the physics engine.
- **WR note scratchpad**: `WRAgent.wr_note` is a persistent per-step scratchpad string injected back into observations.
- **Simulation modes A2/A3/A4**: `runner.py` supports scripted WR + LLM CB (A2), LLM WR + LLM QB no-CB (A3), and full LLM WR + LLM QB + LLM CB (A4). Scenarios are YAML files in `sim/scenarios/`.
- **Replay JSON structure**: `{"header": {...}, "steps": [...], "footer": {...}}`. Each step has `t`, `phase`, `sack_clock`, `players`, `ball`, `events`. Players have `id`, `pos`, `heading`, `facing`, `speed`, `cut_recovery`, `mode`, `action`, `reasoning`. Ball has `state`, `pos`, `landing`, `eta`, `holder` depending on state.
- **QB two-pass architecture**: pass1 produces `hold` or `thinking` with `target_area [x,y]`. Pass2 selects from a pre-computed options table (bullet/hard/medium/soft/lob) by label. Ball speed is chosen via option label, not a raw MPH value.
- **Observation injection**: `agents/observation.py` computes and injects substantial scaffolding — separation distances, bearing to WR, projected WR position, burst/recovery status, CB fuzz zone for ball in air, sideline warnings, move history table with `cut_recovery` columns.
- **Ball state**: `BallState` has `x`, `y`, `state`, `vx`, `vy`, `landing_x`, `landing_y`, `speed_yd_s`, `elapsed`, `eta`, `holder_id`. No Z axis yet — this is the 2D baseline.
- **LLM providers**: `llm_client.py` supports OpenAI (with `response_format=json_object`) and Ollama (temperature-based, no JSON mode enforcement). Scenarios configure `*_provider`, `*_model`, `*_reasoning_effort`.
- **Renderer**: `render/renderer_pygame.py` (class `GridironRenderer`) draws ball arc as a straight line to landing spot (not parabolic). Reads `steps[i]["players"]` and `steps[i]["ball"]` from the JSON.

---

## Context

The sim has a 2D Pygame top-down replay viewer (`render/renderer_pygame.py`) and a ball that travels in a straight flat line with no Z-axis. We want:

1. Real arc physics on the ball (Z-axis, parabolic flight)
2. A 3D Ursina viewer (Madden cam, fixed) to visually verify throw arc, player movement, and coverage
3. The QB agent gets a richer throw interface: explicit arc type and computed flight time become first-class observables

---

## Problems Naturally Solved by 3D

After reading `problems.md`, three open issues will be resolved as a direct consequence of building the 3D infrastructure — we get the fix for free.

### N3 (WR facing hallucination during ball flight) — PARTIALLY SOLVED BY 3D

The WR consistently miscalculates the QB bearing. A partial 2D fix has already been applied (injecting the explicit computed QB bearing as "FACING INSTRUCTION: Set facing=X exactly"). The 3D transition reinforces this by making ball arc and trajectory an explicit geometric object, encouraging precise bearing injection throughout the observation.

### Q3 / N6 (QB lead calc / one-step delay) — SOLVED BY 3D

Arc physics introduces explicit `t_flight` derived from the arc equation. In 3D, `t_flight` is a first-class field computed by `throw_ball()` based on arc type and distance — no longer inferred from `ball_speed_mph / dist`. This value appears directly in the QB options table, making the "where will WR be when ball arrives" computation transparent. The existing recovery-aware WR projection in `qb_agent._build_options()` uses `eta` — with 3D, this eta is physically derived.

### Q2 (QB throw geometry errors) — PARTIALLY SOLVED BY 3D

The 3D interface removes `ball_speed_mph` as a direct output. The QB picks from an options table keyed by arc type (`bullet` or `loft`) × speed tier. The options table shows CB context relative to each option, which catches throw-lane errors before they occur.

---

## Problems NOT Solved by 3D — Must Fix First

The following bugs are pure 2D prompt/observation problems that will be inherited by any 3D transition. See "Pre-3D Requirements" section for fix details:

- **N2** (WR wrong route shape) — geometry injection problem
- **N1/S6** (parse errors with qwen3:8b) — JSON enforcement ← **already applied Round 9**
- **N3** (WR facing hallucination) ← **already partially fixed Round 9**
- **N4** (WR phantom CB-commit trigger) — observation signal design
- **N5** (WR no escalation counter) ← **already applied Round 9** (steps_on_this_heading injected)
- **N7/N8** (CB over-commit, CB geometric hallucinations) — CB prompt
- **W1/W2/W3** (WR call timing, heading after call, route execution) — WR prompt
- **Q4** (QB hold-phase boilerplate) — QB prompt

---

## QB Agent Interface

### What the QB outputs (new format)

The QB's current two-pass architecture stays. Pass1 produces a `target_area [x, y]` candidate. Pass2 selects from the options table by label.

**Current (2D):** Options by speed tier: bullet, hard, medium, soft, lob (fractions of max_mph). Each option shows `eta`, `wr_at_arrival`, `wr_offset`.

**3D extension:** Options become `(arc_type, speed_tier)` pairs: `bullet_fast`, `bullet_medium`, `loft_fast`, `loft_medium`, `loft_slow`. Each option shows `arc`, `t_flight`, `wr_at_arrival`, `wr_offset`.

Pass2 throw output:
```json
{"action": "throw", "option": "loft_medium", "reasoning": "..."}
```

`target_coord` and `ball_speed_mph` are computed from the selected option, not output by the QB directly. `parse_qb_pass2()` in `agents/schema.py` resolves the option label to `(target_coord, arc, t_flight)`.

### How arc + throw_power → flight time

Two arc profiles (tunable constants):
```
BULLET_PEAK_RATIO = 0.15   # peak height = 15% of horizontal distance
LOFT_PEAK_RATIO   = 0.40   # peak height = 40% of horizontal distance
```

Given `dist_xy` (horizontal distance QB to target [x, y]):
```
peak_height = ratio * dist_xy
t_flight = 2 * sqrt(2 * peak_height / 9.8)
speed_xy = dist_xy / t_flight
```

For a 30-yard throw:
- Bullet: peak 4.5 yd → t_flight ≈ 1.91s
- Loft: peak 12 yd → t_flight ≈ 3.12s

### Throw power caps max distance

```
MAX_SPEED_XY = 20 + (throw_power / 99) * 30   # yd/s, range ~20-50
```

If `speed_xy > MAX_SPEED_XY`, throw is impossible — engine rejects it (hold + log warning). Loft gives more range at low throw_power because higher `t_flight` lowers required `speed_xy` for the same distance.

### Z on target_coord

`z` is the intended catch height. It affects:
- The ball's actual peak height (arc computed as parabola from QB release at `z=2yd` to landing at target `z`)
- Visually: `z=5.0` arrives chest-high; `z=1.0` arrives low

For physics: parabola from `(qb.x, qb.y, 2.0)` to `(tx, ty, tz)`. Peak determined by arc type + `dist_xy`. Default catch height `z=2.0`; `z=4.5` for a back-shoulder throw over a CB.

---

## Physics: `engine/ball.py`

### Current BallState (actual fields as of Round 8):
```python
@dataclass
class BallState:
    x: float
    y: float
    state: str = "held"    # "held" | "in_air" | "dead"
    vx: float = 0.0
    vy: float = 0.0
    landing_x: float = 0.0
    landing_y: float = 0.0
    speed_yd_s: float = 0.0
    elapsed: float = 0.0
    eta: float = 0.0
    holder_id: str = "QB"
```

### 3D additions to BallState:
```python
z: float = 0.0        # current height (yards above ground)
vz: float = 0.0       # vertical velocity (yd/s)
arc: str = "bullet"   # arc type for this throw
```

### New throw_ball() signature:
```python
def throw_ball(
    ball: BallState,
    qb_x: float, qb_y: float,
    target_x: float, target_y: float, target_z: float,
    arc_type: str,           # "bullet" | "loft"
    throw_power: float,      # 0-99, from PlayerAttrs.throw_power
) -> BallState:
```

Implementation:
1. `dist_xy = hypot(target_x - qb_x, target_y - qb_y)`
2. `ratio = BULLET_PEAK_RATIO if arc_type == "bullet" else LOFT_PEAK_RATIO`
3. `peak_height = ratio * dist_xy`
4. `t_flight = 2 * sqrt(2 * peak_height / 9.8)`
5. `speed_xy = dist_xy / t_flight`
6. Validate: `max_speed_xy = 20 + (throw_power / 99) * 30` — if `speed_xy > max_speed_xy`, return error signal
7. `vx = (target_x - qb_x) / t_flight`, `vy = (target_y - qb_y) / t_flight`
8. `z_start = 2.0`; `vz = (target_z - z_start + 0.5 * 9.8 * t_flight**2) / t_flight`
9. Set `state="in_air"`, `elapsed=0.0`, `eta=t_flight`, `arc=arc_type`

### Updated advance_ball():
```python
def advance_ball(ball: BallState, dt: float = 0.1) -> BallState:
    if ball.state != "in_air":
        return ball
    Z_START = 2.0
    G = 9.8
    new_elapsed = ball.elapsed + dt
    new_z = max(0.0, Z_START + ball.vz * new_elapsed - 0.5 * G * new_elapsed**2)
    return BallState(
        x=ball.x + ball.vx * dt,
        y=ball.y + ball.vy * dt,
        z=new_z,
        state=ball.state,
        vx=ball.vx, vy=ball.vy, vz=ball.vz,
        landing_x=ball.landing_x, landing_y=ball.landing_y,
        speed_yd_s=ball.speed_yd_s,
        elapsed=new_elapsed,
        eta=max(0.0, ball.eta - dt),
        arc=ball.arc,
        holder_id=ball.holder_id,
    )
```

---

## Files to Change

### `engine/ball.py`
- Add `z`, `vz`, `arc` to `BallState`
- Add arc constants: `BULLET_PEAK_RATIO`, `LOFT_PEAK_RATIO`, `G`, `Z_START`, `MAX_SPEED_XY_BASE`
- Rewrite `throw_ball()` — new signature, arc physics, impossible-throw error return
- Update `advance_ball()` to integrate Z

### `engine/resolution.py`
- No structural change needed. `resolve()` works off final `landing_x`, `landing_y` (still 2D).
- Optional future: use `ball.z` at landing for a catch-height modifier.

### `agents/schema.py`
- `parse_qb_pass2()`: option labels change to `(arc_type, speed_tier)` format — e.g., `"bullet_fast"`, `"loft_medium"`. Return includes `arc` and `t_flight`.
- Remove `ball_speed_mph` from throw resolution path (now derived from `t_flight` and `dist_xy`).

### `agents/qb_agent.py`
- `_build_options()`: replace `OPTION_SPEEDS` (mph-fraction) list with arc x speed-tier combos. Each option shows `arc`, `t_flight`, `wr_at_arrival`. Recovery-aware projection logic stays.
- Options text block updates to show `arc=bullet|loft` and `t_flight`.
- `decide()`: resolve selected option label to `arc`, call arc-based `throw_ball()` with `target_z=2.0`.

### `agents/observation.py`
- `build_qb_observation()`: replace ball travel time section with arc options table showing `t_flight` for bullet and loft at current WR distance. Add QB max range per arc given `throw_power`.
- `build_wr_observation()` during `BALL_IN_AIR`: ← **already updated Round 9** with explicit bearing injection.

### `agents/prompts/qb_system.txt`
- Add arc types section: bullet (flat, fast, less hang) vs loft (high arc, slower, floats over shorter defenders). Explain throw power range limits per arc. Update throw format example to option-label syntax.

### `agents/prompts/qb_pass1.txt`
- Minor: clarify `target_area [x, y]` is still 2D. Z is handled in pass2 option selection.

### `agents/prompts/qb_pass2.txt`
- Update `{options_block}` description: explain arc type, t_flight per option. "Pick bullet when WR has separation and you want ball there before CB closes. Pick loft when CB is in the throw lane or WR needs more time."

### `agents/prompts/wr_ball_in_air.txt`
- Reinforce the explicit facing instruction: "The observation gives you the exact QB bearing in degrees. Set facing= to that number. Do NOT estimate it. Use the number from FACING INSTRUCTION in the observation."

### `sim/runner.py`
- `throw_ball()` call: pass `arc_type` from QB action and `target_z=2.0`.
- Handle impossible throw signal → log + treat as hold.
- Add `arc` field to `THROW` event.
- `_ball_snap()`: include `ball.z` in pos array: `"pos": [round(ball.x, 2), round(ball.y, 2), round(ball.z, 2)]`.

### `replay/recorder.py`
- No structural change. Ball snapshot uses whatever `_ball_snap()` returns. `THROW` event gains an `arc` field.

### `render/renderer_pygame.py` (class `GridironRenderer`)
- `draw_ball()`: handle both 2-element (legacy replays) and 3-element pos. Use only `pos[0]` and `pos[1]` for screen position.
- Optionally show ball height as a number near the ball dot when in air.

### `render/renderer_ursina.py` (new file)

**Coordinate mapping:**
- Field `x` → Ursina `x`
- Field `y` → Ursina `z`
- Ball `z` (height) → Ursina `y`
- Player position: `Vec3(player["pos"][0], 0, player["pos"][1])`
- Ball position: `Vec3(ball["pos"][0], ball["pos"][2] if len(ball["pos"])>2 else 0, ball["pos"][1])`

**Field:**
- Flat `Entity` plane scaled to `53.3 x 120`, green
- Box entities for yard lines every 10 yards (white), every 5 yards (gray)
- Hash marks at `x=18.5` and `x=34.8`

**Players:**
- Body: `Entity(model='cube', scale=(1, 2, 0.5), color=color.blue)` for QB/WR, `color.red` for CB
- Heading rotation: Ursina Y-axis rotation = `player["heading"]`
- Text label with player id

**Ball:**
- `Entity(model='sphere', scale=0.4, color=color.brown)`
- Arc visualization: small sphere entities at ~10 sampled points along the arc when in air

**Camera (Madden cam, fixed):**
```python
camera.position = Vec3(26.65, 15, 10)
camera.look_at(Vec3(26.65, 0, 65))
```
Camera is behind the offensive end zone looking upfield. Tune after first run.

**Playback (`update()` hook):**
- Timer advances at 10 fps (matching sim DT=0.1)
- Reads `steps[frame_idx]`, updates all entity positions/rotations
- HUD: `Text` showing `t=`, `phase`, `arc` from last THROW event, `sack_clock`

**Controls (`input()` hook):**
- `space`: play/pause
- `right` / `left`: step ±1 frame
- `+` / `-`: speed up / slow down
- `r`: toggle reasoning overlay
- `q` / `escape`: quit

**Invocation:**
```
python -m render.renderer_ursina replays/play.json
```

### `requirements.txt`
- Add `ursina`

---

## Agent Observation Changes for 3D

### `agents/observation.py` — `build_qb_observation()`

Replace the ball travel time section with:
```
Arc options for {dist_to_wr:.1f}yd throw:
  bullet (flat):  t_flight~{bullet_t:.2f}s  max range~{bullet_max_range:.0f}yd
  loft   (high):  t_flight~{loft_t:.2f}s    max range~{loft_max_range:.0f}yd
LEAD HINT: at bullet speed WR will be ~({proj_x:.1f}, {proj_y:.1f}). Throw to projected coord.
```

Where `bullet_t` and `loft_t` are computed from arc physics. `bullet_max_range` and `loft_max_range` from `MAX_SPEED_XY` and arc formula.

**Philosophy:** We inform the QB about physical reality of each arc. The QB decides which arc to use. We never enforce a specific arc choice.

### `agents/observation.py` — `build_wr_observation()` during BALL_IN_AIR

Already updated (Round 9) with:
```
FACING INSTRUCTION: Set facing={bearing_to_qb:.0f} exactly. This is the computed bearing from your position to the QB — the direction the ball is coming from. Do NOT estimate this number; use {bearing_to_qb:.0f} directly.
```

**Philosophy:** We inject a computed value (bearing) as context. The WR still decides whether to face that way. We are providing accurate geometry, not enforcing behavior.

### `agents/prompts/wr_ball_in_air.txt`

Add explicit reinforcement: "The observation gives you the exact QB bearing in degrees under FACING INSTRUCTION. Use that number. Do not compute a different bearing."

---

## Pre-3D Requirements

### Applied in Round 9 (before this document was updated)

- **N1/S6 fix**: JSON enforcement appended to all three system prompts.
- **N3 fix**: Explicit `FACING INSTRUCTION: Set facing=X exactly` injected into WR ball-in-air observation.
- **N5 fix**: `steps_on_this_heading` counter computed from history and injected into WR per-step observation.
- **N2 fix**: `_ROUTE_GEOMETRY` dict added; route shape description injected into WR pre-snap observation.
- **Encoding fix**: `°` replaced with `deg` in all `print()` statements in `sim/runner.py`.

### Still Open (Tier 1 — Critical)

**N4 — WR phantom CB-commit trigger**
WR references "CB rec > 0" as an observable field — it is NOT in WR's observation. Fix: in `wr_live_free.txt`, replace with observable proxies:
- "CB heading changed by >90° from its last position in the move log — CB hips are committed"
- "CB heading in same direction for 3+ consecutive log steps — CB is fully running that way"

**W1 / W2 — WR premature call and wrong heading after call**
Reinforce in `wr_live_free.txt`: "Before outputting call_for_ball=true, verify your heading in this response matches the break direction. If heading != break direction, you have not completed the cut — do not call."

### Still Open (Tier 2 — High)

**N7 — CB over-commits; no route anticipation**
Raise CB confirmation threshold to 3 consecutive steps in `cb_pass1.txt`. Add: "Even after a confirmed cut, maintain 10-20deg of hedge toward the opposite break direction in case of a double-move."

**N8 — CB geometric hallucinations**
Add grounding rule to `cb_pass1.txt`: "Your heading decision must be consistent with the move log. If the move log shows WR x-position unchanged between two steps, the WR did NOT move laterally — do not cite lateral drift."

**Q4 — QB hold-phase boilerplate**
Add to `qb_pass1.txt` hold section: "If you hold, briefly note: current WR-CB separation, whether it is growing or shrinking, and what you are waiting for. Generic 'route developing' is not acceptable reasoning."

### Still Open (Tier 3 — Quality)

**P3 — detected_cut_t fires on jabs**: The 2-step confirmation logic in `runner.py` partially addresses this. Low priority.
**C4 — CB speed locked in backpedal**: Minor. Low priority.

---

## Build Order

1. ~~Fix N1 (parse errors)~~ ✅ Done (Round 9)
2. ~~Fix N3 (facing injection)~~ ✅ Done (Round 9)
3. ~~Fix N2 (route geometry per-step)~~ ✅ Done (Round 9)
4. ~~Fix N5 (escalation counter)~~ ✅ Done (Round 9)
5. Fix N4 / W1 / W2 (WR signal + call discipline) — prompt edits
6. Fix N7 / N8 (CB over-commit + hallucination) — prompt edits
7. Fix Q4 (QB hold reasoning) — prompt edit
8. **3D physics**: extend `BallState`, rewrite `throw_ball()`, update `advance_ball()`
9. **3D QB interface**: update `_build_options()` in `qb_agent.py`, update `parse_qb_pass2()` in `schema.py`
10. **3D observations**: update `build_qb_observation()` for arc context
11. **3D runner**: update `throw_ball()` call site, `_ball_snap()`, THROW event
12. **Pygame compat**: handle 3-element pos gracefully in `draw_ball()`
13. **Ursina viewer**: new file `render/renderer_ursina.py`
14. **Prompt updates**: qb_system.txt, qb_pass2.txt, wr_ball_in_air.txt for arc context
15. Run full 10-route eval with 3D physics to verify separation and arc quality

---

## Verification

1. `pip install ursina`
2. Run: `python main.py --scenario sim/scenarios/a4_wr_slant.yaml --seed 42 --output replays/test_3d.json`
3. Check JSON: `ball["pos"]` has 3 values, z peaks mid-flight, returns near target_z at landing
4. Confirm `THROW` event has `arc` field
5. `python -m render.renderer_pygame replays/test_3d.json` — should still work (backward compat)
6. `python -m render.renderer_ursina replays/test_3d.json`
   - Ball visibly rises and falls in arc
   - Loft throws hang longer than bullet throws of same distance
   - QB, WR, CB are colored box entities (blue offense, red defense)
   - Camera shows full field from behind offense
7. Sanity: QB with `throw_power=85` bullets a 30yd throw → `t_flight ~1.91s`, `speed_xy ~15.7 yd/s` (well under max ~45 yd/s)
