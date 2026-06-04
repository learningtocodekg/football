# Future: 3D Viewer (Ursina) + Ball Arc Physics

## Context
The sim has a 2D Pygame top-down replay viewer and a ball that travels in a straight flat line with no Z-axis. We want:
1. Real arc physics on the ball (Z-axis, parabolic flight)
2. A 3D Ursina viewer (Madden cam, fixed) to visually verify throw arc, player movement, and coverage
3. The QB agent gets two new controls: `target_coord [x, y, z]` (3D landing spot) and `arc` ("bullet" or "loft")

---

## QB Agent Interface

### What the QB outputs (new format)
```json
{"action": "throw", "target_coord": [x, y, z], "arc": "bullet", "reasoning": "..."}
```

- `target_coord`: 3D landing spot. `z` is the height at catch point — e.g., `z=2.0` for a low catch, `z=5.0` for a high back-shoulder. This lets the QB place the ball over a CB or low and away.
- `arc`: `"bullet"` or `"loft"`. This is the QB's intent for flight style:
  - **bullet** — flat trajectory, arrives fast, less hang time
  - **loft** — high arc, arrives slower, floats over shorter defenders

### How arc + throw_power → flight time

We define two arc profiles. These constants are tunable:
```
BULLET_PEAK_RATIO = 0.15   # peak height = 15% of horizontal distance
LOFT_PEAK_RATIO   = 0.40   # peak height = 40% of horizontal distance
```

Given `dist_xy` (horizontal distance QB → target `[x, y]`):
```
peak_height = ratio * dist_xy   # e.g., 30yd throw: bullet=4.5yd, loft=12yd

# kinematics: peak at t_flight/2
# h = 0.5 * g * (t_flight/2)²  →  t_flight = 2 * sqrt(2*h/g)
g = 9.8 yd/s²
t_flight = 2 * sqrt(2 * peak_height / g)

# horizontal speed
speed_xy = dist_xy / t_flight
```

Loft always takes longer than bullet for the same distance — this is a strategic tradeoff the QB understands.

### Throw power caps max distance

| throw_power | max distance (bullet) | max distance (loft) |
|---|---|---|
| 99 | ~70 yards | ~70 yards |
| 60 | ~25 yards | ~40 yards |

Implementation: `max_speed_xy` is derived from `throw_power`:
```
MAX_SPEED_XY = 20 + (throw_power / 99) * 30   # yd/s, range ~20–50
```
If computed `speed_xy > MAX_SPEED_XY`, the throw is physically impossible — runner rejects it (treat as "hold" + log warning). The observation tells the QB their max range.

**Why loft gives more range at low throw_power:** loft has higher `t_flight`, so the required `speed_xy` is lower for the same distance. A weak-armed QB can loft further than they can bullet.

### Z on target_coord
`z` is the intended catch height. It affects:
- The ball's actual peak height (the arc is computed from QB release at `z≈2yd` to landing at target `z`)
- Visually: a ball thrown to `z=5.0` arrives chest-high; `z=1.0` arrives low

For physics: the arc is computed as a parabola from `(qb.x, qb.y, 2.0)` to `(tx, ty, tz)`. The peak height is determined by `arc` type + `dist_xy`, not the endpoint z — the endpoint z just shifts the whole parabola vertically.

---

## Physics: `engine/ball.py`

Add to `BallState`:
```python
z: float = 0.0
vz: float = 0.0
elapsed: float = 0.0
```

`throw_ball(qb_state, target_x, target_y, target_z, arc_type, qb_attrs)`:
1. Compute `dist_xy = hypot(target_x - qb.x, target_y - qb.y)`
2. Pick ratio from `arc_type`: bullet=0.15, loft=0.40
3. `peak_height = ratio * dist_xy`
4. `t_flight = 2 * sqrt(2 * peak_height / 9.8)`
5. `speed_xy = dist_xy / t_flight`
6. Validate against `max_speed_xy(qb_attrs.throw_power)` — return error signal if impossible
7. `vx = (target_x - qb.x) / t_flight`; `vy = (target_y - qb.y) / t_flight`
8. `vz`: solve parabola from `z_start=2.0` to `target_z` in time `t_flight`:
   - `vz = (target_z - z_start + 0.5*g*t_flight²) / t_flight`
9. Set `ball.state = "in_air"`, `ball.elapsed = 0`, `ball.eta = t_flight`

`advance_ball(ball, dt)`:
```python
ball.elapsed += dt
ball.z = max(0.0, z_start + ball.vz * ball.elapsed - 0.5 * g * ball.elapsed**2)
ball.x += ball.vx * dt
ball.y += ball.vy * dt
ball.eta -= dt
```

---

## Files to Change

### `engine/ball.py`
- Add `z`, `vz`, `elapsed` to `BallState`
- Rewrite `throw_ball()` as above
- Update `advance_ball()` to integrate Z

### `agents/observation.py`
- Update throw options table: show `arc=bullet` and `arc=loft` options side-by-side for each horizon T, with their flight times and implied max range
- Show QB's max range for bullet and loft given their `throw_power`
- Action format hint updated

### `agents/schema.py`
- `parse_qb_action()`: accept `target_coord` as `[x, y, z]` (len==3), `arc` field ("bullet"/"loft")
- Remove `ball_speed_mph` from throw validation

### `agents/prompts/qb_system.txt`
- Update field description: `target_coord [x, y, z]` — z is catch height (1=low, 5=high)
- Explain `arc`: bullet arrives fast (less CB time to close), loft hangs (can float over shorter defenders, more flight time)
- Explain throw power range limits
- Update JSON example

### `sim/runner.py`
- Pass `target_z` and `arc_type` from QB action into `throw_ball()`
- Handle impossible throw (speed_xy over cap) → log, treat as hold

### `replay/recorder.py`
- Ball snapshot: `"pos": [ball.x, ball.y, ball.z]`
- Add `"arc": arc_type` to THROW event

### `render/renderer_pygame.py`
- Update `draw_ball()` to draw parabolic arc (sample ~10 points along trajectory) instead of straight line to landing spot
- Otherwise no changes — just ignores z for 2D position

### `render/renderer_ursina.py` *(new file)*
**Field:**
- Flat `Entity` plane 53.3 × 120, green
- Thin white box entities for yard lines every 10 yards

**Players (rectangle + arms):**
- Body: `Entity(model='cube', scale=(1, 2, 0.5), color=...)`
- Arms: `Entity(model='cube', scale=(2, 0.3, 0.3), color=...)` parented to body
- QB/WR: blue. CB: red.
- Position: `Vec3(player.x, 0, player.y)` (Ursina Y-up; field Y → Ursina Z)
- Rotation from heading → Ursina Y-axis rotation

**Ball:**
- `Entity(model='sphere', scale=0.4, color=color.brown)`
- Position: `Vec3(ball.x, ball.z, ball.y)` — ball's Z height → Ursina Y

**Camera (Madden cam, fixed):**
```python
camera.position = Vec3(26.65, 12, 30)
camera.look_at(Vec3(26.65, 0, 70))
```
Tune after first run.

**Playback (`update()` hook):**
- Timer advances frame index at 10 fps (sim rate)
- Reads `steps[frame_idx]`, updates all entity positions/rotations
- HUD: `Text` showing `t=`, phase, arc type on last throw

**Controls (`input()` hook):**
- `space`: play/pause
- `right` / `left`: step ±1 frame
- `q` / `escape`: quit

**Invocation:**
```
python -m render.renderer_ursina replays/play_42.json
```

### `requirements.txt`
- Add `ursina`

---

## Verification

1. `pip install ursina`
2. `python main.py --scenario sim/scenarios/a1_basic.yaml --output replays/play_42.json`
3. Check JSON: `ball.pos` has 3 values, z peaks mid-flight, returns near target_z at landing
4. `python -m render.renderer_ursina replays/play_42.json`
   - Ball visibly rises and falls in arc
   - Loft throws hang longer than bullet throws of same distance
   - QB, WR, CB are colored rectangles with arms
   - Camera shows full field from behind offense
5. Sanity check: QB with `throw_power=85` should be able to bullet ~60yd and loft ~70yd
