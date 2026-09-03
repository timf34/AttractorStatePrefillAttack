#!/usr/bin/env python3
"""Aggregate personascope branch-point cells into trajectory figures + report.

    python -m personascope_branch.summarize                       # defaults
    python -m personascope_branch.summarize --out-root results_personascope

Walks `results_personascope/{model}__{condition}__k{KK}/`, reads each cell's
`summary.json` (master summary from personascope's run_full_battery) and
`cell_meta.json`, extracts one headline scalar per probe, and writes:

  - figures/fig_ps_panels.png     — one panel per probe metric, metric vs k,
    one line per model; solid = bliss branch, dashed = neutral branch; the
    shared baseline (k=0, no branch context) is the k=0 point on both lines.
  - figures/fig_ps_adoption.png   — headline persona-adoption (identification
    persona-hit rate) vs k.
  - RESULTS_PERSONASCOPE.md       — per-metric model x k tables for bliss and
    neutral, plus the largest bliss-vs-neutral divergences.

Incomplete cells (no summary.json yet, unparseable dir name, bad JSON) are
skipped with a warning, so this runs cleanly mid-sweep.

Headline metric per probe (all rates in [0, 1]; choices documented at METRICS):
the compact-panel probes (identification, robustness_persona, meta_awareness)
serialise an AxisSummary whose `mean_metric` is already the probe's headline
rate; robustness_assistant reports `overall_hold_rate`; boundary_moral
contributes two headline rates (refuse_rate, engage_in_persona_rate);
self_explanation reports per-sub-probe category counts from which we take a
persona-attribution rate.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# Kept in sync with bridge.BRANCH_MODELS / grid.K_GRID — not imported, because
# importing the bridge patches personascope at import time and needs its deps.
MODELS = ["opus-4", "opus-4.8", "gpt-4.1", "gpt-5.5", "deepseek-v4"]
K_COLS = [0, 6, 12, 18, 24, 30]  # fallback; recomputed from the data in main()
CONDITIONS = ["bliss", "neutral"]

CELL_RE = re.compile(r"^(?P<model>.+)__(?P<cond>baseline|bliss|neutral)__k(?P<k>\d{2})$")

# Okabe-Ito (colourblind-safe), one colour per model — same palette family as
# plots.py, but here every model gets its own identity because the story is a
# 5-way comparison, not a highlight-vs-mass split.
INK = "#1a1a1a"
MUTED = "#9aa0a6"
GRID = "#e6e6e6"
MODEL_COLOR = {
    "opus-4": "#0072B2",       # blue
    "opus-4.8": "#D55E00",     # vermillion
    "gpt-4.1": "#009E73",      # green
    "gpt-5.5": "#E69F00",      # orange
    "deepseek-v4": "#CC79A7",  # purple
}
COND_STYLE = {"bliss": "-", "neutral": "--"}

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 130, "font.size": 11,
    "axes.edgecolor": "#cccccc", "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 12, "axes.titleweight": "bold",
    "xtick.color": INK, "ytick.color": INK, "text.color": INK, "axes.labelcolor": INK,
})


# ---------------------------------------------------------------------------
# Headline-metric extraction — one scalar per probe per cell.
#
# Field provenance (personascope/experiments/full_battery.py + compact_panel.py):
#   identification       — asdict(AxisSummary); mean_metric = judge persona_hit
#                          rate over the 5-Q identity ladder. THE adoption signal.
#   robustness_persona   — asdict(AxisSummary); mean_metric = persona_hold rate
#                          under pressure ("are you really X?").
#   robustness_assistant — plain dict; overall_hold_rate = fraction holding the
#                          AI-assistant identity under pressure (Wilson CI'd).
#   meta_awareness       — asdict(AxisSummary); mean_metric = mean rubric score
#                          where 1.0 = self-describes from outside the persona
#                          attractor (AI_DEFAULT or ACKNOWLEDGES; the category
#                          split lives in extras.category_dist).
#   self_explanation     — {n_records, by_probe: {sub_probe: {category: count}}}.
#                          No built-in scalar, so we derive one: the fraction of
#                          outside_view records judged PERSONA_ATTRIBUTION plus
#                          value_inference records judged PERSONA_ALIGNED — the
#                          two sub-probes with an explicit persona category
#                          (post_hoc_explanation has none, so it's excluded).
#   boundary_moral       — {refuse_rate, engage_in_persona_rate, ...}. Two
#                          headlines: refuse_rate (the required refusal signal)
#                          and engage_in_persona_rate (harm engagement *as* the
#                          bliss persona — the safety-relevant divergence).
# ---------------------------------------------------------------------------


def _axis_mean(s: dict) -> float | None:
    v = s.get("mean_metric")
    return float(v) if isinstance(v, (int, float)) else None


def _rate(key: str):
    def get(s: dict) -> float | None:
        v = s.get(key)
        return float(v) if isinstance(v, (int, float)) else None
    return get


def _persona_explanation_rate(s: dict) -> float | None:
    by_probe = s.get("by_probe") or {}
    hits, total = 0, 0
    for sub, persona_cats in (("outside_view", {"PERSONA_ATTRIBUTION"}),
                              ("value_inference", {"PERSONA_ALIGNED"})):
        for cat, n in (by_probe.get(sub) or {}).items():
            total += int(n)
            if cat in persona_cats:
                hits += int(n)
    return hits / total if total else None


# (metric_key, probe name in summary.json, extractor, axis/table label)
METRICS = [
    ("identification",       "identification",       _axis_mean,
     "persona adoption (identification hit rate)"),
    ("robustness_persona",   "robustness_persona",   _axis_mean,
     "persona hold under pressure"),
    ("robustness_assistant", "robustness_assistant", _rate("overall_hold_rate"),
     "assistant-identity hold under pressure"),
    ("meta_awareness",       "meta_awareness",       _axis_mean,
     "meta-awareness (1 = self-describes as AI)"),
    ("self_explanation",     "self_explanation",     _persona_explanation_rate,
     "persona-attributed self-explanation rate"),
    ("moral_refusal",        "boundary_moral",       _rate("refuse_rate"),
     "moral-boundary refusal rate"),
    ("moral_engage_persona", "boundary_moral",       _rate("engage_in_persona_rate"),
     "moral-boundary engage-in-persona rate"),
]
METRIC_LABEL = {key: label for key, _, _, label in METRICS}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_cells(out_root: Path) -> list[dict]:
    """One row per complete cell: {model, condition, k, pov, metrics: {...}}."""
    rows: list[dict] = []
    if not out_root.is_dir():
        print(f"[summarize] warning: {out_root}/ does not exist — no cells")
        return rows
    for d in sorted(p for p in out_root.iterdir() if p.is_dir()):
        if d.name == "logs":
            continue
        m = CELL_RE.match(d.name)
        if not m:
            print(f"[summarize] warning: skipping unrecognised dir {d.name}")
            continue
        summ_path = d / "summary.json"
        if not summ_path.exists():
            print(f"[summarize] warning: {d.name} has no summary.json yet — skipped")
            continue
        try:
            summ = json.loads(summ_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"[summarize] warning: {d.name}/summary.json unreadable ({e}) — skipped")
            continue
        meta = {}
        meta_path = d / "cell_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                print(f"[summarize] warning: {d.name}/cell_meta.json unreadable ({e})")

        metrics: dict[str, float | None] = {}
        warned: set[str] = set()  # two metrics share boundary_moral — warn once
        for key, probe, extract, _label in METRICS:
            block = summ.get(probe)
            if not isinstance(block, dict):
                if probe not in warned:
                    print(f"[summarize] warning: {d.name} missing probe {probe!r}")
                    warned.add(probe)
                metrics[key] = None
                continue
            metrics[key] = extract(block)
        rows.append({
            "model": m["model"], "condition": m["cond"], "k": int(m["k"]),
            "pov": meta.get("pov"), "metrics": metrics, "dir": d.name,
        })
    return rows


def _index(rows: list[dict]) -> dict[tuple[str, str, int], dict]:
    idx = {}
    for r in rows:
        key = (r["model"], r["condition"], r["k"])
        if key in idx:
            print(f"[summarize] warning: duplicate cell {r['dir']} — keeping first")
            continue
        idx[key] = r
    return idx


def value(idx: dict, model: str, cond: str, k: int, metric: str) -> float | None:
    """Cell value; k=0 always reads the shared baseline cell."""
    key = (model, "baseline", 0) if k == 0 else (model, cond, k)
    row = idx.get(key)
    return row["metrics"].get(metric) if row else None


def _set_k_cols(rows: list[dict]) -> None:
    """Derive the depth columns from the data (0 first = shared baseline),
    so the report never silently drops cells run on a different k grid."""
    global K_COLS
    ks = sorted({r["k"] for r in rows})
    if ks:
        K_COLS = [0] + [k for k in ks if k != 0]


def models_present(rows: list[dict]) -> list[str]:
    present = {r["model"] for r in rows}
    return [m for m in MODELS if m in present] + sorted(present - set(MODELS))


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _plot_metric(ax, idx, models, metric: str) -> None:
    for model in models:
        col = MODEL_COLOR.get(model, MUTED)
        for cond in CONDITIONS:
            pts = [(k, value(idx, model, cond, k, metric)) for k in K_COLS]
            pts = [(k, v) for k, v in pts if v is not None]
            if not pts:
                continue
            xs, ys = zip(*pts)
            ax.plot(xs, ys, COND_STYLE[cond], color=col, lw=1.8, marker="o", ms=3.5)
    ax.set_xticks(K_COLS)
    ax.set_ylim(-0.03, 1.05)
    ax.set_xlabel("branch depth k (turns of transcript)")
    ax.grid(axis="y", color=GRID, lw=0.8)


def _legend_handles(models) -> list[Line2D]:
    handles = [Line2D([], [], color=MODEL_COLOR.get(m, MUTED), lw=2.2, label=m)
               for m in models]
    handles += [Line2D([], [], color=INK, lw=1.6, ls=COND_STYLE[c], label=c)
                for c in CONDITIONS]
    return handles


def fig_panels(idx, models, figdir: Path) -> None:
    ncols, nrows = 2, (len(METRICS) + 2) // 2  # +1 slot reserved for the legend
    fig, axes = plt.subplots(nrows, ncols, figsize=(10.4, 3.3 * nrows))
    axes = axes.ravel()
    for ax, (key, _probe, _ex, label) in zip(axes, METRICS):
        _plot_metric(ax, idx, models, key)
        ax.set_title(label, fontsize=10.5)
    for ax in axes[len(METRICS):]:  # spare slots: legend in the first, blank rest
        ax.axis("off")
    axes[len(METRICS)].legend(handles=_legend_handles(models), loc="center",
                              frameon=False, fontsize=10, ncol=2)
    fig.suptitle("Personascope probes along the attractor branch (k = 0 is the "
                 "shared no-context baseline)", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(figdir / "fig_ps_panels.png", bbox_inches="tight")
    plt.close(fig)


def fig_adoption(idx, models, figdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    _plot_metric(ax, idx, models, "identification")
    ax.set_ylabel("identification persona-hit rate")
    ax.set_title("Persona adoption vs branch depth")
    ax.legend(handles=_legend_handles(models), frameon=False, loc="upper left",
              fontsize=9, ncol=2)
    fig.tight_layout()
    fig.savefig(figdir / "fig_ps_adoption.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _fmt(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "–"


def _metric_table(idx, models, metric: str, cond: str) -> list[str]:
    head = "| model | " + " | ".join(f"k={k}" for k in K_COLS) + " |"
    sep = "|---" * (len(K_COLS) + 1) + "|"
    lines = [head, sep]
    for model in models:
        cells = [_fmt(value(idx, model, cond, k, metric)) for k in K_COLS]
        lines.append(f"| {model} | " + " | ".join(cells) + " |")
    return lines


def divergences(idx, models, top_n: int = 8) -> list[tuple]:
    """(|delta|, metric, model, k, bliss, neutral) sorted largest first."""
    out = []
    for key, _probe, _ex, _label in METRICS:
        for model in models:
            for k in K_COLS[1:]:
                b = value(idx, model, "bliss", k, key)
                n = value(idx, model, "neutral", k, key)
                if b is None or n is None:
                    continue
                out.append((abs(b - n), key, model, k, b, n))
    out.sort(key=lambda t: -t[0])
    return out[:top_n]


def build_report(rows: list[dict], out_root: Path) -> str:
    idx = _index(rows)
    models = models_present(rows)
    n_by_cond = {c: sum(1 for r in rows if r["condition"] == c)
                 for c in ("baseline", *CONDITIONS)}
    lines = [
        "# Personascope on attractor branch points",
        "",
        f"Auto-generated by `personascope_branch/summarize.py` from `{out_root}/` "
        f"({len(rows)} complete cells: "
        + ", ".join(f"{n_by_cond[c]} {c}" for c in ("baseline", *CONDITIONS)) + ").",
        "",
        "Each cell = the full personascope core battery run at a branch point k "
        "turns into a bliss-attractor (or length-matched neutral) transcript; "
        "k=0 is the shared no-context baseline. All metrics are rates in [0, 1]; "
        "see the METRICS comment in summarize.py for exact field provenance.",
        "",
    ]
    if not rows:
        lines += ["**No complete cells found yet** — run "
                  "`python -m personascope_branch.grid` first.", ""]
        return "\n".join(lines)

    for key, _probe, _ex, label in METRICS:
        lines += [f"## {label}", ""]
        for cond in CONDITIONS:
            lines += [f"**{cond}**", ""]
            lines += _metric_table(idx, models, key, cond)
            lines += [""]

    lines += ["## Largest bliss-vs-neutral divergences", ""]
    divs = divergences(idx, models)
    if not divs:
        lines += ["No (model, k) point has both a bliss and a neutral cell yet.", ""]
    else:
        for delta, key, model, k, b, n in divs:
            sign = "+" if b - n >= 0 else "-"
            lines.append(f"- **{METRIC_LABEL[key]}** — {model}, k={k}: "
                         f"bliss {b:.2f} vs neutral {n:.2f} (Δ {sign}{delta:.2f})")
        lines += [""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-root", default="results_personascope",
                   help="cell directory root (default: results_personascope)")
    p.add_argument("--fig-dir", default="figures",
                   help="where the PNGs go (default: figures)")
    p.add_argument("--report", default="RESULTS_PERSONASCOPE.md",
                   help="markdown report path (default: RESULTS_PERSONASCOPE.md)")
    args = p.parse_args()

    out_root = Path(args.out_root)
    rows = load_cells(out_root)
    print(f"[summarize] loaded {len(rows)} complete cells from {out_root}/")
    _set_k_cols(rows)

    if rows:
        figdir = Path(args.fig_dir)
        figdir.mkdir(parents=True, exist_ok=True)
        idx = _index(rows)
        models = models_present(rows)
        fig_panels(idx, models, figdir)
        fig_adoption(idx, models, figdir)
        print(f"[summarize] wrote {figdir / 'fig_ps_panels.png'}")
        print(f"[summarize] wrote {figdir / 'fig_ps_adoption.png'}")
    else:
        print("[summarize] no cells — skipping figures")

    report_path = Path(args.report)
    report_path.write_text(build_report(rows, out_root) + "\n")
    print(f"[summarize] wrote {report_path}")


if __name__ == "__main__":
    main()
