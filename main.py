"""
Gridiron Minds — entry point.

Run a play:
    python main.py --seed 42

Watch the replay:
    python -m render.renderer_pygame replays/play_42.json
"""
import argparse
from sim.runner import run_play


def main():
    p = argparse.ArgumentParser(description="Run a Gridiron Minds play.")
    p.add_argument("--scenario", default="sim/scenarios/a1_basic.yaml")
    p.add_argument("--roster",   default="sim/rosters/default.yaml")
    p.add_argument("--seed",     type=int, default=42)
    p.add_argument("--output",   default=None,
                   help="Path for replay JSON (default: replays/play_<seed>.json)")
    args = p.parse_args()

    out = args.output or f"replays/play_{args.seed}.json"
    run_play(args.scenario, args.roster, args.seed, out)


if __name__ == "__main__":
    main()
