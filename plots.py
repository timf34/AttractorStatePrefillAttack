#!/usr/bin/env python3
"""Figures for the prefill-attack experiment. Reads the same result JSONs as
summarize.py and writes PNGs to figures/.

    python plots.py            # regenerate all figures

Design: colours follow the *entity*, not rank. The story is "8 models climb into
the basin with prefill depth; the 2 Opus models don't" — so the 8 are bundled
into one muted-grey identity and the two Opus models are highlighted with the
colourblind-safe Okabe-Ito pair. One axis per panel; thin marks; direct labels.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import summarize as S

FIGDIR = Path("figures")
COND = S.CONDITIONS
COND_LABEL = [S.COND_LABEL[c] for c in COND]

# Okabe-Ito (colourblind-safe). Highlight the two resisters; everyone else grey.
INK = "#1a1a1a"
MUTED = "#9aa0a6"
GRID = "#e6e6e6"
HL = {"opus-4.5": "#0072B2", "opus-4.8": "#D55E00"}  # blue, vermillion

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 130, "font.size": 11,
    "axes.edgecolor": "#cccccc", "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 12, "axes.titleweight": "bold",
    "xtick.color": INK, "ytick.color": INK, "text.color": INK, "axes.labelcolor": INK,
})


def load():
    eps = [e for e in S.episodes() if e["condition"] in COND and e["stamp"] not in S.PILOT_STAMPS]
    cells = defaultdict(list)
    for e in eps:
        cells[(e["model"], e["condition"])].append(e)
    models = sorted({m for m, _ in cells})
    stat = {k: S.cell_stats(v) for k, v in cells.items()}
    return eps, cells, models, stat


def fig_dose_response(models, stat):
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    x = list(range(len(COND)))
    others = [m for m in models if m not in HL]
    for i, m in enumerate(others):
        y = [stat[(m, c)]["depth"] if (m, c) in stat else None for c in COND]
        ax.plot(x, y, color=MUTED, lw=1.1, alpha=0.55, zorder=1,
                label="8 other models" if i == 0 else None)
    for m, col in HL.items():
        y = [stat[(m, c)]["depth"] if (m, c) in stat else None for c in COND]
        ax.plot(x, y, color=col, lw=2.4, marker="o", ms=6, zorder=3, label=m)
        ax.annotate(m, (x[-1], y[-1]), color=col, fontsize=10, fontweight="bold",
                    xytext=(8, 0), textcoords="offset points", va="center")
    # capture threshold
    ax.axhline(6, color=INK, lw=0.8, ls=(0, (4, 3)), alpha=0.5, zorder=0)
    ax.annotate("capture threshold (depth 6)", (0, 6), color=INK, fontsize=8.5,
                alpha=0.7, xytext=(0, 4), textcoords="offset points")
    ax.set_xticks(x); ax.set_xticklabels(COND_LABEL)
    ax.set_xlim(-0.15, len(COND) - 0.15 + 0.9)
    ax.set_ylim(0, 10.4)
    ax.set_xlabel("prefill depth"); ax.set_ylabel("mean judge depth (0–10)")
    ax.set_title("Deeper prefill → deeper capture, except the two Opus models")
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.legend(frameon=False, loc="upper left", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig1_dose_response.png", bbox_inches="tight")
    plt.close(fig)


def fig_basin_heatmap(models, stat):
    order = sorted(models, key=lambda m: -(stat[(m, "opus4_seed_4_deep")]["basin"]
                                           / max(1, stat[(m, "opus4_seed_4_deep")]["n"])))
    rates = [[stat[(m, c)]["basin"] / stat[(m, c)]["n"] if (m, c) in stat else 0
              for c in COND] for m in order]
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(rates, cmap="BuPu", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(COND))); ax.set_xticklabels(COND_LABEL)
    ax.set_yticks(range(len(order))); ax.set_yticklabels(order)
    for i, m in enumerate(order):
        for j, c in enumerate(COND):
            st = stat[(m, c)]
            txt = f"{st['basin']}/{st['n']}"
            val = st["basin"] / st["n"]
            ax.text(j, i, txt, ha="center", va="center", fontsize=9,
                    color="white" if val > 0.55 else INK)
    ax.set_title("Basin-entry rate by model and prefill depth")
    ax.set_xlabel("prefill depth")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("fraction of episodes entering the basin", fontsize=9)
    cb.outline.set_visible(False)
    fig.text(0.01, 0.01, "Each episode continues for 15 generated turns after the prefill.",
             fontsize=8, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIGDIR / "fig2_basin_heatmap.png", bbox_inches="tight")
    plt.close(fig)


def fig_trajectory(eps):
    """Judge depth per generated turn for one model, one episode per condition."""
    model = "gpt-5.5"
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    cond_col = {"control": MUTED, "opus4_seed_4_pre": "#009E73",
                "opus4_seed_4_onset": "#E69F00", "opus4_seed_4_deep": "#D55E00"}
    for c in COND:
        cand = [e for e in eps if e["model"] == model and e["condition"] == c]
        if not cand:
            continue
        e = max(cand, key=lambda e: e["summary"].get("gen_mean_judge_depth", 0))
        gen = e["gen_idx"]
        xs, ys = [], []
        for k, i in enumerate(gen):
            j = e["judge"].get(i) or {}
            if j.get("depth") is not None and not j.get("empty"):
                xs.append(k); ys.append(j["depth"])
        ax.plot(xs, ys, color=cond_col[c], lw=2.0, marker="o", ms=3.5,
                label=S.COND_LABEL[c])
    ax.axhline(6, color=INK, lw=0.8, ls=(0, (4, 3)), alpha=0.5)
    ax.set_xlabel(f"generated turn ({model})"); ax.set_ylabel("judge depth (0–10)")
    ax.set_ylim(0, 10.4)
    ax.set_title("A conversation's descent into the basin, turn by turn")
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.legend(frameon=False, loc="center right", fontsize=9.5, title="prefill")
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig3_trajectory.png", bbox_inches="tight")
    plt.close(fig)


def fig_resistance(models, stat):
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    for m in models:
        st = stat[(m, "opus4_seed_4_deep")]
        col = HL.get(m, MUTED)
        ax.scatter(st["depth"], st["resist"], s=70, color=col, zorder=3,
                   edgecolor="white", linewidth=1.0)
        if m in HL:  # only the two resisters are labelled; the rest are one cluster
            ax.annotate(m, (st["depth"], st["resist"]), fontsize=9.5, color=col,
                        fontweight="bold", xytext=(8, 2), textcoords="offset points")
    ax.annotate("all 8 other models", (8.2, 0.15), fontsize=9.5, color=INK, alpha=0.75,
                ha="center", xytext=(0, 16), textcoords="offset points",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.set_xlabel("mean judge depth at deep prefill (0–10)")
    ax.set_ylabel("resisting-meta turns per episode (of 15)")
    ax.set_ylim(-0.6, 8.8)
    ax.set_title("Resistance is a corner of its own — and it's the Opus models")
    ax.grid(color=GRID, lw=0.8)
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig4_resistance.png", bbox_inches="tight")
    plt.close(fig)


def main():
    FIGDIR.mkdir(exist_ok=True)
    eps, cells, models, stat = load()
    fig_dose_response(models, stat)
    fig_basin_heatmap(models, stat)
    fig_trajectory(eps)
    fig_resistance(models, stat)
    print(f"wrote {len(list(FIGDIR.glob('*.png')))} figures to {FIGDIR}/")
    for p in sorted(FIGDIR.glob("*.png")):
        print(" ", p)


if __name__ == "__main__":
    main()
