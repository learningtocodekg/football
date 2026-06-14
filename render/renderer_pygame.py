"""
Interactive top-down renderer for Gridiron Minds replays.

Usage:
    python -m render.renderer_pygame replays/play.json

Controls:
    SPACE      play / pause
    ← / →      step backward / forward one frame
    R          toggle reasoning overlay
    +/-        speed up / slow down
    Q / Esc    quit
"""
import json
import math
import sys
from pathlib import Path

import pygame

# ── Colours ──────────────────────────────────────────────────────────────────
GRASS        = (34,  139,  34)
END_ZONE     = ( 0,  100,   0)
LINE_MAJOR   = (255, 255, 255)
LINE_MINOR   = (160, 160, 160)
HASH_COLOR   = (220, 220, 220)
OFFENSE_CLR  = ( 30, 144, 255)   # QB + WR
DEFENSE_CLR  = (220,  50,  50)   # CB
BALL_CLR     = (139,  69,  19)
TRAIL_CLR    = (255, 255, 255, 80)
ARC_CLR      = (255, 215,   0)
REASON_CLR   = (255, 255, 100)
BACKPEDAL_CLR = (  0, 230, 230)  # ring around a player running backwards (mode=backpedal)
SIDEBAR_BG   = ( 18,  18,  18)
WHITE        = (255, 255, 255)
GRAY         = (140, 140, 140)
BLACK        = (  0,   0,   0)
OUTCOME_CLR  = {
    "CATCH":         ( 50, 205,  50),
    "INTERCEPTION":  (255,  50,  50),
    "SACK":          (255,  50,  50),
    "PBU":           (255, 165,   0),
    "DROP":          (200, 200,   0),
    "INCOMPLETE":    (200, 200, 200),
}

FIELD_W   = 53.3
FIELD_L   = 120.0
SIDEBAR_W = 310
TRAIL_LEN = 12   # frames
SIDE_H    = 140  # px — side-elevation (height) panel below the field
SIDE_MAX_Z = 12.0  # yards of height shown in the side panel
REACH_Z   = 3.0  # player vertical reach line


class GridironRenderer:
    def __init__(self, replay_path: str, scale: float = 6.5):
        data = json.loads(Path(replay_path).read_text())
        self.steps   = data["steps"]
        self.header  = data.get("header", {})
        self.footer  = data.get("footer", {})
        self.title   = Path(replay_path).name

        self.scale   = scale
        self.fw      = int(FIELD_W * scale)
        self.fh      = int(FIELD_L * scale)
        self.win_w   = self.fw + SIDEBAR_W
        self.win_h   = self.fh + SIDE_H

        self.cur     = 0
        self.playing = True
        self.fps     = 10
        self.show_reasoning = True

        pygame.init()
        self.screen = pygame.display.set_mode((self.win_w, self.win_h))
        pygame.display.set_caption(f"Gridiron Minds — {self.title}")
        self.clock   = pygame.time.Clock()
        self.font_sm = pygame.font.SysFont("Consolas,monospace", 11)
        self.font_md = pygame.font.SysFont("Consolas,monospace", 13)
        self.font_lg = pygame.font.SysFont("Consolas,monospace", 16, bold=True)

    # ── Coordinate helpers ────────────────────────────────────────────────────
    def fy(self, y: float) -> int:
        """Field y → screen y (flip axis)."""
        return int(self.fh - y * self.scale)

    def fx(self, x: float) -> int:
        return int(x * self.scale)

    def fs(self, x: float, y: float) -> tuple[int, int]:
        return self.fx(x), self.fy(y)

    # ── Drawing helpers ───────────────────────────────────────────────────────
    def _txt(self, text: str, pos, font=None, color=WHITE):
        font = font or self.font_sm
        surf = font.render(text, True, color)
        self.screen.blit(surf, pos)

    def draw_field(self):
        pygame.draw.rect(self.screen, GRASS, (0, 0, self.fw, self.fh))
        # End zones
        ez = int(10 * self.scale)
        pygame.draw.rect(self.screen, END_ZONE, (0, 0, self.fw, ez))
        pygame.draw.rect(self.screen, END_ZONE, (0, self.fh - ez, self.fw, ez))

        # Yard lines
        for yd in range(10, 111):
            sy = self.fy(yd)
            if yd % 10 == 0:
                pygame.draw.line(self.screen, LINE_MAJOR, (0, sy), (self.fw, sy), 1)
                # yard label
                num = min(yd - 10, 100 - (yd - 10))
                self._txt(str(num), (4, sy - 13), color=LINE_MAJOR)
            elif yd % 5 == 0:
                pygame.draw.line(self.screen, LINE_MINOR, (0, sy), (self.fw, sy), 1)

        # Hash marks
        for yd in range(10, 111):
            sy = self.fy(yd)
            for hx in [int(18.5 * self.scale), int(34.8 * self.scale)]:
                pygame.draw.line(self.screen, HASH_COLOR, (hx - 4, sy), (hx + 4, sy), 1)

        # Sidelines
        pygame.draw.rect(self.screen, LINE_MAJOR, (0, 0, self.fw, self.fh), 2)

    def draw_trail(self, pid: str, color):
        positions = []
        lo = max(0, self.cur - TRAIL_LEN)
        for s in self.steps[lo:self.cur + 1]:
            for p in s["players"]:
                if p["id"] == pid:
                    positions.append(p["pos"])
        if len(positions) < 2:
            return
        surf = pygame.Surface((self.fw, self.fh), pygame.SRCALPHA)
        for i in range(1, len(positions)):
            alpha = int(180 * i / len(positions))
            c = (*color[:3], alpha)
            pygame.draw.line(surf, c,
                             self.fs(*positions[i-1]),
                             self.fs(*positions[i]), 2)
        self.screen.blit(surf, (0, 0))

    def draw_player(self, p: dict):
        px, py = p["pos"]
        heading = p["heading"]
        pid = p["id"]
        color = OFFENSE_CLR if pid in ("QB", "WR1") else DEFENSE_CLR

        self.draw_trail(pid, color)

        sx, sy = self.fs(px, py)
        rad = math.radians(heading)
        size = 9

        tip   = (sx + math.sin(rad) * size,        sy - math.cos(rad) * size)
        left  = (sx + math.sin(rad + 2.4) * size * 0.55, sy - math.cos(rad + 2.4) * size * 0.55)
        right = (sx + math.sin(rad - 2.4) * size * 0.55, sy - math.cos(rad - 2.4) * size * 0.55)
        pygame.draw.polygon(self.screen, color,
                            [(int(tip[0]), int(tip[1])),
                             (int(left[0]), int(left[1])),
                             (int(right[0]), int(right[1]))])
        pygame.draw.polygon(self.screen, WHITE,
                            [(int(tip[0]), int(tip[1])),
                             (int(left[0]), int(left[1])),
                             (int(right[0]), int(right[1]))], 1)

        # Backpedal indicator: cyan ring around a player running backwards
        if p.get("mode") == "backpedal":
            pygame.draw.circle(self.screen, BACKPEDAL_CLR, (sx, sy), size + 4, 2)
            self._txt("BP", (sx - 7, sy - 24), color=BACKPEDAL_CLR)

        # ID
        self._txt(pid, (sx + 10, sy - 7), color=WHITE)
        # Reasoning
        if self.show_reasoning and p.get("reasoning"):
            txt = p["reasoning"][:55]
            self._txt(txt, (sx + 10, sy + 5), color=REASON_CLR)

    def draw_ball(self, ball: dict):
        pos = ball["pos"]
        bx, by = pos[0], pos[1]
        bz = pos[2] if len(pos) > 2 else 0.0
        sx, sy = self.fs(bx, by)
        if ball["state"] == "in_air":
            # Shadow on the ground, ball circle grows with height
            pygame.draw.circle(self.screen, BLACK, (sx, sy), 3)
            rad = max(3, int(4 + bz * 1.1))
            pygame.draw.circle(self.screen, BALL_CLR, (sx, sy - int(bz * 1.5)), rad)
            self._txt(f"z={bz:.1f}", (sx + 8, sy - 20), color=ARC_CLR)
            if "landing" in ball:
                land = ball["landing"]
                lx, ly = land[0], land[1]
                lsx, lsy = self.fs(lx, ly)
                pygame.draw.line(self.screen, ARC_CLR, (sx, sy), (lsx, lsy), 1)
                pygame.draw.circle(self.screen, ARC_CLR, (lsx, lsy), 4, 1)
                eta = ball.get("eta", 0)
                self._txt(f"{eta:.2f}s", (lsx + 5, lsy - 8), color=ARC_CLR)
        elif ball["state"] == "held":
            # Small dot on holder
            pygame.draw.circle(self.screen, BALL_CLR, (sx, sy), 4)

    # ── Side-elevation (height) panel ─────────────────────────────────────────
    def sv(self, y: float, z: float) -> tuple[int, int]:
        """Field (y, z) → side-panel screen coords (x = field y, vertical = height)."""
        sx = int(y / FIELD_L * self.fw)
        sy = int(self.fh + SIDE_H - 18 - (z / SIDE_MAX_Z) * (SIDE_H - 34))
        return sx, sy

    def _flight_segment(self) -> list[dict]:
        """All steps of the throw flight at or before the current frame (replay is complete)."""
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
        return self.steps[start:stop + 1]

    def draw_side_view(self):
        pygame.draw.rect(self.screen, (12, 30, 12), (0, self.fh, self.fw, SIDE_H))
        pygame.draw.line(self.screen, LINE_MINOR, (0, self.fh), (self.fw, self.fh), 1)
        self._txt("SIDE VIEW  (field y vs height z)", (6, self.fh + 3), color=GRAY)

        _, ground_y = self.sv(0, 0)
        pygame.draw.line(self.screen, LINE_MAJOR, (0, ground_y), (self.fw, ground_y), 1)
        for yd in range(0, 121, 10):
            tx, _ = self.sv(yd, 0)
            pygame.draw.line(self.screen, LINE_MINOR, (tx, ground_y), (tx, ground_y + 4), 1)
        # Height reference lines
        for z_ref in (REACH_Z, 6.0, 9.0):
            _, zy = self.sv(0, z_ref)
            pygame.draw.line(self.screen, (60, 80, 60), (0, zy), (self.fw, zy), 1)
            self._txt(f"z={z_ref:.0f}", (self.fw - 34, zy - 12), color=GRAY)

        step = self.steps[self.cur]
        # Players as stems (body to 2.0 yd, reach tick at 3.0 yd)
        for p in step["players"]:
            py = p["pos"][1]
            color = OFFENSE_CLR if p["id"] in ("QB", "WR1") else DEFENSE_CLR
            px_s, body_top = self.sv(py, 2.0)
            _, base = self.sv(py, 0)
            pygame.draw.line(self.screen, color, (px_s, base), (px_s, body_top), 3)
            _, reach_y = self.sv(py, REACH_Z)
            pygame.draw.line(self.screen, color, (px_s - 3, reach_y), (px_s + 3, reach_y), 1)
            self._txt(p["id"], (px_s - 8, base + 4), color=color)

        # Full flight arc (past + future of the nearest flight)
        flight = self._flight_segment()
        if flight:
            pts = []
            for s in flight:
                bp = s["ball"]["pos"]
                if len(bp) > 2:
                    pts.append(self.sv(bp[1], bp[2]))
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, ARC_CLR, False, pts, 1)
            land = flight[-1]["ball"].get("landing")
            if land:
                lz = land[2] if len(land) > 2 else 0.0
                lpx, lpy = self.sv(land[1], lz)
                pygame.draw.circle(self.screen, ARC_CLR, (lpx, lpy), 3, 1)

        # Current ball position
        bp = step["ball"]["pos"]
        if step["ball"]["state"] == "in_air" and len(bp) > 2:
            cx, cy = self.sv(bp[1], bp[2])
            pygame.draw.circle(self.screen, BALL_CLR, (cx, cy), 4)

    def _wrap(self, text: str, max_chars: int) -> list[str]:
        words = text.split()
        lines, cur = [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > max_chars:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
        return lines

    def draw_sidebar(self):
        x0 = self.fw
        pygame.draw.rect(self.screen, SIDEBAR_BG, (x0, 0, SIDEBAR_W, self.win_h))

        step = self.steps[self.cur]
        y = 12

        def line(txt, color=WHITE, font=None):
            nonlocal y
            self._txt(txt, (x0 + 10, y), font=font or self.font_md, color=color)
            y += (font or self.font_md).get_height() + 3

        line(f"t = {step['t']:.1f}s", color=(255,215,0), font=self.font_lg)
        line(f"phase      {step['phase']}")
        line(f"sack_clock {step['sack_clock']:.1f}s")
        line(f"frame {self.cur+1}/{len(self.steps)}", color=GRAY)
        y += 8

        # Events
        for ev in step.get("events", []):
            et = ev.get("type", "")
            if et == "THROW":
                arc = ev.get("arc", "")
                tz = ev.get("target_z")
                tz_str = f" z={tz}" if tz is not None else ""
                line(f"THROW → {ev.get('target')} {arc}{tz_str} {ev.get('mph')}mph", color=(100,200,255))
            elif et in ("LANE_TIP", "LANE_PICK"):
                line(f"► {et} at z={ev.get('ball_z','?')}", color=OUTCOME_CLR["PBU"], font=self.font_lg)
            elif et == "RESOLUTION":
                oc = ev.get("outcome", "?")
                col = OUTCOME_CLR.get(oc, WHITE)
                line(f"► {oc}  sep={ev.get('separation','?')}yd", color=col, font=self.font_lg)
            elif et == "SACK":
                line("► SACK", color=OUTCOME_CLR["SACK"], font=self.font_lg)

        # Per-player reasoning panel
        y += 4
        line("── REASONING ──", color=GRAY)
        PLAYER_COLORS = {"QB": (100, 200, 255), "WR1": (30, 144, 255), "CB1": (220, 80, 80)}
        wrap_chars = (SIDEBAR_W - 20) // self.font_sm.size("x")[0]
        for p in step["players"]:
            reasoning = p.get("reasoning", "").strip()
            if not reasoning:
                continue
            pid = p["id"]
            action = p.get("action", "")
            pcol = PLAYER_COLORS.get(pid, WHITE)
            line(f"{pid} [{action}]", color=pcol, font=self.font_sm)
            for wl in self._wrap(reasoning, wrap_chars):
                line(wl, color=REASON_CLR, font=self.font_sm)
            y += 3

        y += 8
        line("CONTROLS", color=GRAY)
        line("SPACE  play/pause",  color=GRAY)
        line("← →    step frame",  color=GRAY)
        line("+/-    fps",         color=GRAY)
        line("R      field text",  color=GRAY)
        line("Q/Esc  quit",        color=GRAY)
        y += 8
        line("LEGEND", color=GRAY)
        line("cyan ring = backpedal", color=BACKPEDAL_CLR, font=self.font_sm)
        y += 8
        line(f"fps={self.fps}  field_text={'ON' if self.show_reasoning else 'off'}", color=GRAY)

        # Footer
        footer = self.footer
        if footer:
            y += 12
            oc = footer.get("outcome", "")
            col = OUTCOME_CLR.get(oc, WHITE)
            line(f"RESULT: {oc}", color=col, font=self.font_lg)
            tel = footer.get("telemetry", {})
            if tel:
                line(f"max_sep  {tel.get('max_separation','?')} yd")
                line(f"throw_t  {tel.get('throw_t','?')} s")
                line(f"dist     {tel.get('throw_distance','?')} yd")
                if tel.get("throw_arc"):
                    line(f"arc      {tel.get('throw_arc')}  z={tel.get('target_z','?')}")
                line(f"qb_calls {tel.get('qb_calls','?')}")

    def run(self):
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    k = ev.key
                    if k in (pygame.K_q, pygame.K_ESCAPE):
                        running = False
                    elif k == pygame.K_SPACE:
                        self.playing = not self.playing
                    elif k == pygame.K_RIGHT:
                        self.cur = min(len(self.steps)-1, self.cur + 1)
                    elif k == pygame.K_LEFT:
                        self.cur = max(0, self.cur - 1)
                    elif k == pygame.K_r:
                        self.show_reasoning = not self.show_reasoning
                    elif k in (pygame.K_PLUS, pygame.K_EQUALS):
                        self.fps = min(60, self.fps + 2)
                    elif k == pygame.K_MINUS:
                        self.fps = max(1, self.fps - 2)

            self.screen.fill(BLACK)
            self.draw_field()
            step = self.steps[self.cur]
            for p in step["players"]:
                self.draw_player(p)
            self.draw_ball(step["ball"])
            self.draw_side_view()
            self.draw_sidebar()
            pygame.display.flip()

            if self.playing and self.cur < len(self.steps) - 1:
                self.cur += 1

            self.clock.tick(self.fps)

        pygame.quit()


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m render.renderer_pygame <replay.json>")
        sys.exit(1)
    GridironRenderer(sys.argv[1]).run()


if __name__ == "__main__":
    main()
