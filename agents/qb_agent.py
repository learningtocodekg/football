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
    cb_heading: float | None = None,
    cb_speed: float | None = None,
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

        # ── CB projected position at arrival ─────────────────────────────────
        if cb_x is not None and cb_y is not None:
            if cb_heading is not None and cb_speed is not None:
                cb_proj_x = cb_x + math.sin(math.radians(cb_heading)) * cb_speed * eta
                cb_proj_y = cb_y + math.cos(math.radians(cb_heading)) * cb_speed * eta
            else:
                cb_proj_x, cb_proj_y = cb_x, cb_y
            sep_at_arrival = math.hypot(wr_proj_x - cb_proj_x, wr_proj_y - cb_proj_y)
            opt["cb_at_arrival"] = [round(cb_proj_x, 1), round(cb_proj_y, 1)]
            opt["sep_at_arrival"] = round(sep_at_arrival, 1)
            if cb_y > ty + 1.0:
                opt["cb_context"] = "CB in throw lane"
            elif sep_at_arrival < 1.5:
                opt["cb_context"] = "CB arrives tight"
            elif sep_at_arrival < 2.5:
                opt["cb_context"] = "CB contested"
            else:
                opt["cb_context"] = "CB clear"

        options.append(opt)

    show_recovery = wr_cut_recovery > 0
    show_cb = cb_x is not None and cb_y is not None

    lines = [
        "  label     land at         mph    flight   WR at arrival        CB at arrival     sep@arr",
        "  ------    -----------     ---    ------   -------------------  ---------------   -------",
    ] if show_cb else [
        "  label     land at         mph    flight   WR will be at arrival    offset from ball",
        "  ------    -----------     ---    ------   --------------------     ----------------",
    ]
    for o in options:
        catchable = "CATCHABLE" if o["wr_offset"] <= 1.3 else f"MISS by {o['wr_offset']}yd"
        if show_cb:
            sep = o.get("sep_at_arrival", "?")
            cb_arr = o.get("cb_at_arrival", ["?", "?"])
            sep_str = f"{sep:.1f}yd" if isinstance(sep, float) else "?"
            lines.append(
                f"  {o['label']:<8}  ({o['target'][0]:.1f},{o['target'][1]:.1f})    "
                f"{o['mph']:.0f} mph   {o['eta']:.2f}s   "
                f"({o['wr_at_arrival'][0]:.1f},{o['wr_at_arrival'][1]:.1f})  "
                f"({cb_arr[0]:.1f},{cb_arr[1]:.1f})   {sep_str}  [{o.get('cb_context','')}]"
            )
        else:
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
            "CB at arrival = projected CB position when ball lands (constant-speed estimate). "
            "sep@arr = projected WR-CB separation at arrival. "
            ">2.5 yd = open (high prob catch). 1.5-2.5 yd = contested. <1.5 yd = tight, expect PBU. "
            "'CB in throw lane' = CB is between QB and landing zone — risk of tip. "
            "AIM AWAY FROM CB: pick a target_coord within 1.3 yd of the WR's projected position, "
            "on the side AWAY from where the CB will be."
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
               cb_x: float | None = None, cb_y: float | None = None,
               cb_heading: float | None = None, cb_speed: float | None = None) -> dict:
        system = _SYSTEM_PROMPT

        # ── Pass 1: read the field ───────────────────────────────────────
        self.call_count += 1
        raw1 = call_llm(system, observation + "\n\n" + _PASS1_PROMPT,
                        self.model, self.reasoning_effort, self.provider)
        p1 = parse_qb_pass1(raw1)
        if p1 is None:
            self.parse_errors += 1
            print(f"  [QB pass1 parse error] raw=\n{raw1}")
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
            cb_heading=cb_heading, cb_speed=cb_speed,
        )
        pass2_prompt = _PASS2_TEMPLATE.replace("{options_block}", options_text)
        raw2 = call_llm(system, observation + "\n\n" + pass2_prompt,
                        self.model, self.reasoning_effort, self.provider)
        p2 = parse_qb_pass2(raw2, options)
        if p2 is None:
            self.parse_errors += 1
            print(f"  [QB pass2 parse error] raw=\n{raw2}")
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
