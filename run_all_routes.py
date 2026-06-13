"""
Run all route scenarios and save replays to replays/.

Usage:
    python run_all_routes.py              # run all routes with seed 42
    python run_all_routes.py --seed 7     # different seed
    python run_all_routes.py --routes go curl slant  # specific routes only
"""
import argparse
import io
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from sim.runner import run_play

ROSTER = "sim/rosters/default.yaml"

# All routes with their scenario files
ROUTE_SCENARIOS = {
    "slant":       "sim/scenarios/a4_wr_slant.yaml",
    "comeback":    "sim/scenarios/a4_wr_comeback.yaml",
    "go":          "sim/scenarios/a4_wr_go.yaml",
    "double_move": "sim/scenarios/a4_wr_double_move.yaml",
    "curl":        "sim/scenarios/a4_wr_curl.yaml",
    "zig":         "sim/scenarios/a4_wr_zig.yaml",
    "drag":        "sim/scenarios/a4_wr_drag.yaml",
    "corner":      "sim/scenarios/a4_wr_corner.yaml",
    "post_corner": "sim/scenarios/a4_wr_post_corner.yaml",
    "in":          "sim/scenarios/a4_wr_in.yaml",
}


def main():
    p = argparse.ArgumentParser(description="Run all route scenarios.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--routes", nargs="+", choices=list(ROUTE_SCENARIOS), default=None,
                   help="Subset of routes to run (default: all)")
    p.add_argument("--ollama", action="store_true",
                   help="Override all agents to use local Ollama (qwen3:8b)")
    p.add_argument("--model", default="qwen3:8b", help="Ollama model name (default: qwen3:8b)")
    args = p.parse_args()

    routes_to_run = args.routes or list(ROUTE_SCENARIOS)
    seed = args.seed

    ollama_overrides = {
        "wr_model": args.model, "wr_provider": "ollama", "wr_reasoning_effort": None,
        "qb_model": args.model, "qb_provider": "ollama", "qb_reasoning_effort": None,
        "cb_model": args.model, "cb_provider": "ollama", "cb_reasoning_effort": None,
    } if args.ollama else None

    results = {}
    Path("replays").mkdir(exist_ok=True)

    for route in routes_to_run:
        scenario = ROUTE_SCENARIOS[route]
        if not Path(scenario).exists():
            print(f"  [SKIP] {route}: scenario file not found ({scenario})")
            continue

        output = f"replays/{route}_{seed}.json"
        print(f"\n{'='*60}")
        print(f"ROUTE: {route}  |  seed={seed}  ->  {output}")
        print(f"{'='*60}")

        try:
            outcome, telemetry = run_play(scenario, ROSTER, seed, output,
                                          scenario_overrides=ollama_overrides)
            results[route] = {"outcome": outcome, "telemetry": telemetry, "output": output}
        except Exception as e:
            print(f"  [ERROR] {route}: {e}")
            results[route] = {"outcome": "ERROR", "error": str(e)}

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for route, r in results.items():
        outcome = r.get("outcome", "?")
        tel = r.get("telemetry", {})
        sep_throw = tel.get("sep_at_throw", "?")
        sep_catch = tel.get("sep_at_catch", "?")
        throw_t = tel.get("throw_t", "?")
        print(f"  {route:<14} {outcome:<14} sep@throw={sep_throw} -> sep@catch={sep_catch} yd  throw_t={throw_t}s")

    return results


if __name__ == "__main__":
    main()
