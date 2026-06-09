"""
Unit tests for 3D arc physics in engine/ball.py.
Run: python tests/test_ball3d.py
"""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from engine.ball import (
    BallState, throw_ball, advance_ball, solve_arc, max_ball_speed, max_range,
    ball_z_at_xy, ARC_ANGLES, RELEASE_Z, DEFAULT_TARGET_Z, G,
)

# ── solve_arc: flight time grows with launch angle ────────────────────────────
times = {}
for arc in ARC_ANGLES:
    sol = solve_arc(30.0, arc)
    assert sol is not None, f"{arc} unsolvable at 30 yd"
    t_f, speed, peak = sol
    times[arc] = t_f
    assert peak >= RELEASE_Z - 0.01, f"{arc} peak below release"
assert times["bullet"] < times["drive"] < times["touch"] < times["loft"], times

# Bullet at 30 yd should be realistic (~1.2-1.4s, not 0.4s like the old 2D bug)
assert 1.0 < times["bullet"] < 1.6, f"bullet 30yd flight time unrealistic: {times['bullet']:.2f}"
assert 2.0 < times["loft"] < 3.0, f"loft 30yd flight time unrealistic: {times['loft']:.2f}"

# ── throw_power range limits ──────────────────────────────────────────────────
v85 = max_ball_speed(85.0)
assert 25.0 < v85 < 28.0, v85
# Bullet should run out of range before loft does
assert max_range("bullet", v85) < max_range("loft", v85)
assert 55.0 < max_range("loft", v85) < 75.0, max_range("loft", v85)

# A 30-yd bullet is feasible at power 85; a 50-yd bullet is not
ball = BallState(x=26.0, y=50.0, holder_id="QB")
ok = throw_ball(ball, 26.0, 50.0, 26.0, 80.0, "bullet", 85.0)
assert ok is not None and ok.state == "in_air"
too_far = throw_ball(ball, 26.0, 50.0, 26.0, 100.0, "bullet", 85.0)
assert too_far is None, "50-yd bullet should exceed power-85 arm"
loft_far = throw_ball(ball, 26.0, 50.0, 26.0, 100.0, "loft", 85.0)
assert loft_far is not None, "50-yd loft should be feasible at power 85"

# ── Flight integration: z rises, peaks, returns to target_z at eta ────────────
b = throw_ball(ball, 26.0, 50.0, 26.0, 75.0, "touch", 85.0, target_z=1.5)
assert b is not None
zs = [b.z]
while b.eta > 0:
    b = advance_ball(b, 0.1)
    zs.append(b.z)
peak_z = max(zs)
assert peak_z > RELEASE_Z + 1.0, f"touch arc never rose: peak={peak_z:.2f}"
assert zs[0] == RELEASE_Z
# z at landing ≈ target_z (within one timestep of error)
assert abs(zs[-1] - 1.5) < 0.8, f"landing z off target: {zs[-1]:.2f}"
# horizontal position ≈ target
assert math.hypot(b.x - 26.0, b.y - 75.0) < 0.5, (b.x, b.y)

# ── ball_z_at_xy: midpoint of flight is near peak, ends near target_z ─────────
b2 = throw_ball(ball, 26.0, 50.0, 26.0, 80.0, "loft", 85.0, target_z=1.5)
z_mid = ball_z_at_xy(b2, 26.0, 65.0)
z_end = ball_z_at_xy(b2, 26.0, 80.0)
assert z_mid is not None and z_end is not None
assert z_mid > z_end, f"mid-flight z {z_mid:.1f} should exceed arrival z {z_end:.1f}"
assert abs(z_end - 1.5) < 0.3, f"arrival z from trajectory query off: {z_end:.2f}"
# A 30-yd loft sails far above a defender's 3.0 reach at midfield
assert z_mid > 3.0, f"loft midpoint should clear vertical reach: {z_mid:.2f}"
# A bullet stays much flatter
b3 = throw_ball(ball, 26.0, 50.0, 26.0, 80.0, "bullet", 85.0, target_z=1.5)
z_mid_bullet = ball_z_at_xy(b3, 26.0, 65.0)
assert z_mid_bullet < z_mid, "bullet should fly flatter than loft"

# ── target_z is clamped ────────────────────────────────────────────────────────
b4 = throw_ball(ball, 26.0, 50.0, 26.0, 70.0, "touch", 85.0, target_z=9.0)
assert b4 is not None and b4.landing_z <= 3.0, b4.landing_z

print("--- PASS --- all 3D ball physics checks")
print(f"30yd flight times: " + "  ".join(f"{a}={t:.2f}s" for a, t in times.items()))
print(f"power-85 ranges: bullet={max_range('bullet', v85):.0f}yd  loft={max_range('loft', v85):.0f}yd")
