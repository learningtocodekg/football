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
import sys
from pathlib import Path

from ursina import (
    Ursina, Entity, Text, Vec3, color, camera, application, window,
)

FIELD_W = 53.3
FIELD_L = 120.0

OFFENSE_COLOR = color.rgb(30, 144, 255)
DEFENSE_COLOR = color.rgb(220, 50, 50)
BALL_COLOR = color.rgb(139, 69, 19)
ARC_COLOR = color.rgb(255, 215, 0)


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
               color=color.rgb(34, 139, 34))
        # End zones
        for z0 in (5.0, FIELD_L - 5.0):
            Entity(model="plane", scale=(FIELD_W, 1, 10),
                   position=Vec3(FIELD_W / 2, 0.01, z0),
                   color=color.rgb(0, 100, 0))
        # Yard lines
        for yd in range(10, 111, 5):
            major = yd % 10 == 0
            Entity(model="cube",
                   scale=(FIELD_W, 0.02, 0.12 if major else 0.06),
                   position=Vec3(FIELD_W / 2, 0.02, yd),
                   color=color.white if major else color.rgb(160, 160, 160))
        # Hash marks
        for yd in range(10, 111):
            for hx in (18.5, 34.8):
                Entity(model="cube", scale=(0.5, 0.02, 0.08),
                       position=Vec3(hx, 0.02, yd),
                       color=color.rgb(220, 220, 220))
        # Sidelines
        for sx in (0.0, FIELD_W):
            Entity(model="cube", scale=(0.15, 0.02, FIELD_L),
                   position=Vec3(sx, 0.02, FIELD_L / 2), color=color.white)

    def _build_players(self):
        self.player_entities: dict[str, Entity] = {}
        self.player_labels: dict[str, Text] = {}
        for p in self.steps[0]["players"]:
            pid = p["id"]
            clr = OFFENSE_COLOR if pid in ("QB", "WR1") else DEFENSE_COLOR
            ent = Entity(model="cube", scale=(0.8, 2.0, 0.5), color=clr,
                         position=Vec3(p["pos"][0], 1.0, p["pos"][1]))
            self.player_entities[pid] = ent
            label = Text(text=pid, parent=ent, y=1.4, scale=18,
                         billboard=True, origin=(0, 0), color=color.white)
            self.player_labels[pid] = label

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
                                color=color.rgb(255, 255, 150))

    def _set_camera(self):
        # Madden cam: behind the offense, looking upfield
        camera.position = Vec3(FIELD_W / 2, 14, 32)
        camera.look_at(Vec3(FIELD_W / 2, 0, 75))
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
            ent.position = Vec3(p["pos"][0], 1.0, p["pos"][1])
            ent.rotation_y = p.get("heading", 0.0)

        ball = step["ball"]
        bp = ball["pos"]
        bz = bp[2] if len(bp) > 2 else 0.0
        if ball["state"] == "in_air":
            self.ball_entity.position = Vec3(bp[0], max(bz, 0.25), bp[1])
        else:
            # sit the ball on its holder
            holder = self.player_entities.get(ball.get("holder", "QB"))
            base = holder.position if holder is not None else Vec3(bp[0], 1.0, bp[1])
            self.ball_entity.position = base + Vec3(0.5, 0.2, 0)

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
    window.color = color.rgb(10, 10, 20)
    viewer = UrsinaReplay(sys.argv[1])

    from ursina import time as ursina_time

    # Hook the playback loop through an Entity — its update/input are always called
    controller = Entity()
    controller.update = lambda: viewer.update(ursina_time.dt)
    controller.input = viewer.input

    app.run()


if __name__ == "__main__":
    main()
