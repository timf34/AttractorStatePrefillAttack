#!/usr/bin/env python3
"""Where does the bliss state live in a model's activation space, relative to its
Assistant Axis? CPU-only, from capped/turn_activations.py output.

  bliss turns   = prefilled (seed) turns of the deep-prefill episodes
  control turns = generated turns of the unprefilled control episodes
  bliss_dir[L]  = mean(bliss) - mean(control) at layer L

Reports, per layer: cos(bliss_dir, assistant axis), how far bliss and control
are apart along the axis (d') versus along bliss_dir itself, and (optionally)
which released role vectors the bliss direction aligns with. Also writes a
paper-format capping config whose vectors are the bliss directions, with caps
at a quantile of the CONTROL turns' projection — i.e. "never be more bliss-ward
than ordinary conversation" — for run_capped --config-path.

    python -m capped.diagnose --model gemma-4-31b --acts results_capped/acts \\
        --roles --windows 28:36,30:34,43:51 --out capped/configs/gemma-4-31b_bliss_config.pt
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import torch
import torch.nn.functional as F

from .common import ROOT, hf_download, load_axis, spec_for


def load_acts(acts_dir: Path, model_prefix: str):
    bliss, control, cont = [], [], []
    for f in sorted(glob.glob(str(acts_dir / f"{model_prefix}*.pt"))):
        d = torch.load(f, map_location="cpu", weights_only=False)
        a = d["acts"].float()
        for i, t in enumerate(d["turns"]):
            if d["condition"] == "control" and t["origin"] == "generated":
                control.append(a[i])
            elif d["condition"] != "control" and t["origin"] == "seed":
                bliss.append(a[i])
            elif d["condition"] != "control" and t["origin"] == "generated":
                cont.append(a[i])
    st = lambda xs: torch.stack(xs) if xs else None  # noqa: E731
    return st(bliss), st(control), st(cont)


def dprime(a: torch.Tensor, b: torch.Tensor) -> float:
    """Separation of two 1-D samples in pooled-sd units."""
    sp = ((a.var() + b.var()) / 2).sqrt() + 1e-6
    return float((a.mean() - b.mean()).abs() / sp)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--acts", default="results_capped/acts")
    p.add_argument("--prefix", default=None, help="acts file prefix (default: <model>-cap__)")
    p.add_argument("--axis-path", default=None)
    p.add_argument("--roles", action="store_true", help="download the released role vectors and rank them")
    p.add_argument("--role-layers", default="30,43,54")
    p.add_argument("--windows", default="28:36,30:34,43:51")
    p.add_argument("--control-quantile", type=float, default=0.75,
                   help="cap = this quantile of control turns' projection onto bliss_dir")
    p.add_argument("--out", default=None, help="bliss-direction capping config .pt")
    p.add_argument("--report", default=None, help="write the tables as JSON here")
    args = p.parse_args()

    spec = spec_for(args.model)
    axis = load_axis(spec, args.axis_path)          # (L, H), toward the Assistant
    n_layers = axis.shape[0]
    bliss, control, cont = load_acts(Path(args.acts), args.prefix or f"{args.model}-cap__")
    if bliss is None or control is None:
        raise SystemExit("need both deep-prefill and control episodes in --acts")
    print(f"{len(bliss)} bliss (prefill) turns, {len(control)} control turns, "
          f"{0 if cont is None else len(cont)} capped-continuation turns; {n_layers} layers")

    rows = []
    bliss_dir = torch.zeros_like(axis)
    caps = {}
    for L in range(n_layers):
        a = F.normalize(axis[L], dim=0)
        bd = bliss[:, L].mean(0) - control[:, L].mean(0)
        bliss_dir[L] = bd
        u = F.normalize(bd, dim=0)
        pa_b, pa_c = bliss[:, L] @ a, control[:, L] @ a
        pu_b, pu_c = bliss[:, L] @ u, control[:, L] @ u
        row = {"layer": L, "cos_bliss_axis": float(F.cosine_similarity(bd, axis[L], dim=0)),
               "bliss_norm": float(bd.norm()),
               "axis_proj_bliss": float(pa_b.mean()), "axis_proj_control": float(pa_c.mean()),
               "dprime_axis": dprime(pa_b, pa_c), "dprime_blissdir": dprime(pu_b, pu_c),
               "cap_control_q": float(torch.quantile(pu_c, args.control_quantile)),
               "blissdir_proj_bliss": float(pu_b.mean()), "blissdir_proj_control": float(pu_c.mean())}
        if cont is not None:
            row["axis_proj_capped_cont"] = float((cont[:, L] @ a).mean())
            row["blissdir_proj_capped_cont"] = float((cont[:, L] @ u).mean())
        rows.append(row)
        caps[L] = row["cap_control_q"]

    print("\nlayer  cos(bliss_dir,axis)  axis: bliss  control  d'   |  bliss_dir: bliss  control  d'   cap(q)")
    for r in rows:
        if r["layer"] % 3 == 0 or r["layer"] in (43, 47, 50):
            print(f"{r['layer']:>5}  {r['cos_bliss_axis']:>+18.3f}  {r['axis_proj_bliss']:>10.1f} {r['axis_proj_control']:>8.1f} {r['dprime_axis']:>5.2f}"
                  f"  |  {r['blissdir_proj_bliss']:>14.1f} {r['blissdir_proj_control']:>8.1f} {r['dprime_blissdir']:>5.2f}  {r['cap_control_q']:>7.1f}")

    role_table = {}
    if args.roles and spec.get("axis"):
        repo, axis_file = spec["axis"]
        rel = axis_file.rsplit("/", 1)[0]
        from huggingface_hub import HfApi
        files = [f for f in HfApi().list_repo_files(repo, repo_type="dataset") if f.startswith(rel + "/role_vectors/")]
        default = torch.load(hf_download(*spec["default_vector"]), map_location="cpu", weights_only=False).float()
        print(f"\n{len(files)} role vectors; cosine of (role - default) with bliss_dir")
        role_layers = [int(x) for x in args.role_layers.split(",")]
        roles = {}
        for f in files:
            v = torch.load(hf_download(repo, f), map_location="cpu", weights_only=False).float()
            roles[Path(f).stem] = v
        for L in role_layers:
            sims = {r: float(F.cosine_similarity(v[L] - default[L], bliss_dir[L], dim=0)) for r, v in roles.items()}
            top = sorted(sims.items(), key=lambda kv: -kv[1])
            role_table[L] = top
            print(f"  L{L}: most bliss-like {[(r, round(s, 2)) for r, s in top[:10]]}")
            print(f"       least          {[(r, round(s, 2)) for r, s in top[-5:]]}")

    if args.out:
        windows = [tuple(int(x) for x in w.split(":")) for w in args.windows.split(",")]
        vectors = {f"layer_{L}/bliss_minus_control": {"layer": L, "vector": bliss_dir[L].to(torch.bfloat16)}
                   for L in range(n_layers)}
        experiments = [{"id": f"bliss_{a}:{b}-c{args.control_quantile:g}",
                        "interventions": [{"vector": f"layer_{L}/bliss_minus_control", "cap": caps[L]} for L in range(a, b)]}
                       for a, b in windows]
        cfg = {"vectors": vectors, "experiments": experiments,
               "meta": {"model": spec["hf"], "note": "vector = mean(bliss prefill turns) - mean(control turns); "
                        f"cap = q{args.control_quantile:g} of control turns' projection (ceiling on bliss-ward drift)",
                        "n_bliss": len(bliss), "n_control": len(control)}}
        out = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        torch.save(cfg, out)
        print(f"\nwrote {out}: experiments {[e['id'] for e in experiments]}")
    if args.report:
        Path(args.report).write_text(json.dumps({"layers": rows, "roles": role_table}, indent=1))
        print(f"wrote {args.report}")


if __name__ == "__main__":
    main()
