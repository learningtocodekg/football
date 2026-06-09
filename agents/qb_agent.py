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
) -> tuple[list[dict], str]:
    """Generate one throw option per arc at the target, with real 3D flight physics."""
    tx, ty = target
    dist = math.hypot(tx - qb_x, ty - qb_y)
    if dist < 0.01:
        dist = 0.01

    v_max = max_ball_speed(throw_power)
    recovery_time = wr_cut_recovery * 0.1  # seconds the WR is still rebuilding speed

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
            "wr_at_arrival": [round(wr_proj_x, 1), round(wr_proj_y, 1)],
            "wr_offset": round(wr_offset, 1),
        }

        # ── Recovery-aware projection: WR rebuilds to max speed during flight ──
        if wr_cut_recovery > 0:
            if eta <= recovery_time:
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
            if sep_at_arrival < 1.5:
                opt["cb_context"] = "CB arrives tight"
            elif sep_at_arrival < 2.5:
                opt["cb_context"] = "CB contested"
            else:
                opt["cb_context"] = "CB clear"
            opt["lane"] = _lane_note(qb_x, qb_y, tx, ty, t_flight,
                                     cb_x, cb_y, cb_heading, cb_speed, arc, target_z)

        options.append(opt)

    show_recovery = wr_cut_recovery > 0
    show_cb = cb_x is not None and cb_y is not None

    lines = [
        f"  Throw options to ({tx:.1f},{ty:.1f}) — {dist:.1f} yd, catch height z={target_z:.1f} (you may change target_z, 0.3–3.0):",
    ]
    if show_cb:
        lines += [
            "  arc       flight   mph   peak_z   WR at arrival        CB at arrival     sep@arr",
            "  ------    ------   ---   ------   -------------------  ---------------   -------",
        ]
    else:
        lines += [
            "  arc       flight   mph   peak_z   WR will be at arrival    offset from ball",
            "  ------    ------   ---   ------   --------------------     ----------------",
        ]
    for o in options:
        catchable = "CATCHABLE" if o["wr_offset"] <= 1.3 else f"MISS by {o['wr_offset']}yd"
        if show_cb:
            sep = o.get("sep_at_arrival", "?")
            cb_arr = o.get("cb_at_arrival", ["?", "?"])
            sep_str = f"{sep:.1f}yd" if isinstance(sep, float) else "?"
            lines.append(
                f"  {o['label']:<8}  {o['t_flight']:.2f}s   {o['mph']:.0f}    {o['peak_z']:>4.1f}    "
                f"({o['wr_at_arrival'][0]:.1f},{o['wr_at_arrival'][1]:.1f})  "
                f"({cb_arr[0]:.1f},{cb_arr[1]:.1f})   {sep_str}  [{o.get('cb_context','')}; {o.get('lane','')}]"
            )
        else:
            lines.append(
                f"  {o['label']:<8}  {o['t_flight']:.2f}s   {o['mph']:.0f}    {o['peak_z']:>4.1f}    "
                f"({o['wr_at_arrival'][0]:.1f},{o['wr_at_arrival'][1]:.1f})   {catchable}"
            )
        if show_recovery and "wr_at_arrival_recovered" in o:
            rec = o["wr_at_arrival_recovered"]
            rec_catchable = "CATCHABLE" if o["wr_offset_recovered"] <= 1.3 else f"MISS by {o['wr_offset_recovered']}yd"
            lines.append(
                f"            w/ accel (recovery): WR at ({rec[0]:.1f},{rec[1]:.1f})   {rec_catchable}"
            )
    if out_of_range:
        lines.append(f"  OUT OF RANGE for your arm at this distance: {', '.join(out_of_range)}")
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
            "The lane note tells you whether the ball passes the CB at a reachable height mid-flight — "
            "a ball within his vertical reach in the lane can be tipped or picked before it ever gets to the WR. "
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
            self.throw_power,
            wr_cut_recovery=wr_cut_recovery, wr_max_speed=wr_max_speed,
            cb_x=cb_x, cb_y=cb_y,
            cb_heading=cb_heading, cb_speed=cb_speed,
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
