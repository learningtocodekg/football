"""
Run this to see exactly what the WR agent reads at two points in a slant play.

    python show_wr_obs.py

SNAPSHOT A = t=1.0s, WR on upfield stem, CB trailing far behind
SNAPSHOT B = t=2.1s, WR just snapped the slant break, both players in cut recovery
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from engine.physics import PlayerState, PlayerAttrs
from engine.ball import BallState
from agents.observation import build_wr_observation

# ── Attrs ────────────────────────────────────────────────────────────────────
wr_attrs = PlayerAttrs(
    name="WR", max_speed=8.5, acceleration=14.0, agility=80.0,
    catch=85.0, catch_in_traffic=75.0, route_running=85.0,
)
qb = PlayerState(x=26.65, y=-5.0)

# ── Route config (slant) ──────────────────────────────────────────────────────
route         = "slant"
cut_time      = 1.0
cut_heading   = 45.0    # diagonal upfield-right, slant inside
route_phases  = [(1.0, 0.0), (999, 45.0)]   # phase1=stem, phase2=break
route_desc = {
    "description": (
        "The upfield stem pushes the CB into a backward lean. When you cut inside, "
        "the CB must reverse his momentum — that reversal is your window. "
        "Accelerate hard through the cut."
    ),
}

# ── Shared history (10 steps of stem) ────────────────────────────────────────
stem_history = [
    dict(t=0.0, wr=(26.65, 0.0),  wr_hdg=0.0, wr_spd=0.0, wr_cut_rec=0, cb=(29.5, 5.0),  cb_hdg=180.0, cb_spd=3.0, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.1, wr=(26.65, 0.3),  wr_hdg=0.0, wr_spd=3.0, wr_cut_rec=0, cb=(29.5, 4.7),  cb_hdg=180.0, cb_spd=3.0, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.2, wr=(26.65, 0.7),  wr_hdg=0.0, wr_spd=5.5, wr_cut_rec=0, cb=(29.5, 4.4),  cb_hdg=180.0, cb_spd=3.2, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.3, wr=(26.65, 1.2),  wr_hdg=0.0, wr_spd=7.0, wr_cut_rec=0, cb=(29.4, 4.0),  cb_hdg=180.0, cb_spd=3.5, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.4, wr=(26.65, 1.9),  wr_hdg=0.0, wr_spd=8.0, wr_cut_rec=0, cb=(29.3, 3.6),  cb_hdg=180.0, cb_spd=3.8, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.5, wr=(26.65, 2.7),  wr_hdg=0.0, wr_spd=8.5, wr_cut_rec=0, cb=(29.2, 3.2),  cb_hdg=180.0, cb_spd=4.0, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.6, wr=(26.65, 3.5),  wr_hdg=0.0, wr_spd=8.5, wr_cut_rec=0, cb=(29.0, 2.8),  cb_hdg=180.0, cb_spd=4.1, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.7, wr=(26.65, 4.4),  wr_hdg=0.0, wr_spd=8.5, wr_cut_rec=0, cb=(28.8, 2.4),  cb_hdg=180.0, cb_spd=4.2, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.8, wr=(26.65, 5.2),  wr_hdg=0.0, wr_spd=8.5, wr_cut_rec=0, cb=(28.6, 2.0),  cb_hdg=180.0, cb_spd=4.3, cb_cut_rec=0, cb_mode="backpedal"),
    dict(t=0.9, wr=(26.65, 6.1),  wr_hdg=0.0, wr_spd=8.5, wr_cut_rec=0, cb=(28.5, 1.6),  cb_hdg=175.0, cb_spd=4.5, cb_cut_rec=0, cb_mode="normal"),
]

# ─────────────────────────────────────────────────────────────────────────────
# SNAPSHOT A  t=1.0s — WR on stem at top speed, CB trailing far behind/right
# ─────────────────────────────────────────────────────────────────────────────
wr_a  = PlayerState(x=26.65, y=7.0,  speed=8.5, heading=0.0,   facing=0.0,   cut_recovery=0)
cb_a  = PlayerState(x=28.5,  y=1.2,  speed=4.6, heading=175.0, facing=175.0, cut_recovery=0)
ball_a = BallState(x=26.65, y=-5.0, state="held")

obs_a = build_wr_observation(
    t=1.0, wr=wr_a, wr_attrs=wr_attrs, cb=cb_a, qb=qb, ball=ball_a,
    route=route, cut_time=cut_time, cut_heading=cut_heading,
    wr_called_for_ball=False, call_t=None, broken_play=False,
    wr_history=stem_history, ball_total_eta=None, detected_cut_t=None,
    route_phases=route_phases, call_heading=None,
    wr_note="deception: not needed yet (t=1.0, stem phase) | running 0deg | CB trailing far behind, hold stem until ~t=1.0 then break",
    route_description=route_desc,
    pre_snap_plan="CB is 5yd off, outside shade, backpedaling. Stem pushes him deeper. Break inside at ~t=1.0 should open the slant.",
    wr_start=(26.65, 0.0),
)

# ─────────────────────────────────────────────────────────────────────────────
# SNAPSHOT B  t=2.1s — WR just snapped break to 135°; CB also cut → both rec=3
# ─────────────────────────────────────────────────────────────────────────────
break_history = stem_history + [
    dict(t=1.0, wr=(26.65, 7.0),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(28.5, 1.2),  cb_hdg=175.0, cb_spd=4.6, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.1, wr=(26.65, 7.9),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(28.4, 0.8),  cb_hdg=170.0, cb_spd=4.8, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.2, wr=(26.65, 8.7),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(28.3, 0.3),  cb_hdg=165.0, cb_spd=5.0, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.3, wr=(26.65, 9.6),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(28.1,-0.2),  cb_hdg=160.0, cb_spd=5.2, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.4, wr=(26.65,10.4),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(27.9,-0.7),  cb_hdg=155.0, cb_spd=5.5, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.5, wr=(26.65,11.3),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(27.6,-1.2),  cb_hdg=150.0, cb_spd=5.8, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.6, wr=(26.65,12.1),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(27.3,-1.7),  cb_hdg=145.0, cb_spd=6.0, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.7, wr=(26.65,13.0),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(26.9,-2.2),  cb_hdg=140.0, cb_spd=6.2, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.8, wr=(26.65,13.8),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(26.5,-2.7),  cb_hdg=135.0, cb_spd=6.3, cb_cut_rec=0, cb_mode="normal"),
    dict(t=1.9, wr=(26.65,14.7),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(26.1,-3.2),  cb_hdg=130.0, cb_spd=6.4, cb_cut_rec=0, cb_mode="normal"),
    dict(t=2.0, wr=(26.65,15.5),  wr_hdg=0.0,   wr_spd=8.5, wr_cut_rec=0, cb=(25.8,-3.7),  cb_hdg=125.0, cb_spd=6.4, cb_cut_rec=0, cb_mode="normal"),
    # WR snaps break at t=2.0 -> both players now in rec=3
    dict(t=2.1, wr=(27.1, 15.9),  wr_hdg=135.0, wr_spd=6.0, wr_cut_rec=3, cb=(26.4,-3.5),  cb_hdg=135.0, cb_spd=6.0, cb_cut_rec=3, cb_mode="normal"),
]

wr_b  = PlayerState(x=27.1, y=15.9, speed=6.0, heading=135.0, facing=135.0, cut_recovery=3)
cb_b  = PlayerState(x=26.4, y=-3.5, speed=6.0, heading=135.0, facing=135.0, cut_recovery=3)
ball_b = BallState(x=26.65, y=-5.0, state="held")

obs_b = build_wr_observation(
    t=2.1, wr=wr_b, wr_attrs=wr_attrs, cb=cb_b, qb=qb, ball=ball_b,
    route=route, cut_time=cut_time, cut_heading=cut_heading,
    wr_called_for_ball=False, call_t=None, broken_play=False,
    wr_history=break_history, ball_total_eta=None, detected_cut_t=2.0,
    route_phases=route_phases, call_heading=None,
    wr_note="deception: done at t=2.0 (CB rec=3 after my cut) | on final break 135deg | calling NOW — gap peaks in ~0.2s",
    route_description=route_desc,
    pre_snap_plan="CB is 5yd off, outside shade, backpedaling. Stem pushes him deeper. Break inside at ~t=2.0 should open the slant.",
    wr_start=(26.65, 0.0),
)

SEP = "\n" + "="*80 + "\n"
print(SEP)
print("SNAPSHOT A  (t=1.0s -- WR on upfield stem, CB trailing far behind/right)")
print(SEP)
print(obs_a)
print(SEP)
print("SNAPSHOT B  (t=2.1s -- WR just snapped break to 135deg, both players rec=3)")
print(SEP)
print(obs_b)
