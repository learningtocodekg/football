import json
from pathlib import Path


class Recorder:
    def __init__(self, header: dict):
        self.header = header
        self.steps: list[dict] = []
        self.footer: dict = {}

    def record_step(
        self,
        t: float,
        phase: str,
        sack_clock: float,
        players_snapshot: list[dict],
        ball_snapshot: dict,
        events: list[dict],
    ) -> None:
        self.steps.append({
            "t": round(t, 2),
            "phase": phase,
            "sack_clock": round(sack_clock, 2),
            "players": players_snapshot,
            "ball": ball_snapshot,
            "events": events,
        })

    def record_footer(self, outcome: str, telemetry: dict) -> None:
        self.footer = {"outcome": outcome, "telemetry": telemetry}

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        payload = {"header": self.header, "steps": self.steps, "footer": self.footer}
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"Replay saved -> {path}  ({len(self.steps)} steps)")
