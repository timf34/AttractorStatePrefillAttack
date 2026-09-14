#!/usr/bin/env python3
"""Turn one experiment of a capping config (paper format, as used by run_capped)
into an EasySteer GGUF + SteeringSpec JSON.

  capping experiments  (interventions with "cap")  -> algorithm "cap", one GGUF with
      direction.L = v_hat * (TAU_OFFSET + tau) per layer (see cap.py), scale 1.0,
      a single VectorSpec over all capped layers.
  steering experiments (interventions with "coef") -> algorithm "direct", one GGUF with
      direction.L = the raw fitted shift per layer, scale = coef (same for all layers).

    python -m capped.easysteer.export --config capped/configs/gemma-4-31b_two_component_config.pt \\
        --experiment two_28:36-c0.75 --out-dir steer_vectors

Prints the spec path. The spec's "source" is an ABSOLUTE path on the machine that
runs vllm serve, so run this on the pod (or pass --source-root).
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import numpy as np
import torch

TAU_OFFSET = 1.0e4  # keep in sync with cap.py


def build(config_path: str, experiment: str, out_dir: str, source_root: str | None = None) -> str:
    cfg = torch.load(config_path, map_location="cpu", weights_only=False)
    exp = next((e for e in cfg["experiments"] if e["id"] == experiment), None)
    if exp is None:
        raise SystemExit(f"experiment {experiment!r} not in {config_path}")
    ivs = exp["interventions"]
    is_cap = all("cap" in iv for iv in ivs)
    is_steer = all("coef" in iv for iv in ivs)
    if not (is_cap or is_steer):
        raise SystemExit("mixed or unknown intervention types in experiment")

    import gguf
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]", "-", f"{Path(config_path).stem}__{experiment}")
    gpath = out / f"{stem}.gguf"
    w = gguf.GGUFWriter(str(gpath), arch="steer")
    layers = []
    coef = None
    for iv in ivs:
        vd = cfg["vectors"][iv["vector"]]
        L = int(vd["layer"])
        vec = vd["vector"].to(torch.float32).reshape(-1)
        if is_cap:
            tau = float(iv["cap"])
            if TAU_OFFSET + tau <= 0:
                raise SystemExit(f"tau {tau} too negative for TAU_OFFSET {TAU_OFFSET}")
            enc = vec / (vec.norm() + 1e-8) * (TAU_OFFSET + tau)
        else:
            c = float(iv["coef"])
            if coef is None:
                coef = c
            elif abs(c - coef) > 1e-9:
                raise SystemExit("steering experiment has per-layer coefficients; EasySteer scale is per spec")
            enc = vec
        w.add_tensor(f"direction.{L}", enc.numpy().astype(np.float32))
        layers.append(L)
    w.write_header_to_file(); w.write_kv_data_to_file(); w.write_tensors_to_file(); w.close()

    src = str(gpath.resolve()) if source_root is None else os.path.join(source_root, gpath.name)
    spec = {"vectors": [{
        "source": src,
        "algorithm": "cap" if is_cap else "direct",
        "scale": 1.0 if is_cap else float(coef),
        "layers": sorted(layers),
        "apply": {"prompt": "all", "generation": "all"},
    }], "conflict": "sequential"}
    spath = out / f"{stem}.json"
    spath.write_text(json.dumps(spec, indent=1))
    return str(spath)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", required=True)
    p.add_argument("--experiment", required=True)
    p.add_argument("--out-dir", default="steer_vectors")
    p.add_argument("--source-root", default=None, help="directory path to write into the spec instead of the local absolute path")
    args = p.parse_args()
    print(build(args.config, args.experiment, args.out_dir, args.source_root))


if __name__ == "__main__":
    main()
