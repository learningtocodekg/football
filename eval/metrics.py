"""Aggregate outcomes + telemetry across a directory of replay JSONs.

Usage:  python -m eval.metrics [replays_dir]   (default: replays)

Replaces hand-tabulating round results in problems.md: run a suite, point this
at the replay directory, get outcome counts, catch rate, separation/throw-time
averages, and parse-error totals in one shot.
"""
import argparse
import glob
import json
import os
from collections import Counter


def _fmt(v) -> str:
    return f"{v:.2f}" if isinstance(v, (int, float)) else "-"


def load_replays(path: str) -> list[tuple[str, str | None, dict]]:
    rows = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        with open(f) as fh:
            data = json.load(fh)
        footer = data.get("footer", {})
        rows.append((os.path.basename(f), footer.get("outcome"), footer.get("telemetry", {})))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Aggregate replay outcomes + telemetry.")
    ap.add_argument("path", nargs="?", default="replays", help="directory of replay JSONs")
    args = ap.parse_args()

    rows = load_replays(args.path)
    if not rows:
        print(f"No replay JSONs found in {args.path!r}")
        return

    outcomes: Counter = Counter()
    qb_err = wr_err = cb_err = 0
    broken = 0
    seps: list[float] = []
    throw_ts: list[float] = []

    print(f"{'file':<28} {'outcome':<13} {'maxSep':>7} {'throw_t':>8} {'cb_intent':>10}  errors(q/w/c)")
    print("-" * 86)
    for name, outcome, tel in rows:
        outcomes[outcome or "UNKNOWN"] += 1
        q = tel.get("qb_parse_errors", 0)
        w = tel.get("wr_parse_errors", 0)
        c = tel.get("cb_parse_errors", 0)
        qb_err += q
        wr_err += w
        cb_err += c
        if tel.get("broken_play"):
            broken += 1
        ms = tel.get("max_separation")
        tt = tel.get("throw_t")
        if isinstance(ms, (int, float)):
            seps.append(ms)
        if isinstance(tt, (int, float)):
            throw_ts.append(tt)
        print(f"{name:<28} {str(outcome):<13} {_fmt(ms):>7} {_fmt(tt):>8} "
              f"{str(tel.get('cb_intent', '')):>10}  {q}/{w}/{c}")

    n = len(rows)
    print("\n=== AGGREGATE ===")
    print(f"plays: {n}")
    for k, v in outcomes.most_common():
        print(f"  {k:<13} {v:>3}  ({100 * v / n:.0f}%)")
    print(f"catch rate: {100 * outcomes.get('CATCH', 0) / n:.0f}%")
    if seps:
        print(f"avg max_separation: {sum(seps) / len(seps):.2f} yd")
    if throw_ts:
        print(f"avg throw_t: {sum(throw_ts) / len(throw_ts):.2f} s")
    print(f"broken plays: {broken}")
    print(f"parse errors  QB:{qb_err}  WR:{wr_err}  CB:{cb_err}")


if __name__ == "__main__":
    main()
