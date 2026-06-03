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
        self.win_h   = self.fh

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

        # ID
        self._txt(pid, (sx + 10, sy - 7), color=WHITE)
        # Reasoning
        if self.show_reasoning and p.get("reasoning"):
            txt = p["reasoning"][:55]
            self._txt(txt, (sx + 10, sy + 5), color=REASON_CLR)

    def draw_ball(self, ball: dict):
        bx, by = ball["pos"]
        sx, sy = self.fs(bx, by)
        if ball["state"] == "in_air":
            pygame.draw.circle(self.screen, BALL_CLR, (sx, sy), 5)
            if "landing" in ball:
                lx, ly = ball["landing"]
                lsx, lsy = self.fs(lx, ly)
                pygame.draw.line(self.screen, ARC_CLR, (sx, sy), (lsx, lsy), 1)
                pygame.draw.circle(self.screen, ARC_CLR, (lsx, lsy), 4, 1)
                eta = ball.get("eta", 0)
                self._txt(f"{eta:.2f}s", (lsx + 5, lsy - 8), color=ARC_CLR)
        elif ball["state"] == "held":
            # Small dot on holder
            pygame.draw.circle(self.screen, BALL_CLR, (sx, sy), 4)

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
                line(f"THROW → {ev.get('target')}  {ev.get('mph')}mph", color=(100,200,255))
            elif et == "RESOLUTION":
                oc = ev.get("outcome", "?")
                col = OUTCOME_CLR.get(oc, WHITE)
                line(f"► {oc}  sep={ev.get('separation','?')}yd", color=col, font=self.font_lg)
            elif et == "SACK":
                line("► SACK", color=OUTCOME_CLR["SACK"], font=self.font_lg)

        y += 8
        line("CONTROLS", color=GRAY)
        line("SPACE  play/pause",  color=GRAY)
        line("← →    step frame",  color=GRAY)
        line("+/-    fps",         color=GRAY)
        line("R      reasoning",   color=GRAY)
        line("Q/Esc  quit",        color=GRAY)
        y += 8
        line(f"fps={self.fps}  reasoning={'ON' if self.show_reasoning else 'off'}", color=GRAY)

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
