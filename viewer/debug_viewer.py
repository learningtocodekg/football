"""
Gridiron Minds — Debug Viewer

Renders a replay with step-by-step decision explanations for each position.

Usage:
    python -m viewer.debug_viewer                    # load from replays/
    python -m viewer.debug_viewer replays/           # explicit directory
    python -m viewer.debug_viewer replays/foo.json   # single file

Controls:
    SPACE       play / pause
    ← / →       step backward / forward
    ↑ / ↓       scroll decision log up / down
    Q / Esc     quit
    +/-         change playback speed
    Tab         switch active position tab (QB / WR1 / CB1)
    R           reload replay list
"""
import json
import math
import sys
import textwrap
from pathlib import Path

import pygame

# ── Colours ──────────────────────────────────────────────────────────────────
GRASS       = (34, 139, 34)
END_ZONE    = (0, 100, 0)
LINE_MAJOR  = (255, 255, 255)
LINE_MINOR  = (160, 160, 160)
HASH_COLOR  = (200, 200, 200)
OFFENSE_CLR = (30, 144, 255)
DEFENSE_CLR = (220, 50, 50)
BALL_CLR    = (139, 69, 19)
ARC_CLR     = (255, 215, 0)
WHITE       = (255, 255, 255)
GRAY        = (140, 140, 140)
DARK_GRAY   = (60, 60, 60)
BLACK       = (0, 0, 0)
YELLOW      = (255, 215, 0)
BG_PANEL    = (22, 22, 28)
BG_HEADER   = (12, 12, 18)
BG_TAB_ACT  = (50, 90, 160)
BG_TAB_IDLE = (30, 30, 40)
BG_ENTRY    = (28, 28, 35)
BG_ENTRY_CUR = (50, 60, 30)
OUTCOME_CLR = {
    "CATCH":        (50, 205, 50),
    "INTERCEPTION": (255, 50, 50),
    "SACK":         (255, 50, 50),
    "PBU":          (255, 165, 0),
    "DROP":         (200, 200, 0),
    "INCOMPLETE":   (200, 200, 200),
    "TIMEOUT":      (180, 180, 100),
}
TRAIL_LEN = 14

# ── Layout constants ──────────────────────────────────────────────────────────
FIELD_SCALE  = 5.5          # px per yard
FIELD_W      = 53.3
FIELD_L      = 120.0
FIELD_W_PX   = int(FIELD_W * FIELD_SCALE)   # ~293
FIELD_H_PX   = int(FIELD_L * FIELD_SCALE)   # 660
HEADER_H     = 44
FOOTER_H     = 44
PANEL_W      = 720
WIN_W        = FIELD_W_PX + PANEL_W         # ~1013
WIN_H        = FIELD_H_PX + HEADER_H + FOOTER_H  # 748

TABS = ["QB", "WR1", "CB1"]
TAB_W = PANEL_W // len(TABS)
TAB_H = 36
LOG_TOP = HEADER_H + TAB_H   # y where log area starts
LOG_H   = WIN_H - LOG_TOP - FOOTER_H
LOG_X   = FIELD_W_PX
ENTRY_PAD = 4


def _load_replays(path_arg: str) -> list[Path]:
    p = Path(path_arg)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(p.glob("*.json"))
    return []


def _build_decision_log(steps: list[dict], player_id: str) -> list[dict]:
    """Extract per-step decision entries for one player."""
    log = []
    for step in steps:
        entry = {
            "t": step["t"],
            "phase": step["phase"],
            "events": step.get("events", []),
            "action": "",
            "heading": None,
            "speed": None,
            "reasoning": "",
        }
        for p in step["players"]:
            if p["id"] == player_id:
                entry["action"] = p.get("action", "")
                entry["heading"] = p.get("heading")
                entry["speed"] = p.get("speed")
                entry["reasoning"] = p.get("reasoning", "")
                break
        log.append(entry)
    return log


class DebugViewer:
    def __init__(self, replays_dir: str = "replays"):
        pygame.init()
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("Gridiron Minds — Debug Viewer")
        self.clock = pygame.time.Clock()

        self.font_sm  = pygame.font.SysFont("Consolas,Courier New,monospace", 10)
        self.font_md  = pygame.font.SysFont("Consolas,Courier New,monospace", 12)
        self.font_lg  = pygame.font.SysFont("Consolas,Courier New,monospace", 14, bold=True)
        self.font_hdr = pygame.font.SysFont("Consolas,Courier New,monospace", 13, bold=True)

        self.replays_dir = replays_dir
        self.replay_paths: list[Path] = []
        self.replay_idx = 0
        self.steps: list[dict] = []
        self.header: dict = {}
        self.footer: dict = {}
        self.title = ""
        self.logs: dict[str, list[dict]] = {}  # player_id -> log

        self.cur = 0
        self.playing = False
        self.fps = 10
        self.active_tab = "WR1"
        self.log_scroll = 0       # pixel offset from top of log
        self.show_dropdown = False

        self._load_replay_list()
        if self.replay_paths:
            self._load_replay(0)

    # ── Replay management ─────────────────────────────────────────────────────

    def _load_replay_list(self):
        p = Path(self.replays_dir)
        if p.is_dir():
            self.replay_paths = sorted(p.glob("*.json"))
        elif p.is_file() and p.suffix == ".json":
            self.replay_paths = [p]
        else:
            self.replay_paths = []

    def _load_replay(self, idx: int):
        if not self.replay_paths:
            return
        idx = max(0, min(idx, len(self.replay_paths) - 1))
        self.replay_idx = idx
        data = json.loads(self.replay_paths[idx].read_text())
        self.steps  = data["steps"]
        self.header = data.get("header", {})
        self.footer = data.get("footer", {})
        self.title  = self.replay_paths[idx].name
        self.logs   = {pid: _build_decision_log(self.steps, pid) for pid in TABS}
        self.cur    = 0
        self.log_scroll = 0
        self.show_dropdown = False
        pygame.display.set_caption(f"Gridiron Minds Debug — {self.title}")

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _fy(self, y: float) -> int:
        """Field y → screen y (flipped, offset by header)."""
        return HEADER_H + int(FIELD_H_PX - y * FIELD_SCALE)

    def _fx(self, x: float) -> int:
        return int(x * FIELD_SCALE)

    def _fs(self, x: float, y: float):
        return self._fx(x), self._fy(y)

    # ── Drawing helpers ───────────────────────────────────────────────────────

    def _txt(self, text: str, pos, font=None, color=WHITE, bg=None):
        font = font or self.font_sm
        surf = font.render(text, True, color)
        if bg:
            pygame.draw.rect(self.screen, bg, (*pos, surf.get_width() + 4, surf.get_height()))
        self.screen.blit(surf, pos)

    def _wrap_text(self, text: str, max_width: int, font) -> list[str]:
        if not text:
            return []
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = current + (" " if current else "") + word
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    # ── Field drawing ─────────────────────────────────────────────────────────

    def draw_field(self):
        # Field rectangle
        pygame.draw.rect(self.screen, GRASS, (0, HEADER_H, FIELD_W_PX, FIELD_H_PX))
        # End zones
        ez = int(10 * FIELD_SCALE)
        pygame.draw.rect(self.screen, END_ZONE, (0, HEADER_H, FIELD_W_PX, ez))
        pygame.draw.rect(self.screen, END_ZONE, (0, HEADER_H + FIELD_H_PX - ez, FIELD_W_PX, ez))

        # Yard lines
        for yd in range(10, 111):
            sy = self._fy(yd)
            if yd % 10 == 0:
                pygame.draw.line(self.screen, LINE_MAJOR, (0, sy), (FIELD_W_PX, sy), 1)
                num = min(yd - 10, 100 - (yd - 10))
                self._txt(str(num), (3, sy - 12), color=LINE_MAJOR, font=self.font_sm)
            elif yd % 5 == 0:
                pygame.draw.line(self.screen, LINE_MINOR, (0, sy), (FIELD_W_PX, sy), 1)

        # Hash marks
        for yd in range(10, 111):
            sy = self._fy(yd)
            for hx in [int(18.5 * FIELD_SCALE), int(34.8 * FIELD_SCALE)]:
                pygame.draw.line(self.screen, HASH_COLOR, (hx - 3, sy), (hx + 3, sy), 1)

        pygame.draw.rect(self.screen, LINE_MAJOR, (0, HEADER_H, FIELD_W_PX, FIELD_H_PX), 2)

    def draw_trail(self, pid: str, color):
        positions = []
        lo = max(0, self.cur - TRAIL_LEN)
        for s in self.steps[lo:self.cur + 1]:
            for p in s["players"]:
                if p["id"] == pid:
                    positions.append(p["pos"])
        if len(positions) < 2:
            return
        surf = pygame.Surface((FIELD_W_PX, FIELD_H_PX), pygame.SRCALPHA)
        for i in range(1, len(positions)):
            alpha = int(160 * i / len(positions))
            c = (*color[:3], alpha)
            pygame.draw.line(surf, c,
                             (self._fx(positions[i-1][0]), int(FIELD_H_PX - positions[i-1][1] * FIELD_SCALE)),
                             (self._fx(positions[i][0]),   int(FIELD_H_PX - positions[i][1]   * FIELD_SCALE)), 2)
        self.screen.blit(surf, (0, HEADER_H))

    def draw_player(self, p: dict):
        px, py = p["pos"]
        heading = p["heading"]
        pid = p["id"]
        color = OFFENSE_CLR if pid in ("QB", "WR1") else DEFENSE_CLR

        self.draw_trail(pid, color)

        sx, sy = self._fs(px, py)
        rad = math.radians(heading)
        size = 8
        tip   = (sx + math.sin(rad) * size,         sy - math.cos(rad) * size)
        left  = (sx + math.sin(rad + 2.4) * size * 0.55, sy - math.cos(rad + 2.4) * size * 0.55)
        right = (sx + math.sin(rad - 2.4) * size * 0.55, sy - math.cos(rad - 2.4) * size * 0.55)
        pts = [(int(tip[0]), int(tip[1])), (int(left[0]), int(left[1])), (int(right[0]), int(right[1]))]
        pygame.draw.polygon(self.screen, color, pts)
        pygame.draw.polygon(self.screen, WHITE, pts, 1)
        self._txt(pid, (sx + 9, sy - 6), color=WHITE, font=self.font_sm)

    def draw_ball(self, ball: dict):
        bx, by = ball["pos"][0], ball["pos"][1]
        bz = ball["pos"][2] if len(ball["pos"]) > 2 else 0.0
        sx, sy = self._fs(bx, by)
        if ball["state"] == "in_air":
            # Ground shadow + ball drawn larger when higher
            pygame.draw.circle(self.screen, DARK_GRAY, (sx, sy), 3)
            rad = 5 + min(4, int(bz * 0.6))
            pygame.draw.circle(self.screen, BALL_CLR, (sx, sy - int(bz * 2)), rad)
            if bz > 0.1:
                self._txt(f"z={bz:.1f}", (sx + 8, sy - 18), color=ARC_CLR, font=self.font_sm)
            if "landing" in ball:
                lx, ly = ball["landing"][0], ball["landing"][1]
                lsx, lsy = self._fs(lx, ly)
                pygame.draw.line(self.screen, ARC_CLR, (sx, sy), (lsx, lsy), 1)
                pygame.draw.circle(self.screen, ARC_CLR, (lsx, lsy), 4, 1)
                eta = ball.get("eta", 0)
                self._txt(f"{eta:.2f}s", (lsx + 4, lsy - 8), color=ARC_CLR, font=self.font_sm)
        elif ball["state"] == "held":
            pygame.draw.circle(self.screen, BALL_CLR, (sx, sy), 4)

    # ── Header (replay selector) ──────────────────────────────────────────────

    def draw_header(self):
        pygame.draw.rect(self.screen, BG_HEADER, (0, 0, WIN_W, HEADER_H))
        pygame.draw.line(self.screen, DARK_GRAY, (0, HEADER_H - 1), (WIN_W, HEADER_H - 1), 1)

        if not self.replay_paths:
            self._txt("No replays found in replays/", (10, 14), color=GRAY, font=self.font_hdr)
            return

        total = len(self.replay_paths)
        idx_txt = f"[{self.replay_idx + 1}/{total}]"
        self._txt(idx_txt, (8, 14), color=GRAY, font=self.font_md)

        # Replay name (clickable dropdown toggle)
        name_x = 70
        name = self.title[:50]
        drop_label = f"  {name}  ▼" if not self.show_dropdown else f"  {name}  ▲"
        color = YELLOW if self.show_dropdown else WHITE
        self._txt(drop_label, (name_x, 14), color=color, font=self.font_hdr)

        # Outcome
        outcome = self.footer.get("outcome", "")
        if outcome:
            col = OUTCOME_CLR.get(outcome, WHITE)
            self._txt(f"  [{outcome}]", (name_x + 520, 14), color=col, font=self.font_hdr)

        # Dropdown
        if self.show_dropdown:
            dd_x = name_x
            dd_y = HEADER_H
            dd_w = 480
            row_h = 18
            visible = min(len(self.replay_paths), 18)
            pygame.draw.rect(self.screen, (30, 30, 40), (dd_x, dd_y, dd_w, visible * row_h + 4))
            pygame.draw.rect(self.screen, GRAY, (dd_x, dd_y, dd_w, visible * row_h + 4), 1)
            for i, rp in enumerate(self.replay_paths[:visible]):
                ry = dd_y + 2 + i * row_h
                if i == self.replay_idx:
                    pygame.draw.rect(self.screen, (50, 80, 50), (dd_x + 1, ry, dd_w - 2, row_h))
                col = YELLOW if i == self.replay_idx else WHITE
                self._txt(rp.name[:58], (dd_x + 6, ry + 2), color=col, font=self.font_sm)

    def _header_click(self, mx: int, my: int):
        if self.show_dropdown:
            # check dropdown items
            dd_x = 70
            dd_y = HEADER_H
            row_h = 18
            visible = min(len(self.replay_paths), 18)
            if dd_x <= mx <= dd_x + 480 and dd_y <= my <= dd_y + visible * row_h + 4:
                idx = (my - dd_y - 2) // row_h
                if 0 <= idx < visible:
                    self._load_replay(idx)
                    return
            # click outside dropdown closes it
            self.show_dropdown = False
            return
        # toggle dropdown
        if 70 <= mx <= 600:
            self.show_dropdown = not self.show_dropdown

    # ── Footer (controls) ─────────────────────────────────────────────────────

    def draw_footer(self):
        fy = WIN_H - FOOTER_H
        pygame.draw.rect(self.screen, BG_HEADER, (0, fy, WIN_W, FOOTER_H))
        pygame.draw.line(self.screen, DARK_GRAY, (0, fy), (WIN_W, fy), 1)

        if not self.steps:
            return

        step = self.steps[self.cur]
        t_txt = f"t={step['t']:.1f}s"
        phase = step.get("phase", "")
        events_txt = ""
        for ev in step.get("events", []):
            et = ev.get("type", "")
            if et == "THROW":
                events_txt += f" | THROW {ev.get('mph')}mph"
            elif et == "RESOLUTION":
                events_txt += f" | {ev.get('outcome','?')}"
            elif et == "SACK":
                events_txt += " | SACK"
            elif et == "WR_CALL_FOR_BALL":
                events_txt += f" | WR CALL hdg={ev.get('heading',0):.0f}°"

        info = f"{t_txt}  {phase}  frame={self.cur+1}/{len(self.steps)}{events_txt}"
        self._txt(info, (8, fy + 8), color=YELLOW, font=self.font_md)

        controls = "SPACE=play/pause  ←→=step  ↑↓=scroll  Tab=tab  +/-=fps  Q=quit"
        self._txt(f"fps={self.fps}  {controls}", (8, fy + 24), color=GRAY, font=self.font_sm)

    # ── Decision panel ────────────────────────────────────────────────────────

    def draw_panel(self):
        # Panel background
        pygame.draw.rect(self.screen, BG_PANEL, (FIELD_W_PX, HEADER_H, PANEL_W, WIN_H - HEADER_H))
        pygame.draw.line(self.screen, DARK_GRAY, (FIELD_W_PX, HEADER_H), (FIELD_W_PX, WIN_H), 1)

        if not self.replay_paths:
            return

        # Tab bar
        self._draw_tabs()
        # Log area
        self._draw_log()

    def _draw_tabs(self):
        tab_y = HEADER_H
        for i, tab in enumerate(TABS):
            tx = FIELD_W_PX + i * TAB_W
            bg = BG_TAB_ACT if tab == self.active_tab else BG_TAB_IDLE
            pygame.draw.rect(self.screen, bg, (tx, tab_y, TAB_W, TAB_H))
            pygame.draw.rect(self.screen, DARK_GRAY, (tx, tab_y, TAB_W, TAB_H), 1)

            # Count parse errors for this player from footer
            label = tab
            self._txt(label, (tx + TAB_W // 2 - 14, tab_y + 10), color=WHITE, font=self.font_hdr)

    def _draw_log(self):
        log = self.logs.get(self.active_tab, [])
        if not log:
            self._txt(f"No data for {self.active_tab}", (LOG_X + 10, LOG_TOP + 10), color=GRAY)
            return

        # Clipping region for log
        clip = pygame.Rect(LOG_X, LOG_TOP, PANEL_W, LOG_H)
        self.screen.set_clip(clip)

        line_h_sm  = self.font_sm.get_height() + 1
        line_h_md  = self.font_md.get_height() + 2
        max_text_w = PANEL_W - 18

        # First pass: compute heights so we can position each entry
        entry_rects = []  # (entry_idx, y_start, entry_height)
        y = 0
        for i, entry in enumerate(log):
            wrapped = self._wrap_text(entry["reasoning"], max_text_w, self.font_sm)
            # header line + wrapped reasoning + spacing
            entry_h = line_h_md + max(1, len(wrapped)) * line_h_sm + ENTRY_PAD * 2 + 2
            entry_rects.append((i, y, entry_h))
            y += entry_h

        total_h = y

        # Auto-scroll to keep current entry visible
        if self.cur < len(entry_rects):
            _, ey, eh = entry_rects[self.cur]
            # Ensure current entry is visible
            if ey - self.log_scroll < 0:
                self.log_scroll = ey
            elif ey + eh - self.log_scroll > LOG_H:
                self.log_scroll = ey + eh - LOG_H

        self.log_scroll = max(0, min(self.log_scroll, max(0, total_h - LOG_H)))

        # Second pass: draw
        for i, entry in enumerate(log):
            _, ey, eh = entry_rects[i]
            screen_y = LOG_TOP + ey - self.log_scroll

            if screen_y + eh < LOG_TOP or screen_y > LOG_TOP + LOG_H:
                continue  # off screen

            is_current = (i == self.cur)
            bg = BG_ENTRY_CUR if is_current else BG_ENTRY
            pygame.draw.rect(self.screen, bg, (LOG_X, screen_y, PANEL_W - 1, eh))
            if is_current:
                pygame.draw.rect(self.screen, YELLOW, (LOG_X, screen_y, PANEL_W - 1, eh), 1)

            # Header line: t=X.Xs  action  heading  speed  events
            hdg = f"hdg={entry['heading']:.0f}°" if entry['heading'] is not None else ""
            spd = f"spd={entry['speed']:.1f}" if entry['speed'] is not None else ""
            phase_short = entry['phase'][:4]
            evts = ""
            for ev in entry.get("events", []):
                et = ev.get("type", "")
                if et == "THROW":
                    evts += " [THROW]"
                elif et == "RESOLUTION":
                    evts += f" [{ev.get('outcome','?')}]"
                elif et == "WR_CALL_FOR_BALL":
                    evts += " [CALL]"
                elif et == "SACK":
                    evts += " [SACK]"

            hdr = f"t={entry['t']:.1f}s  {phase_short}  {entry['action'][:8]}  {hdg}  {spd}{evts}"
            hdr_color = YELLOW if is_current else (180, 200, 255)
            self._txt(hdr, (LOG_X + 6, screen_y + ENTRY_PAD), color=hdr_color, font=self.font_md)

            # Reasoning (wrapped)
            reasoning = entry["reasoning"] or "(no reasoning)"
            wrapped = self._wrap_text(reasoning, max_text_w, self.font_sm)
            for j, line in enumerate(wrapped[:8]):  # cap at 8 wrapped lines
                ry = screen_y + ENTRY_PAD + line_h_md + j * line_h_sm
                r_color = WHITE if is_current else GRAY
                self._txt(line, (LOG_X + 8, ry), color=r_color, font=self.font_sm)

        self.screen.set_clip(None)

        # Scrollbar
        if total_h > LOG_H:
            sb_x = LOG_X + PANEL_W - 6
            sb_h = max(20, int(LOG_H * LOG_H / total_h))
            sb_y = LOG_TOP + int(self.log_scroll / total_h * LOG_H)
            pygame.draw.rect(self.screen, DARK_GRAY, (sb_x, LOG_TOP, 5, LOG_H))
            pygame.draw.rect(self.screen, GRAY, (sb_x, sb_y, 5, sb_h))

    # ── Tab click handling ────────────────────────────────────────────────────

    def _panel_click(self, mx: int, my: int):
        if HEADER_H <= my <= HEADER_H + TAB_H:
            rel_x = mx - FIELD_W_PX
            tab_idx = rel_x // TAB_W
            if 0 <= tab_idx < len(TABS):
                self.active_tab = TABS[tab_idx]
                self.log_scroll = 0

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if my < HEADER_H or self.show_dropdown:
                        self._header_click(mx, my)
                    elif mx > FIELD_W_PX:
                        self._panel_click(mx, my)
                    elif event.button == 4:  # scroll up on field
                        pass
                    elif event.button == 5:
                        pass

                elif event.type == pygame.MOUSEWHEEL:
                    mx, my = pygame.mouse.get_pos()
                    if mx > FIELD_W_PX:
                        self.log_scroll -= event.y * 30
                        self.log_scroll = max(0, self.log_scroll)

                elif event.type == pygame.KEYDOWN:
                    k = event.key
                    if k in (pygame.K_q, pygame.K_ESCAPE):
                        running = False
                    elif k == pygame.K_SPACE:
                        self.playing = not self.playing
                        self.show_dropdown = False
                    elif k == pygame.K_RIGHT:
                        self.cur = min(len(self.steps) - 1, self.cur + 1)
                        self.playing = False
                    elif k == pygame.K_LEFT:
                        self.cur = max(0, self.cur - 1)
                        self.playing = False
                    elif k == pygame.K_UP:
                        self.log_scroll = max(0, self.log_scroll - 40)
                    elif k == pygame.K_DOWN:
                        self.log_scroll += 40
                    elif k == pygame.K_TAB:
                        idx = TABS.index(self.active_tab) if self.active_tab in TABS else 0
                        self.active_tab = TABS[(idx + 1) % len(TABS)]
                        self.log_scroll = 0
                    elif k in (pygame.K_PLUS, pygame.K_EQUALS):
                        self.fps = min(60, self.fps + 2)
                    elif k == pygame.K_MINUS:
                        self.fps = max(1, self.fps - 2)
                    elif k == pygame.K_r:
                        self._load_replay_list()

            self.screen.fill(BLACK)

            if self.steps:
                self.draw_field()
                step = self.steps[self.cur]
                for p in step["players"]:
                    self.draw_player(p)
                self.draw_ball(step["ball"])

            self.draw_panel()
            self.draw_header()
            self.draw_footer()

            # Dropdown on top of everything
            if self.show_dropdown:
                self.draw_header()

            pygame.display.flip()

            if self.playing and self.steps and self.cur < len(self.steps) - 1:
                self.cur += 1

            self.clock.tick(self.fps)

        pygame.quit()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "replays"
    viewer = DebugViewer(path)
    viewer.run()


if __name__ == "__main__":
    main()
