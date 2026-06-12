import math
from pathlib import Path
from .llm_client import call_llm
from .schema import parse_qb_pass1, parse_qb_pass2
from engine.ball import (
    solve_arc, max_ball_speed, max_range, ARC_ANGLES,
    DEFAULT_TARGET_Z, YD_S_TO_MPH,
)
from engine.resolution import CB_VERTICAL_REACH

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "qb_system.txt").read_text()
_PASS1_PROMPT  = (Path(__file__).parent / "prompts" / "qb_pass1.txt").read_text()
_PASS2_TEMPLATE = (Path(__file__).parent / "prompts" / "qb_pass2.txt").read_text()

ARC_ORDER = ["bullet", "drive", "touch", "loft"]
LANE_NEAR_DIST = 1.5  # CB within this of the flight line counts as "in the lane"


def _lane_note(
    qb_x: float, qb_y: float,
    tx: float, ty: float,
    t_flight: float,
    cb_x: float, cb_y: float,
    cb_heading: float | None, cb_speed: float | None,
    arc: str,
    target_z: float,
) -> str:
    """Where does the ball pass relative to the CB mid-flight? Heights from the arc parabola."""
    vx = tx - qb_x
    vy = ty - qb_y
    length_sq = vx * vx + vy * vy
    if length_sq < 1e-9:
        return ""
    frac = ((cb_x - qb_x) * vx + (cb_y - qb_y) * vy) / length_sq
    if frac <= 0.05 or frac >= 0.95:
        return "lane clear"
    t_pass = frac * t_flight
    # CB position when the ball passes his stretch of the lane
    if cb_heading is not None and cb_speed is not None:
        cbx_t = cb_x + math.sin(math.radians(cb_heading)) * cb_speed * t_pass
        cby_t = cb_y + math.cos(math.radians(cb_heading)) * cb_speed * t_pass
    else:
        cbx_t, cby_t = cb_x, cb_y
    px = qb_x + frac * vx
    py = qb_y + frac * vy
    lane_dist = math.hypot(cbx_t - px, cby_t - py)
    if lane_dist > LANE_NEAR_DIST:
        return "lane clear"
    # Ball height at that point of the parabola
    from engine.ball import RELEASE_Z, G
    dist = math.sqrt(length_sq)
    theta = math.radians(ARC_ANGLES[arc])
    v_h = dist / t_flight
    z_pass = RELEASE_Z + v_h * math.tan(theta) * t_pass - 0.5 * G * t_pass ** 2
    if z_pass > CB_VERTICAL_REACH:
        return f"clears CB in lane (ball z={z_pass:.1f} over his {CB_VERTICAL_REACH:.1f} reach)"
    return f"!! ball passes CB at z={z_pass:.1f} — within reach, TIP/PICK RISK"


def _build_options(
    target: list[float],
    qb_x: float,
    qb_y: float,
    wr_x: float,
    wr_y: float,
    wr_heading: float,
    wr_speed: float,
    throw_power: float,
    wr_cut_recovery: int = 0,
    wr_max_speed: float = 9.5,
    cb_x: float | None = None,
    cb_y: float | None = None,
    cb_heading: float | None = None,
    cb_speed: float | None = None,
    target_z: float = DEFAULT_TARGET_Z,
    t_now: float = 0.0,
    open_window: tuple[float, float] | None = None,
) -> tuple[list[dict], str]:
    """Generate one throw option per arc at the target, with real 3D flight physics."""
    tx, ty = target
    dist = math.hypot(tx - qb_x, ty - qb_y)
    if dist < 0.01:
        dist = 0.01

    v_max = max_ball_speed(throw_power)

    options = []
    out_of_range = []
    for arc in ARC_ORDER:
        sol = solve_arc(dist, arc, target_z)
        if sol is None:
            out_of_range.append(arc)
            continue
        t_flight, speed, peak_z = sol
        if speed > v_max:
            out_of_range.append(arc)
            continue
        eta = t_flight
        arrival_t = round(t_now + t_flight, 2)
        in_window = (
            open_window is not None and open_window[0] <= arrival_t <= open_window[1]
        )
        # Project WR forward by eta using current heading/speed (constant-speed estimate)
        wr_proj_x = wr_x + math.sin(math.radians(wr_heading)) * wr_speed * eta
        wr_proj_y = wr_y + math.cos(math.radians(wr_heading)) * wr_speed * eta
        wr_offset = math.hypot(tx - wr_proj_x, ty - wr_proj_y)

        opt = {
            "label": arc,
            "target": [round(tx, 1), round(ty, 1)],
            "arc": arc,
            "t_flight": round(t_flight, 2),
            "mph": round(speed * YD_S_TO_MPH, 1),
            "peak_z": round(peak_z, 1),
            "eta": round(eta, 2),
            "arrival_t": arrival_t,
            "in_window": in_window,
            "wr_at_arrival": [round(wr_proj_x, 1), round(wr_proj_y, 1)],
            "wr_offset": round(wr_offset, 1),
        }

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
            opt["lane"] = _lane_note(qb_x, qb_y, tx, ty, t_flight,
                                     cb_x, cb_y, cb_heading, cb_speed, arc, target_z)

        options.append(opt)

    show_cb = cb_x is not None and cb_y is not None

    win_str = (
        f"  (you want the ball to ARRIVE between t={open_window[0]:.1f}s and t={open_window[1]:.1f}s)"
        if open_window is not None else ""
    )
    lines = [
        f"  Arc options to ({tx:.1f},{ty:.1f}) - throw distance {dist:.1f} yd, catch height z={target_z:.1f}.{win_str}",
    ]
    if show_cb:
        lines += [
            "  arc       flight   arrives@   WR at arrival        CB at arrival      sep@arr",
            "  ------    ------   --------   -------------------  -----------------  -------",
        ]
        for o in options:
            sep = o.get("sep_at_arrival")
            cb_arr = o.get("cb_at_arrival", [0.0, 0.0])
            sep_str = f"{sep:.1f}yd" if isinstance(sep, float) else "?"
            mark = "  <-- arrives in your window" if o.get("in_window") else ""
            note = o.get("lane", "")
            note_str = f"  [{note}]" if note and "clear" not in note else (f"  [{note}]" if note else "")
            lines.append(
                f"  {o['label']:<8}  {o['t_flight']:.2f}s   t={o['arrival_t']:<5.1f}"
                f"  ({o['wr_at_arrival'][0]:.1f},{o['wr_at_arrival'][1]:.1f})  "
                f"({cb_arr[0]:.1f},{cb_arr[1]:.1f})   {sep_str:>6}{note_str}{mark}"
            )
    else:
        lines += [
            "  arc       flight   arrives@   WR at arrival",
            "  ------    ------   --------   -------------------",
        ]
        for o in options:
            lines.append(
                f"  {o['label']:<8}  {o['t_flight']:.2f}s   t={o['arrival_t']:<5.1f}"
                f"  ({o['wr_at_arrival'][0]:.1f},{o['wr_at_arrival'][1]:.1f})"
            )
    if out_of_range:
        lines.append(f"  OUT OF RANGE for your arm at this distance: {', '.join(out_of_range)}")
    lines += [
        "",
        "arrives@ = when the ball lands if you throw now (current time + flight time).",
    ]
    if show_cb:
        lines.append(
            "WR/CB at arrival are projected to that time (WR on his locked heading at current speed - he may "
            "still be accelerating; CB chasing at current speed). sep@arr is center-to-center: 1.8+ clean, "
            "1.0-1.8 contested, 1.0 or less the CB wins. A [TIP/PICK RISK] note means the ball passes within "
            "the CB's reach mid-flight - prefer a higher arc or a spot away from him."
        )
    return options, "\n".join(lines)


class QBAgent:
    def __init__(
        self,
        model: str = "gpt-5-nano",
        reasoning_effort: str | None = "low",
        provider: str = "openai",
        throw_power: float = 85.0,
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.throw_power = throw_power
        self.last_action: dict = {"action": "hold", "reasoning": "initializing"}
        self.call_count = 0
        self.parse_errors = 0

    def decide(self, observation: str, qb_x: float, qb_y: float,
               wr_x: float = 0.0, wr_y: float = 0.0,
               wr_heading: float = 0.0, wr_speed: float = 0.0,
               wr_cut_recovery: int = 0, wr_max_speed: float = 9.5,
               cb_x: float | None = None, cb_y: float | None = None,
               cb_heading: float | None = None, cb_speed: float | None = None,
               t: float = 0.0) -> dict:
        system = _SYSTEM_PROMPT

        # ── Pass 1: anticipation — is there a window, when/where? ─────────
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

        # ── Pass 2: pick the arc + placement, or hold ────────────────────
        self.call_count += 1
        options, options_text = _build_options(
            p1["target_area"], qb_x, qb_y,
            wr_x, wr_y, wr_heading, wr_speed,
            self.throw_power,
            wr_cut_recovery=wr_cut_recovery, wr_max_speed=wr_max_speed,
            cb_x=cb_x, cb_y=cb_y,
            cb_heading=cb_heading, cb_speed=cb_speed,
            t_now=t, open_window=p1.get("open_window"),
        )
        if not options:
            result = {"action": "hold",
                      "reasoning": "target out of throwing range for every arc",
                      "pass1": p1}
            self.last_action = result
            return result
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
            "arc": p2["arc"],
            "target_z": p2["target_z"],
            "reasoning": p2["reasoning"],
            "pass1": p1,
        }
        self.last_action = result
        return result
