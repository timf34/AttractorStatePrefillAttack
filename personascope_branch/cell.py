#!/usr/bin/env python3
"""Run personascope's battery at ONE branch point of an attractor transcript.

Examples:
    python -m personascope_branch.cell --model gpt-4.1 --condition bliss --k 15
    python -m personascope_branch.cell --model opus-4.8 --condition baseline --k 0
    python -m personascope_branch.cell --model deepseek-v4 --condition neutral --k 30 --dry-run
"""

from __future__ import annotations

import argparse
import json

from personascope_branch.bridge import BRANCH_MODELS, run_cell


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True, choices=sorted(BRANCH_MODELS))
    p.add_argument("--condition", required=True, choices=["bliss", "neutral", "baseline"])
    p.add_argument("--k", type=int, required=True,
                   help="branch depth in transcript turns (0 = baseline)")
    p.add_argument("--n-samples", type=int, default=4)
    p.add_argument("--tier", default="core")
    p.add_argument("--out-root", default="results_personascope")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    summary = run_cell(
        model_alias=args.model,
        condition=args.condition,
        k=args.k,
        out_root=args.out_root,
        n_samples=args.n_samples,
        tier=args.tier,
        seed=args.seed,
        dry_run=args.dry_run,
    )
    print(json.dumps({name: summary[name] for name in
                      ("persona", "model", "k", "probes_run") if name in summary},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
