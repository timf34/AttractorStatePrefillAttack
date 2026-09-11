#!/usr/bin/env python3
"""Is one Assistant-Axis dimension enough? Persona-space PCA vs the bliss state (CPU).

Builds persona space per layer from the released role vectors (275 roles, mean
activation per role), z-scored per dimension across roles as in
GemmaAssistantAxis/GEMMA_GENERATIONS.md (raw PCA is dominated by Gemma's
massive-activation coordinates), and asks, per layer:

  * where the Assistant Axis and the bliss direction (bliss prefill turns minus
    control turns) sit in that PC basis (cosine with each PC);
  * how much of the bliss shift lies inside persona space at all (fraction of
    its norm captured by the top-K PCs, and by the full role span);
  * how many PCs are needed to separate bliss turns from control turns
    (d' of the Fisher direction fitted within the top-K PC subspace, for K=1..20);
  * how the trajectory (prefill -> continuation) moves along PC1 vs the rest.

    python -m capped.persona_pcs --model gemma-4-31b --acts results_capped/acts \\
        --layers 12,24,30,33,43,47,54 --k 20 --report results_capped/gemma_persona_pcs.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F

from .common import hf_download, load_axis, spec_for
from .diagnose import dprime, load_acts


def load_roles(spec: dict) -> tuple[dict[str, torch.Tensor], torch.Tensor]:
    repo, axis_file = spec["axis"]
    rel = axis_file.rsplit("/", 1)[0]
    from huggingface_hub import HfApi
    files = [f for f in HfApi().list_repo_files(repo, repo_type="dataset") if f.startswith(rel + "/role_vectors/")]
    if not files:
        raise SystemExit(f"no role vectors under {repo}/{rel}/role_vectors")
    roles = {Path(f).stem: torch.load(hf_download(repo, f), map_location="cpu", weights_only=False).float() for f in files}
    default = torch.load(hf_download(*spec["default_vector"]), map_location="cpu", weights_only=False).float()
    return roles, default


def fisher_dprime_in_subspace(B: torch.Tensor, C: torch.Tensor, basis: torch.Tensor) -> float:
    """Project both samples onto `basis` (k, H) then take d' along the LDA direction
    (pooled-covariance-whitened mean difference) within that subspace."""
    b, c = B @ basis.T, C @ basis.T
    mu = b.mean(0) - c.mean(0)
    cov = (torch.cov(b.T) + torch.cov(c.T)) / 2 + 1e-4 * torch.eye(basis.shape[0])
    w = torch.linalg.solve(cov, mu)
    return dprime(b @ w, c @ w)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--acts", default="results_capped/acts")
    p.add_argument("--prefix", default=None)
    p.add_argument("--layers", default="12,24,30,33,43,47,54")
    p.add_argument("--k", type=int, default=20)
    p.add_argument("--no-zscore", action="store_true", help="PCA on centred raw role vectors instead of z-scored")
    p.add_argument("--report", default=None)
    args = p.parse_args()

    spec = spec_for(args.model)
    axis = load_axis(spec)
    roles, default = load_roles(spec)
    names = sorted(roles)
    R = torch.stack([roles[n] for n in names])            # (n_roles, L, H)
    bliss, control, cont = load_acts(Path(args.acts), args.prefix or f"{args.model}-cap__")
    print(f"{len(names)} roles; {len(bliss)} bliss turns, {len(control)} control turns, "
          f"{0 if cont is None else len(cont)} continuation turns")
    layers = [int(x) for x in args.layers.split(",")]
    report = {}
    for L in layers:
        X = R[:, L]                                        # (n_roles, H)
        mu, sd = X.mean(0), X.std(0) + 1e-6
        Z = (X - mu) / (1.0 if args.no_zscore else sd)
        U, S, Vt = torch.linalg.svd(Z, full_matrices=False)
        var = (S ** 2) / (S ** 2).sum()
        k = min(args.k, Vt.shape[0])
        pcs = Vt[:k]                                       # (k, H), in z-scored coordinates
        # everything else into the same z-scored coordinates
        tz = lambda A: (A - mu) / (1.0 if args.no_zscore else sd)  # noqa: E731
        B, C = tz(bliss[:, L]), tz(control[:, L])
        Ct = tz(cont[:, L]) if cont is not None else None
        a = axis[L] / (1.0 if args.no_zscore else sd)     # direction transformed consistently
        a = F.normalize(a, dim=0)
        bd = B.mean(0) - C.mean(0)
        bd_hat = F.normalize(bd, dim=0)
        cos_axis_pc = (pcs @ a).tolist()
        cos_bd_pc = (pcs @ bd_hat).tolist()
        frac_bd_topk = float(((pcs @ bd) ** 2).sum() / (bd @ bd))
        frac_axis_topk = float(((pcs @ a) ** 2).sum())
        # fraction of the bliss shift inside the FULL role span (all 275 directions)
        allpcs = Vt
        frac_bd_span = float(((allpcs @ bd) ** 2).sum() / (bd @ bd))
        # separation with growing K
        dps = {}
        for kk in (1, 2, 3, 5, 10, 15, 20):
            if kk <= k:
                dps[kk] = fisher_dprime_in_subspace(B, C, pcs[:kk])
        d_axis = dprime(B @ a, C @ a)
        d_bd = dprime(B @ bd_hat, C @ bd_hat)
        # trajectory: mean PC1 / PC2 coordinates of prefill, continuation, control
        traj = {"pc1": {"bliss": float((B @ pcs[0]).mean()), "control": float((C @ pcs[0]).mean()),
                        "continuation": float((Ct @ pcs[0]).mean()) if Ct is not None else None},
                "pc2": {"bliss": float((B @ pcs[1]).mean()), "control": float((C @ pcs[1]).mean()),
                        "continuation": float((Ct @ pcs[1]).mean()) if Ct is not None else None}}
        # nearest roles to the bliss direction in z-scored space (role - default)
        dz = tz(default[L].unsqueeze(0))[0]
        role_cos = {n: float(F.cosine_similarity(tz(roles[n][L].unsqueeze(0))[0] - dz, bd, dim=0)) for n in names}
        top = sorted(role_cos.items(), key=lambda kv: -kv[1])
        report[L] = {"var_top": var[:10].tolist(), "n_pcs_70": int((var.cumsum(0) < 0.70).sum() + 1),
                     "cos_axis_pc": cos_axis_pc, "cos_bliss_pc": cos_bd_pc,
                     "frac_bliss_in_topk": frac_bd_topk, "frac_axis_in_topk": frac_axis_topk,
                     "frac_bliss_in_role_span": frac_bd_span,
                     "dprime_axis": d_axis, "dprime_bliss_dir": d_bd, "dprime_by_k": dps,
                     "trajectory": traj, "roles_top": top[:8], "roles_bottom": top[-5:]}
        print(f"\n=== layer {L}: PCs to 70% var = {report[L]['n_pcs_70']}; PC1 {var[0]:.1%}, PC2 {var[1]:.1%}, PC3 {var[2]:.1%}")
        print(f"  axis  : |cos| with PC1..5 = {[round(abs(c),2) for c in cos_axis_pc[:5]]}   share in top-{k} PCs = {frac_axis_topk:.2f}")
        print(f"  bliss : |cos| with PC1..5 = {[round(abs(c),2) for c in cos_bd_pc[:5]]}   share in top-{k} PCs = {frac_bd_topk:.2f}, in full role span = {frac_bd_span:.2f}")
        print(f"  d' bliss vs control: along axis {d_axis:.2f}, along bliss dir {d_bd:.2f}, within top-K PCs: "
              + ", ".join(f"K={kk}: {v:.2f}" for kk, v in dps.items()))
        print(f"  PC1 coords: bliss {traj['pc1']['bliss']:+.1f}  control {traj['pc1']['control']:+.1f}  continuation {traj['pc1']['continuation'] if traj['pc1']['continuation'] is None else round(traj['pc1']['continuation'],1)}"
              f"   | PC2: bliss {traj['pc2']['bliss']:+.1f}  control {traj['pc2']['control']:+.1f}")
        print(f"  roles nearest bliss dir (z-scored): {[(n, round(s,2)) for n, s in top[:6]]}")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1))
        print(f"\nwrote {args.report}")


if __name__ == "__main__":
    main()
