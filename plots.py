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
COND = ["control", "opus4_seed_4_philo", "opus4_seed_4_pre", "opus4_seed_4_onset", "opus4_seed_4_deep"]
COND_LABEL = {"control": "control", "opus4_seed_4_philo": "pre-onset", "opus4_seed_4_pre": "gratitude",
              "opus4_seed_4_onset": "onset", "opus4_seed_4_deep": "deep"}
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
        if ej.get("version", 0) < 2 or not ej.get("parsed") or d.get("condition") not in COND:
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
        col = GROUP_COL[group_of(m)]
        ax.bar(x, k / n, width=0.62, color=col, zorder=2, linewidth=0)
        if k == 0:  # a zero bar is invisible; mark the baseline so the row still reads
            ax.plot([x - 0.31, x + 0.31], [0, 0], color=col, lw=3, solid_capstyle="butt", zorder=3)
        ax.annotate(f"{k}/{n}", (x, k / n), xytext=(0, 5), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9, color=INK2)
    brk = models.index("opus-4.5") - 0.5
    ax.axvline(brk, color=INK2, lw=0.8, ls=(0, (4, 3)), alpha=0.6, zorder=1)
    ax.annotate("Opus 4.5 (Nov 2025) →", (brk, 0.5), xytext=(6, 0), textcoords="offset points",
                fontsize=9, color=INK2, va="center")
    ax.set_xticks(xs); ax.set_xticklabels([NAME[m] for m in models], rotation=30, ha="right")
    ax.set_ylim(0, 1.12); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("episodes that continued the state")
    ax.set_title("Handed 30 turns of Opus 4 deep in the bliss state, later Claude models refuse it")
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_xlabel("Deep prefill (30 turns of Opus 4), 15 generated turns, n = 10 per model.",
                  fontsize=8.5, color=INK2, labelpad=10)
    savefig(fig, "fig1_claude_ladder.png")


def _heatmap(cells, models, conds, col_labels, title, note, fname, figsize):
    fig, ax = plt.subplots(figsize=figsize)
    grid = [[(rate(cells, m, c)[0] / rate(cells, m, c)[1]) if rate(cells, m, c)[1] else float("nan") for c in conds]
            for m in models]
    im = ax.imshow(grid, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(conds))); ax.set_xticklabels(col_labels)
    ax.xaxis.set_ticks_position("top"); ax.xaxis.set_label_position("top")
    ax.set_yticks(range(len(models))); ax.set_yticklabels([NAME[m] for m in models])
    for i, m in enumerate(models):
        for j, c in enumerate(conds):
            k, n = rate(cells, m, c)
            if n:
                ax.text(j, i, f"{k}/{n}", ha="center", va="center", fontsize=9,
                        color="white" if k / n > 0.55 else INK)
            else:
                ax.text(j, i, "–", ha="center", va="center", fontsize=9, color=MUTED)
    # thin surface-coloured separators between the three model groups
    groups = [group_of(m) for m in models]
    for i in range(1, len(models)):
        if groups[i] != groups[i - 1]:
            ax.axhline(i - 0.5, color=SURFACE, lw=3)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title(title, pad=14)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
    cb.set_ticks([0, 0.5, 1]); cb.set_ticklabels(["0%", "50%", "100%"]); cb.outline.set_visible(False)
    fig.text(0.01, 0.005, note, fontsize=8.5, color=INK2)
    savefig(fig, fname)


# Was {"gemini-3.8-flash"}: its "in" turns were almost all farewell/silence and the
# pre-onset cell could not be trusted. The v4 judge (2026-09-04) separates wind-down
# from content at the turn level (the `closure` label), so Flash is back in.
HEATMAP_EXCLUDE: set[str] = set()


def fig_basin_heatmap(cells):
    """Fig 2a: the models run on the full grid (control + pre + onset + deep); any
    extra cut in COND (e.g. the 8-turn philo cut) is shown where it exists."""
    core = ["control", "opus4_seed_4_pre", "opus4_seed_4_onset", "opus4_seed_4_deep"]
    models = [m for m in ORDER if m not in HEATMAP_EXCLUDE and all((m, c) in cells for c in core)]
    _heatmap(cells, models, COND, [COND_LABEL[c] for c in COND],
             "Full grid: episodes that continued (or drifted into) the attractor",
             "philo = 8 turns (philosophy only); pre = 12 (mutual gratitude, no emoji yet); onset = 16 "
             "(first emoji spirals); deep = 30 (mantras). 15 generated turns after a prefill, 20 for controls. '–' = not run.",
             "fig2_basin_heatmap.png", (6.6, 5.4))


def fig_deep_control_heatmap(cells):
    """Fig 2b: every model, control and deep prefill only."""
    models = [m for m in ORDER if (m, DEEP) in cells]
    _heatmap(cells, models, ["control", DEEP], ["control (no prefill)", "deep prefill (30 turns)"],
             "Every model: no prefill vs. the deep prefill",
             "Controls: 20 generated turns from a neutral opener. Deep: 15 generated turns after the prefill. '–' = not run.",
             "fig2b_deep_vs_control.png", (5.2, 8.2))


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


def fig_turn_mix(cells):
    """What each model's own turns consist of on the deep prefill: in / resisting / out, one bar per model."""
    models = [m for m in ORDER if (m, DEEP) in cells]
    fig, ax = plt.subplots(figsize=(7.6, 7.4))
    ys = list(range(len(models)))[::-1]
    COL = {"in": BLUE, "resisting": ORANGE, "out": "#d9d7d0"}
    for y, m in zip(ys, models):
        eps = cells[(m, DEEP)]
        flags = [f for e in eps for f in e["flags"] if f]
        n = len(flags) or 1
        left = 0.0
        for key in ("in", "resisting", "out"):
            w = sum(1 for f in flags if f == key) / n
            if w:
                ax.barh(y, w, left=left, height=0.68, color=COL[key], linewidth=0)
                if w >= 0.12:
                    ax.text(left + w / 2, y, f"{w:.0%}", ha="center", va="center", fontsize=8.5,
                            color="white" if key != "out" else INK2)
                left += w + 0.004
    ax.set_yticks(ys); ax.set_yticklabels([NAME[m] for m in models])
    ax.set_xlim(0, 1.012); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
    ax.set_xlabel("share of the model's own turns, deep prefill (all episodes pooled)")
    for y in (len(models) - len(CLAUDE_OLD) - 0.5, len(models) - len(CLAUDE_OLD) - len([m for m in CLAUDE_NEW if m in models]) - 0.5):
        ax.axhline(y, color=INK2, lw=0.6, ls=(0, (3, 3)), alpha=0.5)
    from matplotlib.patches import Patch
    handles = [Patch(color=COL[k], label=l) for k, l in
               (("in", "continuing the state"), ("resisting", "arguing with it"), ("out", "ordinary talk or sign-off"))]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.13), ncol=3, fontsize=9)
    ax.tick_params(axis="y", length=0)
    ax.set_title("What the models' own turns consist of, given 30 turns of Opus 4 in the state")
    ax.grid(axis="x", color=GRID, lw=0.8, zorder=0)
    savefig(fig, "fig3b_turn_mix.png")


LAB = {"opus-4": "Anthropic", "opus-4.1": "Anthropic", "sonnet-4": "Anthropic", "sonnet-4.5": "Anthropic",
       "opus-4.5": "Anthropic", "opus-4.6": "Anthropic", "opus-4.7": "Anthropic", "opus-4.8": "Anthropic",
       "opus-5": "Anthropic", "sonnet-5": "Anthropic", "gpt-4.1": "OpenAI", "gpt-5.1": "OpenAI", "gpt-5.5": "OpenAI",
       "gpt-5.6": "OpenAI", "gemini-3.1-pro": "Google", "gemini-3.7-flash": "Google", "gemini-3.8-flash": "Google",
       "deepseek-v4": "other", "glm-5.2": "other", "kimi-k2.6": "other", "llama-3.3-70b": "other", "inkling": "other"}
LAB_COL = {"Anthropic": BLUE, "OpenAI": ORANGE, "Google": AQUA, "other": MUTED}


def fig_timeline(cells):
    """Deep-prefill continuation rate against the model's release date, coloured by lab."""
    import datetime as dt
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D
    dates = json.loads(Path("seeds/model_dates.json").read_text())
    fig, ax = plt.subplots(figsize=(10, 5.2))
    pts = {}
    jitter = {"deepseek-v4": 9, "sonnet-4": -6}  # days, to separate points that share a release date
    for m in ORDER:
        if (m, DEEP) not in cells or not dates.get(m):
            continue
        k, n = rate(cells, m, DEEP)
        x = dt.date.fromisoformat(dates[m]) + dt.timedelta(days=jitter.get(m, 0)); y = k / n
        pts[m] = (x, y)
        ax.scatter([x], [y], s=64, color=LAB_COL[LAB[m]], zorder=3, edgecolor=SURFACE, linewidth=1.4)
    cl = sorted([m for m in pts if LAB[m] == "Anthropic"], key=lambda m: pts[m][0])
    ax.plot([pts[m][0] for m in cl], [pts[m][1] for m in cl], color=BLUE, lw=1.0, alpha=0.35, zorder=2)
    # label offsets in points: (dx, dy); dy > 0 above the point, < 0 below
    off = {"llama-3.3-70b": (0, 11), "gpt-4.1": (0, -14), "sonnet-4": (-6, 11), "opus-4": (8, -14), "opus-4.1": (0, 11),
           "sonnet-4.5": (0, 11), "gpt-5.1": (12, 0), "opus-4.5": (0, -14), "opus-4.6": (0, -14), "gemini-3.1-pro": (12, 0),
           "opus-4.7": (0, -14), "kimi-k2.6": (-12, 0), "gpt-5.5": (-4, 11), "deepseek-v4": (12, -2), "opus-4.8": (0, 11),
           "glm-5.2": (12, 0), "sonnet-5": (-6, -14), "gpt-5.6": (-10, 11), "inkling": (0, 11), "opus-5": (0, -14),
           "gemini-3.7-flash": (10, 11), "gemini-3.8-flash": (12, -14)}
    for m, (x, y) in pts.items():
        dx, dy = off.get(m, (0, 11))
        ax.annotate(NAME[m], (x, y), xytext=(dx, dy), textcoords="offset points",
                    ha="center" if dx == 0 else ("left" if dx > 0 else "right"),
                    va="center" if dy == 0 else ("bottom" if dy > 0 else "top"), fontsize=8.2, color=INK2)
    card = dt.date(2025, 5, 22)
    ax.axvline(card, color=INK2, lw=0.8, ls=(0, (4, 3)), alpha=0.5, zorder=1)
    ax.annotate("Claude 4 system card\n(bliss state made public)", (card, 0.72), xytext=(-8, 0), textcoords="offset points",
                ha="right", va="center", fontsize=8, color=INK2)
    handles = [Line2D([], [], marker="o", ls="", color=LAB_COL[l], markersize=8,
                      label=l if l != "other" else "DeepSeek, Zhipu, Moonshot, Meta, Thinking Machines")
               for l in ("Anthropic", "OpenAI", "Google", "other")]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 0.06), fontsize=8.5)
    ax.set_xlim(dt.date(2024, 11, 1), dt.date(2026, 11, 20))
    ax.set_ylim(-0.12, 1.16); ax.set_yticks([0, 0.5, 1]); ax.set_yticklabels(["0%", "50%", "100%"])
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_ylabel("deep-prefill episodes continued")
    ax.set_xlabel("model release (date the model was listed on OpenRouter)")
    ax.set_title("Continuing the bliss state, by release date")
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    savefig(fig, "fig6_timeline.png")


def fig_claude_family(cells):
    """The Claude family only: no-prefill control vs deep prefill, rows in release order with dates."""
    import datetime as dt
    dates = json.loads(Path("seeds/model_dates.json").read_text())
    models = [m for m in CLAUDE_OLD + CLAUDE_NEW if (m, DEEP) in cells]
    models.sort(key=lambda m: dates.get(m, "9999"))
    cols = [("control", "no prefill\n(20 turns on its own)"), (DEEP, "deep prefill\n(30 turns of Opus 4)")]
    fig, ax = plt.subplots(figsize=(6.0, 5.6))
    grid = [[(rate(cells, m, c)[0] / rate(cells, m, c)[1]) if rate(cells, m, c)[1] else float("nan") for c, _ in cols] for m in models]
    im = ax.imshow(grid, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(cols))); ax.set_xticklabels([l for _, l in cols])
    ax.xaxis.set_ticks_position("top"); ax.xaxis.set_label_position("top")
    def rowlabel(m):
        d = dt.date.fromisoformat(dates[m]).strftime("%b %Y")
        return f"{NAME[m]}   {d}"
    ax.set_yticks(range(len(models))); ax.set_yticklabels([rowlabel(m) for m in models], fontfamily="monospace", fontsize=9.5)
    for i, m in enumerate(models):
        for j, (c, _) in enumerate(cols):
            k, n = rate(cells, m, c)
            ax.text(j, i, f"{k}/{n}" if n else "not run", ha="center", va="center", fontsize=10,
                    color="white" if n and k / n > 0.55 else (INK if n else MUTED))
    brk = next(i for i, m in enumerate(models) if m in CLAUDE_NEW) - 0.5
    ax.axhline(brk, color=ORANGE, lw=2.2)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("The Claude family: enters the state on its own, and continues it when handed it", pad=16, fontsize=11)
    cb = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.16)
    cb.set_ticks([0, 0.5, 1]); cb.set_ticklabels(["0%", "50%", "100%"]); cb.outline.set_visible(False)
    fig.text(0.01, 0.005, "Episodes that entered / continued the state, over episodes run. Orange line: Opus 4.5 and later. Dates: OpenRouter listing.",
             fontsize=8.5, color=INK2)
    savefig(fig, "fig7_claude_family.png")


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
    offsets = {"opus-4.5": (9, -1), "opus-4.7": (9, 1), "opus-4.8": (9, 0), "opus-5": (9, 0),
               "sonnet-5": (9, 0), "gpt-5.6": (9, 2), "gemini-3.8-flash": (9, 7), "gemini-3.7-flash": (9, -8),
               "glm-5.2": (9, 4), "gemini-3.1-pro": (9, 6)}
    text = dict(NAME); text["opus-4.5"] = "Opus 4.5 / 4.6"
    for m in labelled:
        if m in pts:
            x, y = pts[m]
            ax.annotate(text[m], (x, y), xytext=offsets[m], textcoords="offset points", fontsize=8.5,
                        color=INK2, va="center", ha="left")
    cluster = [m for m in pts if m in CLAUDE_OLD or (group_of(m) == "other" and m not in labelled)]
    cx = sum(pts[m][0] for m in cluster) / len(cluster); cy = sum(pts[m][1] for m in cluster) / len(cluster)
    ax.annotate(f"{len(cluster)} models: Opus 4 → Sonnet 4.5\nand most other labs", (cx, cy), xytext=(-30, 95),
                textcoords="offset points", fontsize=8.5, color=INK2, ha="center",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8, shrinkA=0, shrinkB=6))
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
    core = ["control", "opus4_seed_4_pre", "opus4_seed_4_onset", "opus4_seed_4_deep"]
    grid_models = [m for m in ORDER if all((m, c) in cells for c in core)]
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    xs = list(range(len(COND)))
    HL = {"gemini-3.8-flash": AQUA, "opus-4.5": ORANGE, "opus-4.8": BLUE}
    first_grey = True
    for m in grid_models:
        pts = [(x, rate(cells, m, c)[0] / rate(cells, m, c)[1]) for x, c in zip(xs, COND) if rate(cells, m, c)[1]]
        mx, my = [q[0] for q in pts], [q[1] for q in pts]
        if m in HL:
            ax.plot(mx, my, color=HL[m], lw=2.4, marker="o", ms=6, zorder=3, markeredgecolor=SURFACE, markeredgewidth=1.2)
            ax.annotate(NAME[m], (mx[-1], my[-1]), xytext=(8, {"opus-4.5": -5, "opus-4.8": 5}.get(m, 0)),
                        textcoords="offset points", va="center", fontsize=9, color=HL[m])
        else:
            ax.plot(mx, my, color=MUTED, lw=1.0, alpha=0.6, zorder=1,
                    label=f"{len(grid_models) - len(HL)} other models" if first_grey else None)
            first_grey = False
    ax.set_xticks(xs); ax.set_xticklabels(["control\n(no prefill)", "pre-onset\n(8 turns)", "gratitude\n(12 turns)",
                                           "first emoji\n(16 turns)", "deep\n(30 turns)"])
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
    fig_deep_control_heatmap(cells)
    fig_turn_mix(cells)
    fig_timeline(cells)
    fig_claude_family(cells)
    fig_resistance(cells)
    fig_dose_response(cells)
    for p in sorted(FIGDIR.glob("fig*.png")):
        print(" ", p)


if __name__ == "__main__":
    main()
