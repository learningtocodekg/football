"""
3D replay viewer for Gridiron Minds (Ursina engine).

Usage:
    python -m render.renderer_ursina replays/play.json

Coordinate mapping (field → Ursina):
    field x (0..53.3, sideline to sideline) → Ursina x
    field y (0..120, upfield)               → Ursina z
    ball z (height)                          → Ursina y

Controls:
    SPACE      play / pause
    ← / →      step backward / forward one frame
    + / -      speed up / slow down
    R          toggle reasoning overlay
    Q / Esc    quit
"""
import json
import math
import sys
from pathlib import Path

from ursina import (
    Ursina, Entity, Text, Vec3, color, camera, application, window,
)

FIELD_W = 53.3
FIELD_L = 120.0

# NOTE: ursina 8.x color.rgb() takes 0-1 floats; rgb32() takes 0-255 ints.
OFFENSE_COLOR = color.rgb32(30, 144, 255)
DEFENSE_COLOR = color.rgb32(220, 50, 50)
BALL_COLOR = color.rgb32(170, 90, 30)
ARC_COLOR = color.rgb32(255, 215, 0)
BACKPEDAL_COLOR = color.rgb32(0, 230, 230)  # body tint while running backwards (mode=backpedal)


class UrsinaReplay:
    def __init__(self, replay_path: str):
        data = json.loads(Path(replay_path).read_text())
        self.steps = data["steps"]
        self.header = data.get("header", {})
        self.footer = data.get("footer", {})
        self.title = Path(replay_path).name

        self.cur = 0
        self.playing = True
        self.fps = 10.0
        self.timer = 0.0
        self.show_reasoning = True

        self._build_field()
        self._build_players()
        self._build_ball()
        self._build_hud()
        self._set_camera()
        self.apply_frame()

    # ── Scene construction ────────────────────────────────────────────────────
    def _build_field(self):
        Entity(model="plane", scale=(FIELD_W, 1, FIELD_L),
               position=Vec3(FIELD_W / 2, 0, FIELD_L / 2),
               color=color.rgb32(34, 139, 34))
        # End zones
        for z0 in (5.0, FIELD_L - 5.0):
            Entity(model="plane", scale=(FIELD_W, 1, 10),
                   position=Vec3(FIELD_W / 2, 0.01, z0),
                   color=color.rgb32(0, 100, 0))
        # Yard lines
        for yd in range(10, 111, 5):
            major = yd % 10 == 0
            Entity(model="cube",
                   scale=(FIELD_W, 0.02, 0.12 if major else 0.06),
                   position=Vec3(FIELD_W / 2, 0.02, yd),
                   color=color.white if major else color.rgb32(160, 160, 160))
        # Hash marks
        for yd in range(10, 111):
            for hx in (18.5, 34.8):
                Entity(model="cube", scale=(0.5, 0.02, 0.08),
                       position=Vec3(hx, 0.02, yd),
                       color=color.rgb32(220, 220, 220))
        # Sidelines
        for sx in (0.0, FIELD_W):
            Entity(model="cube", scale=(0.15, 0.02, FIELD_L),
                   position=Vec3(sx, 0.02, FIELD_L / 2), color=color.white)

    def _build_players(self):
        # Each player is an UNSCALED holder entity (so the billboard label is not
        # distorted by the body cube's non-uniform scale), with the body as a child.
        self.player_entities: dict[str, Entity] = {}
        self.player_labels: dict[str, Text] = {}
        self.player_bodies: dict[str, Entity] = {}
        self.player_team_color: dict[str, object] = {}
        self.player_bp_tags: dict[str, Text] = {}
        for p in self.steps[0]["players"]:
            pid = p["id"]
            clr = OFFENSE_COLOR if pid in ("QB", "WR1") else DEFENSE_COLOR
            holder = Entity(position=Vec3(p["pos"][0], 0.0, p["pos"][1]))
            body = Entity(model="cube", scale=(0.8, 2.0, 0.5), color=clr,
                          parent=holder, y=1.0)
            self.player_entities[pid] = holder
            self.player_bodies[pid] = body
            self.player_team_color[pid] = clr
            label = Text(text=pid, parent=holder, y=2.6, scale=14,
                         billboard=True, origin=(0, 0), color=color.white)
            self.player_labels[pid] = label
            bp_tag = Text(text="BP", parent=holder, y=3.0, scale=16,
                          billboard=True, origin=(0, 0), color=BACKPEDAL_COLOR,
                          enabled=False)
            self.player_bp_tags[pid] = bp_tag

    def _build_ball(self):
        self.ball_entity = Entity(model="sphere", scale=0.45, color=BALL_COLOR,
                                  position=Vec3(26.65, 1.0, 50.0))
        # Pre-allocated arc sample dots, shown only during flight
        self.arc_dots = [
            Entity(model="sphere", scale=0.18, color=ARC_COLOR, enabled=False)
            for _ in range(24)
        ]

    def _build_hud(self):
        self.hud = Text(text="", position=(-0.86, 0.47), scale=0.8, color=color.yellow)
        self.reason_text = Text(text="", position=(-0.86, 0.40), scale=0.65,
                                color=color.rgb32(255, 255, 150))

    def _set_camera(self):
        # Madden cam: behind the QB's snap position, pitched down at the action.
        # (Explicit rotation — camera.look_at proved unreliable here.)
        qb = next((p for p in self.steps[0]["players"] if p["id"] == "QB"), None)
        qx = qb["pos"][0] if qb else FIELD_W / 2
        qy = qb["pos"][1] if qb else 50.0
        cam_h, cam_back, look_ahead = 11.0, 17.0, 20.0
        camera.position = Vec3(qx, cam_h, qy - cam_back)
        pitch = math.degrees(math.atan2(cam_h - 1.0, cam_back + look_ahead))
        camera.rotation = Vec3(pitch, 0, 0)
        camera.fov = 70

    # ── Per-frame state ───────────────────────────────────────────────────────
    def _flight_points(self) -> list[Vec3]:
        """Sampled 3D points of the flight containing/nearest the current frame."""
        end = None
        for i in range(self.cur, -1, -1):
            if self.steps[i]["ball"]["state"] == "in_air":
                end = i
                break
        if end is None:
            return []
        start = end
        while start > 0 and self.steps[start - 1]["ball"]["state"] == "in_air":
            start -= 1
        stop = end
        while stop + 1 < len(self.steps) and self.steps[stop + 1]["ball"]["state"] == "in_air":
            stop += 1
        pts = []
        for s in self.steps[start:stop + 1]:
            bp = s["ball"]["pos"]
            if len(bp) > 2:
                pts.append(Vec3(bp[0], bp[2], bp[1]))
        return pts

    def apply_frame(self):
        step = self.steps[self.cur]
        for p in step["players"]:
            ent = self.player_entities.get(p["id"])
            if ent is None:
                continue
            ent.position = Vec3(p["pos"][0], 0.0, p["pos"][1])
            ent.rotation_y = p.get("heading", 0.0)
            # Backpedal indicator: tint the body cyan + show a floating "BP" tag
            backpedal = p.get("mode") == "backpedal"
            body = self.player_bodies.get(p["id"])
            if body is not None:
                body.color = BACKPEDAL_COLOR if backpedal else self.player_team_color[p["id"]]
            tag = self.player_bp_tags.get(p["id"])
            if tag is not None:
                tag.enabled = backpedal

        ball = step["ball"]
        bp = ball["pos"]
        bz = bp[2] if len(bp) > 2 else 0.0
        if ball["state"] == "in_air":
            self.ball_entity.position = Vec3(bp[0], max(bz, 0.25), bp[1])
        else:
            # sit the ball on its holder (holder origin is at ground level)
            holder = self.player_entities.get(ball.get("holder", "QB"))
            base = holder.position if holder is not None else Vec3(bp[0], 0.0, bp[1])
            self.ball_entity.position = base + Vec3(0.5, 1.2, 0)

        # Arc dots
        pts = self._flight_points()
        for i, dot in enumerate(self.arc_dots):
            if pts and i < len(self.arc_dots):
                idx = int(i * (len(pts) - 1) / max(1, len(self.arc_dots) - 1))
                dot.position = pts[idx]
                dot.enabled = ball["state"] == "in_air"
            else:
                dot.enabled = False

        # HUD
        arc_name = ball.get("arc", "")
        eta = ball.get("eta")
        eta_str = f"  eta={eta:.2f}s" if isinstance(eta, (int, float)) else ""
        outcome = self.footer.get("outcome", "")
        hud = (f"t={step['t']:.1f}s  phase={step['phase']}  "
               f"sack={step['sack_clock']:.1f}s  frame {self.cur + 1}/{len(self.steps)}")
        if arc_name:
            hud += f"  arc={arc_name}  z={bz:.1f}{eta_str}"
        if self.cur == len(self.steps) - 1 and outcome:
            hud += f"   ►► {outcome}"
        self.hud.text = hud

        if self.show_reasoning:
            lines = []
            for p in step["players"]:
                r = (p.get("reasoning") or "").strip()
                # Font lacks non-ASCII glyphs (model reasoning is occasionally non-English)
                r = r.encode("ascii", "ignore").decode()
                if r:
                    lines.append(f"{p['id']}: {r[:90]}")
            self.reason_text.text = "\n".join(lines)
        else:
            self.reason_text.text = ""

    # ── Hooks (wired to Ursina globals in main) ───────────────────────────────
    def update(self, dt: float):
        if not self.playing:
            return
        self.timer += dt
        if self.timer >= 1.0 / self.fps:
            self.timer = 0.0
            if self.cur < len(self.steps) - 1:
                self.cur += 1
                self.apply_frame()

    def input(self, key: str):
        if key in ("q", "escape"):
            application.quit()
        elif key == "space":
            self.playing = not self.playing
        elif key == "right arrow":
            self.cur = min(len(self.steps) - 1, self.cur + 1)
            self.apply_frame()
        elif key == "left arrow":
            self.cur = max(0, self.cur - 1)
            self.apply_frame()
        elif key in ("+", "="):
            self.fps = min(60.0, self.fps + 2.0)
        elif key == "-":
            self.fps = max(1.0, self.fps - 2.0)
        elif key == "r":
            self.show_reasoning = not self.show_reasoning
            self.apply_frame()


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m render.renderer_ursina <replay.json>")
        sys.exit(1)

    app = Ursina(title=f"Gridiron Minds 3D — {Path(sys.argv[1]).name}")
    window.color = color.rgb32(60, 120, 180)  # sky
    for counter in ("fps_counter", "entity_counter", "collider_counter", "cog_button"):
        try:
            getattr(window, counter).enabled = False
        except AttributeError:
            pass
    viewer = UrsinaReplay(sys.argv[1])

    from ursina import time as ursina_time

    # Hook the playback loop through an Entity — its update/input are always called
    controller = Entity()
    controller.update = lambda: viewer.update(ursina_time.dt)
    controller.input = viewer.input

    app.run()


if __name__ == "__main__":
    main()
