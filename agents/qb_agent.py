import math
from pathlib import Path
from .llm_client import call_llm
from .schema import parse_qb_pass1, parse_qb_pass2
from engine.ball import solve_arc, max_ball_speed, DEFAULT_TARGET_Z

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "qb_system.txt").read_text()
_PASS1_PROMPT  = (Path(__file__).parent / "prompts" / "qb_pass1.txt").read_text()
_PASS2_TEMPLATE = (Path(__file__).parent / "prompts" / "qb_pass2.txt").read_text()

ARC_ORDER = ["bullet", "drive", "touch", "loft"]


def _proj_distance(speed0: float, vmax: float, tau: float,
                   cut_recovery: int = 0, ramp: float = 0.6, safety: float = 0.9) -> float:
    """Forward yards the WR covers in tau seconds, accelerating from speed0 toward vmax. The runner
    drives the WR at full speed in the air, so the landing point must be solved for that motion —
    projecting at the (often post-cut, low) instantaneous speed places the ball short and the WR
    arrives early and stalls. A WR mid-cut-recovery accelerates slower, so the ramp is lengthened by
    the recovery time; `safety` (<1) keeps the model conservative — over-projecting lands the ball
    out of reach (incomplete), under-projecting only costs a brief early arrival (contested)."""
    vmax = max(vmax, speed0)
    ramp_eff = ramp + cut_recovery * 0.1
    if tau <= ramp_eff:
        d = speed0 * tau + 0.5 * (vmax - speed0) * (tau * tau / ramp_eff)
    else:
        d = 0.5 * (speed0 + vmax) * ramp_eff + vmax * (tau - ramp_eff)
    return d * safety


def _meeting_options(
    qb_x: float, qb_y: float,
    wr_x: float, wr_y: float,
    wr_heading: float, wr_speed: float,
    throw_power: float,
    wr_max_speed: float = 9.5,
    wr_cut_recovery: int = 0,
    target_z: float = DEFAULT_TARGET_Z,
    t_now: float = 0.0,
    open_window: tuple[float, float] | None = None,
) -> tuple[list[dict], str]:
    """For each arc, solve for the self-consistent point where a ball released NOW lands on the
    WR's locked line W(tau) = W_now + heading*speed*tau. The unknown is the arrival time tau:
    flight_time_of_arc(distance to W(tau)) == tau. Because flight time grows sublinearly with
    distance while tau grows linearly, there is exactly one crossing — found by bisection.

    This is pure landing geometry. It deliberately does NOT report the CB or separation at the
    meeting point: judging whether the WR is open is the QB's job (pass 1), not ours.
    """
    v_max = max_ball_speed(throw_power)
    hx = math.sin(math.radians(wr_heading))
    hy = math.cos(math.radians(wr_heading))

    def residual(arc: str, tau: float):
        travel = _proj_distance(wr_speed, wr_max_speed, tau, wr_cut_recovery)
        px = wr_x + hx * travel
        py = wr_y + hy * travel
        d = math.hypot(px - qb_x, py - qb_y)
        sol = solve_arc(d, arc, target_z)
        if sol is None:
            return None, px, py, d, None
        return sol[0] - tau, px, py, d, sol[1]  # (flight_time - tau, px, py, dist, launch_speed)

    def meet(arc: str):
        lo, hi = 0.02, 6.0
        flo = residual(arc, lo)[0]
        fhi = residual(arc, hi)[0]
        if flo is None or fhi is None or (flo > 0) == (fhi > 0):
            return None  # no clean crossing in range
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            fm = residual(arc, mid)[0]
            if fm is None:
                hi = mid
                continue
            if (fm > 0) == (flo > 0):
                lo, flo = mid, fm
            else:
                hi = mid
        tau = 0.5 * (lo + hi)
        _, px, py, d, spd = residual(arc, tau)
        feasible = spd is not None and spd <= v_max
        return tau, px, py, d, feasible

    options: list[dict] = []
    unreachable: list[str] = []
    for arc in ARC_ORDER:
        r = meet(arc)
        if r is None or not r[4]:
            unreachable.append(arc)
            continue
        tau, px, py, d, _feas = r
        options.append({
            "arc": arc,
            "label": arc,
            "target": [round(px, 1), round(py, 1)],
            "tau": round(tau, 2),
            "arrival_t": round(t_now + tau, 2),
            "dist": round(d, 1),
            "in_window": open_window is not None and open_window[0] <= tau <= open_window[1],
        })

    win_str = (
        f"  (you said he is open {open_window[0]:.1f}-{open_window[1]:.1f}s from now)"
        if open_window is not None else ""
    )
    lines = [
        f"  Where each arc, released NOW, lands on the WR's path:{win_str}",
        "  arc       meets WR at        arrives in   throw dist",
        "  ------    ---------------    ----------   ----------",
    ]
    for o in options:
        mark = "  <-- arrives in your window" if o["in_window"] else ""
        lines.append(
            f"  {o['arc']:<8}  ({o['target'][0]:.1f},{o['target'][1]:.1f})".ljust(30)
            + f"   +{o['tau']:<4.1f}s    {o['dist']:.1f} yd{mark}"
        )
    if unreachable:
        lines.append(f"  OUT OF RANGE (cannot reach his line on this arc): {', '.join(unreachable)}")
    lines += [
        "",
        "Each row is the self-consistent meeting point: throw that arc now and it lands where the WR's "
        "locked line will be at the arrival time shown (assuming he runs to top speed). Flatter arcs "
        "meet him sooner and shallower; higher arcs meet him deeper and later. Pick the arc whose arrival "
        "falls in the window you identified.",
    ]
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

        # ── Pass 1: the QB's own read — is the WR open, and WHEN? ─────────
        # Raw facts only (no projected separation): judging the window is the QB's job.
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

        # ── Pass 2: landing estimations — where/when each arc meets his line ──
        self.call_count += 1
        options, options_text = _meeting_options(
            qb_x, qb_y, wr_x, wr_y, wr_heading, wr_speed,
            self.throw_power, wr_max_speed=wr_max_speed,
            wr_cut_recovery=wr_cut_recovery,
            t_now=t, open_window=p1.get("open_window"),
        )
        if not options:
            result = {"action": "hold",
                      "reasoning": "WR's path is out of throwing range on every arc",
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
