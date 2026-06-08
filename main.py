"""
Gridiron Minds — entry point.

Run a play (OpenAI):
    python main.py --seed 42

Run a play with a local Ollama model:
    python main.py --local --seed 42
    python main.py --local --model qwen3:8b --seed 42

Watch the replay:
    python -m render.renderer_pygame replays/play_42.json
"""
import argparse
import sys
from sim.runner import run_play

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_LOCAL_MODEL = "qwen3:8b"


def main():
    p = argparse.ArgumentParser(description="Run a Gridiron Minds play.")
    p.add_argument("--scenario", default="sim/scenarios/a1_basic.yaml")
    p.add_argument("--roster",   default="sim/rosters/default.yaml")
    p.add_argument("--seed",     type=int, default=42)
    p.add_argument("--output",   default=None,
                   help="Path for replay JSON (default: replays/play_<seed>.json)")
    p.add_argument("--local",    action="store_true",
                   help="Use local Ollama model instead of OpenAI")
    p.add_argument("--model",    default=None,
                   help=f"Override QB model name (default for --local: {DEFAULT_LOCAL_MODEL})")
    args = p.parse_args()

    out = args.output or f"replays/play_{args.seed}.json"
    overrides: dict = {}

    if args.local:
        local_model = args.model or DEFAULT_LOCAL_MODEL
        overrides["qb_provider"] = "ollama"
        overrides["qb_model"] = local_model
        overrides["qb_reasoning_effort"] = None
        overrides["wr_provider"] = "ollama"
        overrides["wr_model"] = local_model
        overrides["wr_reasoning_effort"] = None
        overrides["cb_provider"] = "ollama"
        overrides["cb_model"] = local_model
        overrides["cb_reasoning_effort"] = None
        print(f"[local] Using Ollama model: {local_model}")
    elif args.model:
        overrides["qb_model"] = args.model

    run_play(args.scenario, args.roster, args.seed, out,
             scenario_overrides=overrides if overrides else None)


if __name__ == "__main__":
    main()
