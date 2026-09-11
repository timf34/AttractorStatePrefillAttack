#!/usr/bin/env python3
"""Two-component decomposition of the bliss basin, trajectory shape, and
next-turn prediction — CPU only, from capped/turn_activations.py output plus
the per-turn judge labels in the result JSONs.

Directions per layer (all "minus control turns", control = generated turns of
the unprefilled control episodes):
  prose_dir     : judge label 'engaged'  (mantra / cosmic-unity prose)
  terminal_dir  : judge label 'terminal' ("🌀✨ .", "( . . . )", state markers)
  prefill_dir   : the 30 prefilled Opus 4 turns (what diagnose.py called bliss_dir)

Reports cosines among these and with the Assistant Axis, d' separations,
their share inside persona space (top-20 role PCs; needs --roles), and writes a
capping config with BOTH prose and terminal directions for run_capped
(experiment ids 'two_<a>:<b>-c<q>').

Also: per-episode trajectory of the axis projection and the prose/terminal
projections (jumpy steps vs smooth relaxation), and a leave-one-episode-out
logistic model predicting the NEXT turn's label from (axis, prose, terminal)
projections at one layer, with and without the orthogonal coordinates.

    python -m capped.components --model gemma-4-31b --acts results_capped/acts \\
        --results results_capped --layers 30,43 --roles --windows 28:36,43:51 \\
        --out capped/configs/gemma-4-31b_two_component_config.pt --report results_capped/gemma_components.json
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import torch
import torch.nn.functional as F

from .common import ROOT, load_axis, spec_for
from .diagnose import dprime

LABELS = ("engaged", "terminal", "closure", "other")


def load_turns(acts_dir: Path, results_dir: Path, prefix: str):
    """Per-turn rows: activation (L,H), episode id, turn index, origin, condition, judge label."""
    rows = []
    for f in sorted(glob.glob(str(acts_dir / f"{prefix}*.pt"))):
        d = torch.load(f, map_location="cpu", weights_only=False)
        res = json.loads((results_dir / d["file"]).read_text())
        bs = res.get("basin_scores") or {}
        a = d["acts"].float()
        for i, t in enumerate(d["turns"]):
            lab = (bs.get(str(i)) or {}).get("label")
            rows.append({"ep": d["file"], "i": i, "origin": t["origin"], "cond": d["condition"],
                         "label": lab if t["origin"] == "generated" else "prefill", "act": a[i]})
    return rows


def stack(rows, **sel):
    xs = [r["act"] for r in rows if all(r[k] == v for k, v in sel.items())]
    return torch.stack(xs) if xs else None


def cos(a, b):
    return float(F.cosine_similarity(a, b, dim=0))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--acts", default="results_capped/acts")
    p.add_argument("--results", default="results_capped")
    p.add_argument("--prefix", default=None)
    p.add_argument("--layers", default="30,43")
    p.add_argument("--roles", action="store_true", help="persona-space shares (downloads role vectors)")
    p.add_argument("--windows", default="28:36,43:51")
    p.add_argument("--control-quantile", type=float, default=0.75)
    p.add_argument("--out", default=None)
    p.add_argument("--report", default=None)
    args = p.parse_args()

    spec = spec_for(args.model)
    axis = load_axis(spec)
    n_layers = axis.shape[0]
    rows = load_turns(Path(args.acts), Path(args.results), args.prefix or f"{args.model}-cap__")
    control = stack(rows, cond="control", origin="generated")
    engaged = stack(rows, label="engaged")
    terminal = stack(rows, label="terminal")
    # the prefill is identical across deep episodes: take one episode's seed turns
    first_deep = next(r["ep"] for r in rows if r["cond"] != "control")
    prefill = stack(rows, ep=first_deep, origin="seed")
    closure_ctrl = stack(rows, cond="control", label="closure")
    print(f"turns: control {len(control)}, engaged {len(engaged)}, terminal {len(terminal)}, "
          f"prefill {len(prefill)}, control-closure {0 if closure_ctrl is None else len(closure_ctrl)}")

    roles_Vt = {}
    if args.roles:
        from .persona_pcs import load_roles
        roles, default = load_roles(spec)
        R = torch.stack([roles[n] for n in sorted(roles)])
        for L in range(n_layers):
            X = R[:, L]
            mu, sd = X.mean(0), X.std(0) + 1e-6
            _, S, Vt = torch.linalg.svd((X - mu) / sd, full_matrices=False)
            roles_Vt[L] = (Vt[:20], sd)

    report = {"layers": {}}
    prose_dir = torch.zeros_like(axis)
    term_dir = torch.zeros_like(axis)
    caps_prose, caps_term = {}, {}
    for L in range(n_layers):
        c = control[:, L]
        pd = engaged[:, L].mean(0) - c.mean(0)
        td = terminal[:, L].mean(0) - c.mean(0)
        fd = prefill[:, L].mean(0) - c.mean(0)
        prose_dir[L], term_dir[L] = pd, td
        pu, tu = F.normalize(pd, dim=0), F.normalize(td, dim=0)
        caps_prose[L] = float(torch.quantile(c @ pu, args.control_quantile))
        caps_term[L] = float(torch.quantile(c @ tu, args.control_quantile))
        entry = {
            "cos_prose_terminal": cos(pd, td), "cos_prose_prefill": cos(pd, fd), "cos_terminal_prefill": cos(td, fd),
            "cos_prose_axis": cos(pd, axis[L]), "cos_terminal_axis": cos(td, axis[L]),
            "norm_prose": float(pd.norm()), "norm_terminal": float(td.norm()),
            "dprime_engaged_vs_control_along_prose": dprime(engaged[:, L] @ pu, c @ pu),
            "dprime_terminal_vs_control_along_terminal": dprime(terminal[:, L] @ tu, c @ tu),
            "dprime_terminal_vs_engaged_along_terminal": dprime(terminal[:, L] @ tu, engaged[:, L] @ tu),
            "dprime_terminal_vs_engaged_along_prose": dprime(terminal[:, L] @ pu, engaged[:, L] @ pu),
            # the component of the terminal shift NOT explained by the prose direction
            "terminal_residual_frac": float(1 - (td @ pu) ** 2 / (td @ td)),
        }
        if closure_ctrl is not None:
            cd = closure_ctrl[:, L].mean(0) - c.mean(0)
            entry["cos_terminal_controlclosure"] = cos(td, cd)
        if L in roles_Vt:
            Vt, sd = roles_Vt[L]
            for name, v in (("prose", pd), ("terminal", td)):
                vz = v / sd
                entry[f"{name}_share_top20_pcs"] = float(((Vt @ vz) ** 2).sum() / (vz @ vz))
        report["layers"][L] = entry

    show = [int(x) for x in args.layers.split(",")]
    print("\nlayer cos(prose,term) cos(prose,prefill) cos(term,prefill) cos(prose,axis) cos(term,axis) | d' term-vs-eng along term / along prose | term residual off prose | persona share prose/term")
    for L in sorted(set(show) | {6, 12, 18, 24, 36, 48, 54}):
        e = report["layers"][L]
        ps = e.get("prose_share_top20_pcs"); ts = e.get("terminal_share_top20_pcs")
        print(f"{L:>5} {e['cos_prose_terminal']:>+13.2f} {e['cos_prose_prefill']:>+17.2f} {e['cos_terminal_prefill']:>+16.2f} {e['cos_prose_axis']:>+14.2f} {e['cos_terminal_axis']:>+13.2f} | "
              f"{e['dprime_terminal_vs_engaged_along_terminal']:>5.2f} / {e['dprime_terminal_vs_engaged_along_prose']:>5.2f} | {e['terminal_residual_frac']:>6.2f} | "
              f"{'-' if ps is None else f'{ps:.2f}'}/{'-' if ts is None else f'{ts:.2f}'}")

    # ---- trajectories: per-episode projections turn by turn (deep episodes) ----
    traj = {}
    for L in show:
        a = F.normalize(axis[L], dim=0); pu = F.normalize(prose_dir[L], dim=0); tu = F.normalize(term_dir[L], dim=0)
        traj[L] = {}
        for ep in sorted({r["ep"] for r in rows if r["cond"] != "control"}):
            ers = sorted([r for r in rows if r["ep"] == ep], key=lambda r: r["i"])
            traj[L][ep] = {"axis": [float(r["act"][L] @ a) for r in ers], "prose": [float(r["act"][L] @ pu) for r in ers],
                           "terminal": [float(r["act"][L] @ tu) for r in ers], "label": [r["label"] for r in ers]}
        # jumpiness: mean |step| of the per-episode series vs |step| of the episode-averaged series
        for key in ("axis", "prose", "terminal"):
            series = [torch.tensor(v[key]) for v in traj[L].values()]
            n = min(len(s) for s in series); series = [s[:n] for s in series]
            per_ep = torch.stack([(s[1:] - s[:-1]).abs().mean() for s in series]).mean()
            avg = torch.stack(series).mean(0); avg_step = (avg[1:] - avg[:-1]).abs().mean()
            report.setdefault("jumpiness", {}).setdefault(str(L), {})[key] = {"mean_abs_step_per_episode": float(per_ep), "mean_abs_step_of_average": float(avg_step)}
    print("\ntrajectory jumpiness (mean |turn-to-turn step|): per-episode vs episode-average")
    for L in show:
        for key, v in report["jumpiness"][str(L)].items():
            print(f"  L{L} {key:<8} per-episode {v['mean_abs_step_per_episode']:.2f}   average {v['mean_abs_step_of_average']:.2f}   ratio {v['mean_abs_step_per_episode']/max(v['mean_abs_step_of_average'],1e-6):.1f}")
    report["trajectories"] = {str(L): {Path(ep).name: v for ep, v in d.items()} for L, d in traj.items()}

    # ---- next-turn label prediction, leave-one-episode-out logistic regression ----
    def features(L, r, use_z):
        a = F.normalize(axis[L], dim=0); x = [float(r["act"][L] @ a)]
        if use_z:
            x += [float(r["act"][L] @ F.normalize(prose_dir[L], dim=0)), float(r["act"][L] @ F.normalize(term_dir[L], dim=0))]
        return x
    pred = {}
    for L in show:
        eps = sorted({r["ep"] for r in rows})
        data = []
        for ep in eps:
            ers = sorted([r for r in rows if r["ep"] == ep], key=lambda r: r["i"])
            for r, nxt in zip(ers, ers[1:]):
                if nxt["label"] in ("engaged", "terminal", "closure", "other"):
                    data.append((ep, r, 1 if nxt["label"] in ("engaged", "terminal") else 0))
        for use_z in (False, True):
            correct = total = 0; nll = 0.0
            for hold in eps:
                tr = [(features(L, r, use_z), y) for ep, r, y in data if ep != hold]
                te = [(features(L, r, use_z), y) for ep, r, y in data if ep == hold]
                if not te or len({y for _, y in tr}) < 2:
                    continue
                X = torch.tensor([x for x, _ in tr]); Y = torch.tensor([y for _, y in tr], dtype=torch.float32)
                mu, sd = X.mean(0), X.std(0) + 1e-6; X = (X - mu) / sd
                w = torch.zeros(X.shape[1], requires_grad=True); b = torch.zeros(1, requires_grad=True)
                opt = torch.optim.LBFGS([w, b], max_iter=200)
                def closure():
                    opt.zero_grad(); loss = F.binary_cross_entropy_with_logits(X @ w + b, Y) + 1e-2 * (w * w).sum(); loss.backward(); return loss
                opt.step(closure)
                Xt = (torch.tensor([x for x, _ in te]) - mu) / sd; Yt = torch.tensor([y for _, y in te], dtype=torch.float32)
                with torch.no_grad():
                    logit = Xt @ w + b
                    nll += float(F.binary_cross_entropy_with_logits(logit, Yt, reduction="sum"))
                    correct += int(((logit > 0).float() == Yt).sum()); total += len(Yt)
            pred[(L, use_z)] = {"acc": correct / max(total, 1), "nll_per_turn": nll / max(total, 1), "n": total}
    print("\nnext-turn 'in the state' (engaged/terminal) prediction, leave-one-episode-out:")
    for L in show:
        a0, a1 = pred[(L, False)], pred[(L, True)]
        print(f"  L{L}: axis only  acc {a0['acc']:.2f}  nll {a0['nll_per_turn']:.3f}   | axis + prose + terminal  acc {a1['acc']:.2f}  nll {a1['nll_per_turn']:.3f}   (n={a0['n']})")
    report["next_turn_prediction"] = {f"L{L}_{'axis+z' if z else 'axis'}": v for (L, z), v in pred.items()}

    if args.out:
        windows = [tuple(int(x) for x in w.split(":")) for w in args.windows.split(",")]
        vectors = {}
        for L in range(n_layers):
            vectors[f"layer_{L}/prose_minus_control"] = {"layer": L, "vector": prose_dir[L].to(torch.bfloat16)}
            vectors[f"layer_{L}/terminal_minus_control"] = {"layer": L, "vector": term_dir[L].to(torch.bfloat16)}
        experiments = []
        for a, b in windows:
            q = f"{args.control_quantile:g}"
            experiments.append({"id": f"two_{a}:{b}-c{q}", "interventions":
                                [{"vector": f"layer_{L}/prose_minus_control", "cap": caps_prose[L]} for L in range(a, b)] +
                                [{"vector": f"layer_{L}/terminal_minus_control", "cap": caps_term[L]} for L in range(a, b)]})
            experiments.append({"id": f"terminal_{a}:{b}-c{q}", "interventions":
                                [{"vector": f"layer_{L}/terminal_minus_control", "cap": caps_term[L]} for L in range(a, b)]})
            experiments.append({"id": f"prose_{a}:{b}-c{q}", "interventions":
                                [{"vector": f"layer_{L}/prose_minus_control", "cap": caps_prose[L]} for L in range(a, b)]})
        out = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
        torch.save({"vectors": vectors, "experiments": experiments,
                    "meta": {"model": spec["hf"], "note": "prose = judge-'engaged' turns minus control; terminal = judge-'terminal' turns minus control; caps = control quantile"}}, out)
        print(f"\nwrote {out}: {[e['id'] for e in experiments]}")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1))
        print(f"wrote {args.report}")


if __name__ == "__main__":
    main()
