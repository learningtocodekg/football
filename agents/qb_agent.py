import math
from pathlib import Path
from .llm_client import call_llm
from .schema import parse_qb_pass1, parse_qb_pass2

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "qb_system.txt").read_text()
_PASS1_PROMPT  = (Path(__file__).parent / "prompts" / "qb_pass1.txt").read_text()
_PASS2_TEMPLATE = (Path(__file__).parent / "prompts" / "qb_pass2.txt").read_text()

MPH_TO_YDS_S = 1.46667

# Speeds offered as options in pass 2: bullet, hard, medium, soft, lob
OPTION_SPEEDS = [
    ("bullet",  1.00),   # fraction of max_mph
    ("hard",    0.80),
    ("medium",  0.60),
    ("soft",    0.40),
    ("lob",     0.20),   # fraction above MIN toward max
]


def _build_options(
    target: list[float],
    qb_x: float,
    qb_y: float,
    wr_x: float,
    wr_y: float,
    wr_heading: float,
    wr_speed: float,
    min_mph: float,
    max_mph: float,
) -> tuple[list[dict], str]:
    """Generate throw options at the target, showing where the WR will actually be at arrival."""
    tx, ty = target
    dist = math.hypot(tx - qb_x, ty - qb_y)
    if dist < 0.01:
        dist = 0.01

    options = []
    for label, frac in OPTION_SPEEDS:
        mph = min_mph + frac * (max_mph - min_mph)
        eta = dist / (mph * MPH_TO_YDS_S)
        # Project WR forward by eta using current heading/speed
        wr_proj_x = wr_x + math.sin(math.radians(wr_heading)) * wr_speed * eta
        wr_proj_y = wr_y + math.cos(math.radians(wr_heading)) * wr_speed * eta
        wr_offset = math.hypot(tx - wr_proj_x, ty - wr_proj_y)
        options.append({
            "label": label,
            "target": [round(tx, 1), round(ty, 1)],
            "mph": round(mph, 1),
            "eta": round(eta, 2),
            "wr_at_arrival": [round(wr_proj_x, 1), round(wr_proj_y, 1)],
            "wr_offset": round(wr_offset, 1),
        })

    lines = [
        "  label     land at         mph    flight   WR will be at arrival    offset from ball",
        "  ------    -----------     ---    ------   --------------------     ----------------",
    ]
    for o in options:
        catchable = "CATCHABLE" if o["wr_offset"] <= 1.3 else f"MISS by {o['wr_offset']}yd"
        lines.append(
            f"  {o['label']:<8}  ({o['target'][0]:.1f},{o['target'][1]:.1f})    "
            f"{o['mph']:.0f} mph   {o['eta']:.2f}s   "
            f"({o['wr_at_arrival'][0]:.1f},{o['wr_at_arrival'][1]:.1f})   {catchable}"
        )
    lines.append("")
    lines.append("NOTE: WR projection uses current heading/speed — if a cut is pending, actual position will differ.")
    return options, "\n".join(lines)


class QBAgent:
    def __init__(
        self,
        model: str = "gpt-5-nano",
        reasoning_effort: str | None = "low",
        provider: str = "openai",
        min_mph: float = 20.0,
        max_mph: float = 54.3,
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.min_mph = min_mph
        self.max_mph = max_mph
        self.last_action: dict = {"action": "hold", "reasoning": "initializing"}
        self.call_count = 0
        self.parse_errors = 0

    def decide(self, observation: str, qb_x: float, qb_y: float,
               wr_x: float = 0.0, wr_y: float = 0.0,
               wr_heading: float = 0.0, wr_speed: float = 0.0) -> dict:
        system = _SYSTEM_PROMPT

        # ── Pass 1: read the field ───────────────────────────────────────
        self.call_count += 1
        raw1 = call_llm(system, observation + "\n\n" + _PASS1_PROMPT,
                        self.model, self.reasoning_effort, self.provider)
        p1 = parse_qb_pass1(raw1)
        if p1 is None:
            self.parse_errors += 1
            print(f"  [QB pass1 parse error] raw={raw1[:120]!r}")
            return {"action": "hold", "reasoning": "parse_error", "pass1": None}

        if p1["action"] == "hold":
            result = {"action": "hold", "reasoning": p1["reasoning"], "pass1": p1}
            self.last_action = result
            return result

        # ── Pass 2: commit or hold ───────────────────────────────────────
        self.call_count += 1
        options, options_text = _build_options(
            p1["target_area"], qb_x, qb_y,
            wr_x, wr_y, wr_heading, wr_speed,
            self.min_mph, self.max_mph
        )
        pass2_prompt = _PASS2_TEMPLATE.replace("{options_block}", options_text)
        raw2 = call_llm(system, observation + "\n\n" + pass2_prompt,
                        self.model, self.reasoning_effort, self.provider)
        p2 = parse_qb_pass2(raw2, options)
        if p2 is None:
            self.parse_errors += 1
            print(f"  [QB pass2 parse error] raw={raw2[:120]!r}")
            return {"action": "hold", "reasoning": "parse_error", "pass1": p1}

        if p2["action"] == "hold":
            result = {"action": "hold", "reasoning": p2["reasoning"], "pass1": p1}
            self.last_action = result
            return result

        result = {
            "action": "throw",
            "target_coord": p2["target_coord"],
            "ball_speed_mph": p2["ball_speed_mph"],
            "reasoning": p2["reasoning"],
            "pass1": p1,
        }
        self.last_action = result
        return result
