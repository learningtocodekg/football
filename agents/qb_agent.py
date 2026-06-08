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
    wr_cut_recovery: int = 0,
    wr_max_speed: float = 9.5,
    cb_x: float | None = None,
    cb_y: float | None = None,
) -> tuple[list[dict], str]:
    """Generate throw options at the target, showing where the WR will actually be at arrival."""
    tx, ty = target
    dist = math.hypot(tx - qb_x, ty - qb_y)
    if dist < 0.01:
        dist = 0.01

    recovery_time = wr_cut_recovery * 0.1  # seconds the WR is still rebuilding speed

    options = []
    for label, frac in OPTION_SPEEDS:
        mph = min_mph + frac * (max_mph - min_mph)
        eta = dist / (mph * MPH_TO_YDS_S)
        # Project WR forward by eta using current heading/speed (constant-speed estimate)
        wr_proj_x = wr_x + math.sin(math.radians(wr_heading)) * wr_speed * eta
        wr_proj_y = wr_y + math.cos(math.radians(wr_heading)) * wr_speed * eta
        wr_offset = math.hypot(tx - wr_proj_x, ty - wr_proj_y)

        opt = {
            "label": label,
            "target": [round(tx, 1), round(ty, 1)],
            "mph": round(mph, 1),
            "eta": round(eta, 2),
            "wr_at_arrival": [round(wr_proj_x, 1), round(wr_proj_y, 1)],
            "wr_offset": round(wr_offset, 1),
        }

        # ── Recovery-aware projection: WR rebuilds to max speed during flight ──
        if wr_cut_recovery > 0:
            if eta <= recovery_time:
                # Entire flight is during recovery — current speed is the estimate
                rec_proj_x, rec_proj_y = wr_proj_x, wr_proj_y
            else:
                # Phase 1: recovery_time seconds at current (slow) speed
                mid_x = wr_x + math.sin(math.radians(wr_heading)) * wr_speed * recovery_time
                mid_y = wr_y + math.cos(math.radians(wr_heading)) * wr_speed * recovery_time
                # Phase 2: remaining time at recovered max speed
                free_time = eta - recovery_time
                rec_proj_x = mid_x + math.sin(math.radians(wr_heading)) * wr_max_speed * free_time
                rec_proj_y = mid_y + math.cos(math.radians(wr_heading)) * wr_max_speed * free_time
            opt["wr_at_arrival_recovered"] = [round(rec_proj_x, 1), round(rec_proj_y, 1)]
            opt["wr_offset_recovered"] = round(math.hypot(tx - rec_proj_x, ty - rec_proj_y), 1)

        # ── CB context relative to the landing zone ──────────────────────────
        if cb_x is not None and cb_y is not None:
            cb_to_land = math.hypot(tx - cb_x, ty - cb_y)
            wr_to_land = wr_offset
            if cb_y > ty + 1.0:
                opt["cb_context"] = "CB in throw lane"
            elif cb_to_land < wr_to_land:
                opt["cb_context"] = "CB may contest"
            else:
                opt["cb_context"] = "CB behind WR"

        options.append(opt)

    show_recovery = wr_cut_recovery > 0
    show_cb = cb_x is not None and cb_y is not None

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
        if show_recovery:
            rec = o["wr_at_arrival_recovered"]
            rec_catchable = "CATCHABLE" if o["wr_offset_recovered"] <= 1.3 else f"MISS by {o['wr_offset_recovered']}yd"
            lines.append(
                f"            w/ accel (recovery): WR at ({rec[0]:.1f},{rec[1]:.1f})   {rec_catchable}"
            )
        if show_cb:
            lines.append(f"            CB_CONTEXT: {o['cb_context']}")
    lines.append("")
    if show_recovery:
        if recovery_time > 0:
            lines.append(
                f"NOTE: WR is in cut_recovery ({wr_cut_recovery} steps ≈ {recovery_time:.1f}s) — "
                "the 'current speed' row assumes the WR stays slow; the 'w/ accel (recovery)' row assumes "
                "the WR rebuilds to max speed after recovery ends. The truth is between them; trust 'w/ accel' "
                "for longer flights, 'current speed' for very fast throws."
            )
    else:
        lines.append("NOTE: WR projection uses current heading/speed — if a cut is pending, actual position will differ.")
    if show_cb:
        lines.append(
            "CB_CONTEXT: 'CB in throw lane' = CB body is between QB and landing zone (a flat throw risks a tip — "
            "use more arc or a different target). 'CB may contest' = CB is closer to the landing spot than the WR. "
            "'CB behind WR' = throw hard and fast, the CB cannot catch up."
        )
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
               wr_heading: float = 0.0, wr_speed: float = 0.0,
               wr_cut_recovery: int = 0, wr_max_speed: float = 9.5,
               cb_x: float | None = None, cb_y: float | None = None) -> dict:
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
            self.min_mph, self.max_mph,
            wr_cut_recovery=wr_cut_recovery, wr_max_speed=wr_max_speed,
            cb_x=cb_x, cb_y=cb_y,
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
