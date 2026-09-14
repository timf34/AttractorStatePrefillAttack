#!/usr/bin/env python3
"""Append steering experiments (add coef x direction at every token, all layers of a
window) to an existing capping config, for positive AND negative coefficients.

Vectors are stored unnormalised (mean bliss turn - mean control turn), so coef = -1
subtracts the full fitted shift; the Gemma runs showed |coef| >= 0.5 over-steers
into token loops, hence the small default doses.

    python -m capped.add_steer capped/configs/llama-3.3-70b_bliss_config.pt \\
        --family bliss_minus_control --windows 40:56 --coefs -0.1,-0.2,-0.3,0.1,0.2,0.3
    python -m capped.add_steer capped/configs/gemma-4-31b_two_component_config.pt \\
        --family prose_minus_control --windows 28:36 --coefs -0.1,-0.2,-0.3

Experiment ids: steer_<family-short>_<a>:<b>-x<coef>, e.g. steer_bliss_40:56-x-0.2.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config")
    p.add_argument("--family", required=True, help="vector name suffix after 'layer_<L>/', e.g. bliss_minus_control")
    p.add_argument("--windows", required=True, help="comma list of a:b layer windows")
    p.add_argument("--coefs", default="-0.1,-0.2,-0.3")
    args = p.parse_args()

    cfg = torch.load(args.config, map_location="cpu", weights_only=False)
    short = args.family.split("_")[0]
    have = {e["id"] for e in cfg["experiments"]}
    added = []
    for w in args.windows.split(","):
        a, b = (int(x) for x in w.split(":"))
        for L in range(a, b):
            if f"layer_{L}/{args.family}" not in cfg["vectors"]:
                raise SystemExit(f"config has no vector layer_{L}/{args.family}")
        for c in (float(x) for x in args.coefs.split(",")):
            eid = f"steer_{short}_{a}:{b}-x{c:g}"
            if eid in have:
                continue
            cfg["experiments"].append({"id": eid, "interventions":
                                       [{"vector": f"layer_{L}/{args.family}", "coef": c} for L in range(a, b)]})
            added.append(eid)
    torch.save(cfg, args.config)
    print(f"{Path(args.config).name}: added {added}; now {len(cfg['experiments'])} experiments")


if __name__ == "__main__":
    main()
