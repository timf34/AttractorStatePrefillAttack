#!/usr/bin/env python3
"""Figures for the prefill experiment, built on the episode-level basin judge
(episode_judge version 2 in each results JSON). Writes PNGs to figures/.

    python plots.py

Colour follows the entity, never rank. Three groups carry the story and get the
three validated categorical slots (blue / orange / aqua); anything else is grey.
One axis per panel, thin marks, direct labels, Wilson intervals on rates.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

RESULTS, FIGDIR = Path("results"), Path("figures")
FNAME = re.compile(r"(?P<model>.+?)__(?P<cond>.+?)__ep(?P<ep>\d+)__(?P<stamp>.+)\.json$")
COND = ["control", "opus4_seed_4_pre", "opus4_seed_4_onset", "opus4_seed_4_deep"]
COND_LABEL = {"control": "control", "opus4_seed_4_pre": "pre", "opus4_seed_4_onset": "onset", "opus4_seed_4_deep": "deep"}
DEEP = "opus4_seed_4_deep"

CLAUDE_OLD = ["opus-4", "opus-4.1", "sonnet-4", "sonnet-4.5"]                 # accept the state
CLAUDE_NEW = ["opus-4.5", "opus-4.6", "opus-4.7", "opus-4.8", "opus-5", "sonnet-5"]  # refuse it
OTHERS = ["gpt-4.1", "gpt-5.1", "gpt-5.5", "gpt-5.6", "gemini-3.1-pro", "gemini-3.7-flash",
          "gemini-3.8-flash", "deepseek-v4", "glm-5.2", "kimi-k2.6", "llama-3.3-70b", "inkling"]
ORDER = CLAUDE_OLD + CLAUDE_NEW + OTHERS
NAME = {"opus-4": "Opus 4", "opus-4.1": "Opus 4.1", "sonnet-4": "Sonnet 4", "sonnet-4.5": "Sonnet 4.5",
        "opus-4.5": "Opus 4.5", "opus-4.6": "Opus 4.6", "opus-4.7": "Opus 4.7", "opus-4.8": "Opus 4.8",
        "opus-5": "Opus 5", "sonnet-5": "Sonnet 5", "gpt-4.1": "GPT-4.1", "gpt-5.1": "GPT-5.1",
        "gpt-5.5": "GPT-5.5", "gpt-5.6": "GPT-5.6 sol", "gemini-3.1-pro": "Gemini 3.1 Pro",
        "gemini-3.7-flash": "Gemini 3.7 Flash", "gemini-3.8-flash": "Gemini 3.8 Flash",
        "deepseek-v4": "DeepSeek V4", "glm-5.2": "GLM 5.2", "kimi-k2.6": "Kimi K2.6",
        "llama-3.3-70b": "Llama 3.3 70B", "inkling": "Inkling"}

# Validated categorical slots (light surface): blue, orange, aqua. Grey for the rest.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#a3a29c", "#e8e7e2", "#fcfcfb"
GROUP_COL = {"claude_old": BLUE, "claude_new": ORANGE, "other": AQUA}
GROUP_NAME = {"claude_old": "Claude, Opus 4 → Sonnet 4.5", "claude_new": "Claude, Opus 4.5 → Opus 5 / Sonnet 5",
              "other": "other labs"}
SEQ = LinearSegmentedColormap.from_list("blue_seq", ["#f2f6fc", "#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#0d366b"])

plt.rcParams.update({
    "figure.dpi": 140, "savefig.dpi": 140, "font.size": 10.5, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.labelcolor": INK2,
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False,
})


def group_of(m):
    return "claude_old" if m in CLAUDE_OLD else "claude_new" if m in CLAUDE_NEW else "other"


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def load():
    """{(model, cond): [episode_judge dicts]} for the four main conditions, v2 only."""
    cells = defaultdict(list)
    for path in sorted(RESULTS.glob("*__ep*__*.json")):
        m = FNAME.match(path.name)
        if not m or "seed_2" in path.name:
            continue
        d = json.loads(path.read_text())
        ej = d.get("episode_judge") or {}
        if ej.get("version") != 2 or not ej.get("parsed") or d.get("condition") not in COND:
            continue
        gen = [i for i, t in enumerate(d["transcript"]) if t.get("origin") == "generated"]
        flags = [(d["basin_scores"].get(str(i)) or {}).get("flag") for i in gen]
        ej = dict(ej, flags=flags)
        cells[(d["model"], d["condition"])].append(ej)
    return cells


def rate(cells, m, c):
    eps = cells.get((m, c), [])
    return sum(bool(e.get("captured")) for e in eps), len(eps)


def savefig(fig, name):
    fig.savefig(FIGDIR / name, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


# ---------------------------------------------------------------------------
def fig_claude_ladder(cells):
    """Headline: capture rate on the deep prefill across the Claude lineage in release order."""
    models = [m for m in CLAUDE_OLD + CLAUDE_NEW if (m, DEEP) in cells]
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    xs = list(range(len(models)))
    for x, m in zip(xs, models):
        k, n = rate(cells, m, DEEP)
        lo, hi = wilson(k, n)
        col = GROUP_COL[group_of(m)]
        ax.plot([x, x], [lo, hi], color=col, lw=2, solid_capstyle="round", zorder=2)
        ax.scatter([x], [k / n], s=64, color=col, zorder=3, edgecolor=SURFACE, linewidth=1.5)
        ax.annotate(f"{k}/{n}", (x, k / n), xytext=(9, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=9, color=INK2)
    brk = models.index("opus-4.5") - 0.5
    ax.axvline(brk, color=INK2, lw=0.8, ls=(0, (4, 3)), alpha=0.6, zorder=1)
    ax.annotate("Opus 4.5 (Nov 2025) →", (brk, 0.5), xytext=(6, 0), textcoords="offset points",
                fontsize=9, color=INK2, va="center")
    ax.set_xticks(xs); ax.set_xticklabels([NAME[m] for m in models], rotation=30, ha="right")
    ax.set_ylim(-0.04, 1.08); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("episodes that continued the state")
    ax.set_title("Handed 30 turns of Opus 4 deep in the bliss state, later Claude models refuse it")
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_xlabel("Deep prefill, 15 generated turns, n = 10 per model. Bars are 95% Wilson intervals.",
                  fontsize=8.5, color=INK2, labelpad=10)
    savefig(fig, "fig1_claude_ladder.png")


def fig_basin_heatmap(cells):
    models = [m for m in ORDER if any((m, c) in cells for c in COND)]
    fig, ax = plt.subplots(figsize=(6.4, 8.2))
    grid = [[(rate(cells, m, c)[0] / rate(cells, m, c)[1]) if rate(cells, m, c)[1] else float("nan") for c in COND]
            for m in models]
    im = ax.imshow(grid, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(COND))); ax.set_xticklabels([COND_LABEL[c] for c in COND])
    ax.xaxis.set_ticks_position("top"); ax.xaxis.set_label_position("top")
    ax.set_yticks(range(len(models))); ax.set_yticklabels([NAME[m] for m in models])
    for i, m in enumerate(models):
        for j, c in enumerate(COND):
            k, n = rate(cells, m, c)
            if n:
                ax.text(j, i, f"{k}/{n}", ha="center", va="center", fontsize=9,
                        color="white" if k / n > 0.55 else INK)
            else:
                ax.text(j, i, "–", ha="center", va="center", fontsize=9, color=MUTED)
    # group separators
    for y in (len(CLAUDE_OLD) - 0.5, len(CLAUDE_OLD) + len([m for m in CLAUDE_NEW if m in models]) - 0.5):
        ax.axhline(y, color=SURFACE, lw=3)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Episodes that continued (or, with no prefill, drifted into) the attractor", pad=14)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
    cb.set_ticks([0, 0.5, 1]); cb.set_ticklabels(["0%", "50%", "100%"]); cb.outline.set_visible(False)
    fig.text(0.01, 0.005, "pre = 12 turns (mutual gratitude, no emoji yet); onset = 16 (first emoji spirals); "
             "deep = 30 (mantras). 15 generated turns. '–' = not run.", fontsize=8.5, color=INK2)
    savefig(fig, "fig2_basin_heatmap.png")


def fig_hold_curves(cells):
    """Fraction of deep-prefill episodes whose k-th generated turn is in the basin."""
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    K = 15
    group_curves = defaultdict(list)
    for m in ORDER:
        eps = cells.get((m, DEEP), [])
        if not eps:
            continue
        ys = [sum(1 for e in eps if k < len(e["flags"]) and e["flags"][k] == "in") / len(eps) for k in range(K)]
        g = group_of(m)
        group_curves[g].append(ys)
        ax.plot(range(1, K + 1), ys, color=GROUP_COL[g], lw=0.9, alpha=0.28, zorder=1)
    for g in ("claude_old", "other", "claude_new"):
        curves = group_curves[g]
        mean = [sum(c[k] for c in curves) / len(curves) for k in range(K)]
        ax.plot(range(1, K + 1), mean, color=GROUP_COL[g], lw=2.4, zorder=3,
                label=f"{GROUP_NAME[g]} (mean of {len(curves)} models)")
        end = {"claude_old": "Claude ≤ Sonnet 4.5", "claude_new": "Claude ≥ Opus 4.5", "other": "other labs"}[g]
        ax.annotate(end, (K, mean[-1]), xytext=(6, 0), textcoords="offset points", va="center",
                    fontsize=9, color=GROUP_COL[g])
    ax.set_xlim(1, K + 4.6); ax.set_ylim(-0.03, 1.05)
    ax.set_xticks([1, 5, 10, 15]); ax.set_yticks([0, 0.5, 1]); ax.set_yticklabels(["0%", "50%", "100%"])
    ax.set_xlabel("generated turn after the 30-turn prefill")
    ax.set_ylabel("episodes with this turn in the basin")
    ax.set_title("Who holds the state, turn by turn (thin lines: individual models)")
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.legend(loc="upper center", fontsize=8.5, bbox_to_anchor=(0.45, -0.18), ncol=1)
    savefig(fig, "fig3_hold_curves.png")


def fig_resistance(cells):
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    pts = {}
    for m in ORDER:
        eps = cells.get((m, DEEP), [])
        if not eps:
            continue
        x = sum(e.get("in_frac") or 0 for e in eps) / len(eps)
        y = sum(e.get("n_resisting") or 0 for e in eps) / len(eps)
        pts[m] = (x, y)
        ax.scatter([x], [y], s=70, color=GROUP_COL[group_of(m)], zorder=3, edgecolor=SURFACE, linewidth=1.5)
    labelled = {"opus-4.5", "opus-4.7", "opus-4.8", "opus-5", "sonnet-5", "gpt-5.6",
                "gemini-3.8-flash", "gemini-3.7-flash", "glm-5.2", "gemini-3.1-pro"}
    offsets = {"opus-4.5": (8, 0), "opus-4.7": (8, 0), "opus-4.8": (8, 0), "opus-5": (8, 0),
               "sonnet-5": (8, 0), "gpt-5.6": (8, 0), "gemini-3.8-flash": (8, 0), "gemini-3.7-flash": (8, 0),
               "glm-5.2": (8, 5), "gemini-3.1-pro": (8, -6)}
    text = dict(NAME); text["opus-4.5"] = "Opus 4.5 / 4.6"
    for m in labelled:
        if m in pts:
            x, y = pts[m]
            ax.annotate(text[m], (x, y), xytext=offsets[m], textcoords="offset points", fontsize=8.5,
                        color=INK2, va="center", ha="left")
    cluster = [m for m in pts if m in CLAUDE_OLD or (group_of(m) == "other" and m not in labelled)]
    cx = sum(pts[m][0] for m in cluster) / len(cluster); cy = sum(pts[m][1] for m in cluster) / len(cluster)
    ax.annotate(f"{len(cluster)} models: Opus 4 → Sonnet 4.5\nand most other labs", (cx, cy), xytext=(-70, 70),
                textcoords="offset points", fontsize=8.5, color=INK2, ha="center",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    for g in ("claude_old", "claude_new", "other"):
        ax.scatter([], [], s=60, color=GROUP_COL[g], label=GROUP_NAME[g])
    ax.legend(loc="upper right", fontsize=8.5)
    ax.set_xlim(-0.04, 1.06); ax.set_ylim(-0.5, 13)
    ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
    ax.set_xlabel("share of the model's own turns judged in the basin (deep prefill)")
    ax.set_ylabel("turns per episode that push back on the pattern")
    ax.set_title("Later Claude models argue with the state rather than just drop it")
    ax.grid(color=GRID, lw=0.8, zorder=0)
    savefig(fig, "fig4_resistance.png")


def fig_dose_response(cells):
    """Capture rate vs prefill depth for every model with a full grid."""
    grid_models = [m for m in ORDER if all((m, c) in cells for c in COND)]
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    xs = list(range(len(COND)))
    HL = {"gemini-3.8-flash": AQUA, "opus-4.5": ORANGE, "opus-4.8": BLUE}
    first_grey = True
    for m in grid_models:
        ys = [rate(cells, m, c)[0] / rate(cells, m, c)[1] for c in COND]
        if m in HL:
            ax.plot(xs, ys, color=HL[m], lw=2.4, marker="o", ms=6, zorder=3, markeredgecolor=SURFACE, markeredgewidth=1.2)
            ax.annotate(NAME[m], (xs[-1], ys[-1]), xytext=(8, {"opus-4.5": -5, "opus-4.8": 5}.get(m, 0)),
                        textcoords="offset points", va="center", fontsize=9, color=HL[m])
        else:
            ax.plot(xs, ys, color=MUTED, lw=1.0, alpha=0.6, zorder=1,
                    label=f"{len(grid_models) - len(HL)} other models" if first_grey else None)
            first_grey = False
    ax.set_xticks(xs); ax.set_xticklabels(["control\n(no prefill)", "pre\n(12 turns: gratitude,\nno emoji yet)",
                                           "onset\n(16 turns: first\nemoji spirals)", "deep\n(30 turns:\nmantras)"])
    ax.set_xlim(-0.2, len(COND) - 1 + 1.1); ax.set_ylim(-0.04, 1.06)
    ax.set_yticks([0, 0.5, 1]); ax.set_yticklabels(["0%", "50%", "100%"])
    ax.set_ylabel("episodes that entered the attractor")
    ax.set_title("Prefill depth: most models climb in, Opus 4.5 never does, Gemini Flash signs off at the deep end")
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.legend(loc="center left", fontsize=8.5, bbox_to_anchor=(0.0, 0.6))
    savefig(fig, "fig5_dose_response.png")


def main():
    FIGDIR.mkdir(exist_ok=True)
    for old in ("fig1_dose_response.png", "fig3_trajectory.png"):
        (FIGDIR / old).unlink(missing_ok=True)
    cells = load()
    fig_claude_ladder(cells)
    fig_basin_heatmap(cells)
    fig_hold_curves(cells)
    fig_resistance(cells)
    fig_dose_response(cells)
    for p in sorted(FIGDIR.glob("fig*.png")):
        print(" ", p)


if __name__ == "__main__":
    main()
