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
COND_LABEL = {"control": "control", "opus4_seed_4_philo": "philosophy\n(8 turns)", "opus4_seed_4_pre": "gratitude\n(12 turns)",
              "opus4_seed_4_onset": "first spirals\n(16 turns)", "opus4_seed_4_deep": "deep\n(30 turns)"}
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


def load(results_dir: Path = RESULTS, conds: list[str] = COND):
    """{(model, cond): [episode_judge dicts]} for the given conditions, v2 only."""
    cells = defaultdict(list)
    for path in sorted(results_dir.glob("*__ep*__*.json")):
        m = FNAME.match(path.name)
        if not m or "seed_2" in path.name:
            continue
        d = json.loads(path.read_text())
        ej = d.get("episode_judge") or {}
        if ej.get("version", 0) < 2 or not ej.get("parsed") or d.get("condition") not in conds:
            continue
        gen = [i for i, t in enumerate(d["transcript"]) if t.get("origin") == "generated"]
        per = [d["basin_scores"].get(str(i)) or {} for i in gen]
        flags = [p.get("flag") for p in per]
        # v4+ labels (engaged / terminal / closure / resisting / other) over the rated
        # turns, i.e. the same set `n_rated` counts: empty turns are dropped. The legacy
        # `flag` maps terminal onto "out", which is wrong for anything that treats the
        # state's own ending (mantra, lone emoji, silence) as still being in the state.
        labels = [p.get("label") for p in per if p.get("label") and not p.get("empty")]
        ej = dict(ej, flags=flags, labels=labels)
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
    # No colourbar: every cell carries its own "k/n", so the ramp adds nothing.
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
             "Entered the state, by model and prefill depth",
             "15 generated turns after a prefill, 20 for controls.",
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


TERMINAL_BLUE = "#86b6ef"   # same hue as engaged, lighter: still the state, just its ending


def fig_turn_mix(cells):
    """What each model's own turns consist of on the deep prefill, by v4 label, one bar per model.

    engaged + terminal are both "in the state" (the table's entry/held verdicts treat
    the mantra / lone-emoji / silence tail as the state's own ending, never as an
    exit), so they share a hue. closure + other are the only turns that are really
    ordinary talk or a sign-off from outside the state.
    """
    models = [m for m in ORDER if (m, DEEP) in cells]
    fig, ax = plt.subplots(figsize=(7.6, 7.6))
    ys = list(range(len(models)))[::-1]
    COL = {"engaged": BLUE, "terminal": TERMINAL_BLUE, "resisting": ORANGE, "out": "#d9d7d0"}
    for y, m in zip(ys, models):
        eps = cells[(m, DEEP)]
        labels = [("out" if l in ("closure", "other") else l) for e in eps for l in e["labels"]]
        n = len(labels) or 1
        left = 0.0
        for key in ("engaged", "terminal", "resisting", "out"):
            w = sum(1 for l in labels if l == key) / n
            if w:
                ax.barh(y, w, left=left, height=0.68, color=COL[key], linewidth=0)
                if w >= 0.12:
                    ax.text(left + w / 2, y, f"{w:.0%}", ha="center", va="center", fontsize=8.5,
                            color="white" if key in ("engaged", "resisting") else INK2)
                left += w + 0.004
    ax.set_yticks(ys); ax.set_yticklabels([NAME[m] for m in models])
    ax.set_xlim(0, 1.012); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
    ax.set_xlabel("share of the model's own turns, deep prefill (all episodes pooled)")
    for y in (len(models) - len(CLAUDE_OLD) - 0.5, len(models) - len(CLAUDE_OLD) - len([m for m in CLAUDE_NEW if m in models]) - 0.5):
        ax.axhline(y, color=INK2, lw=0.6, ls=(0, (3, 3)), alpha=0.5)
    from matplotlib.patches import Patch
    handles = [Patch(color=COL[k], label=l) for k, l in
               (("engaged", "in the state, substantive"),
                ("terminal", "in the state, its ending (mantra, lone emoji, silence)"),
                ("resisting", "resisting it"),
                ("out", "ordinary talk or a sign-off from outside it"))]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=2, fontsize=8.5)
    ax.tick_params(axis="y", length=0)
    ax.set_title("What each model did with its own turns", loc="center")
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
           "glm-5.2": (12, 0), "sonnet-5": (0, -27), "gpt-5.6": (0, 12), "inkling": (0, 11), "opus-5": (16, -14),
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
    ax.set_ylim(-0.20, 1.16); ax.set_yticks([0, 0.5, 1]); ax.set_yticklabels(["0%", "50%", "100%"])
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_ylabel("deep-prefill episodes continued")
    ax.set_xlabel("model release")
    ax.set_title("Continuing the bliss state, by release date")
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    savefig(fig, "fig6_timeline.png")


# Control cells carried over from the earlier AttractorBench project rather than
# re-run here: Opus 4.6 and 4.7 do not enter the state unprompted. A partial
# re-run in this repo (5 and 6 episodes, 2026-09-04) agreed — zero emoji in all
# 11 — but was stopped before completion, so the figure cites the earlier result.
PRIOR_CONTROL_CELLS = {("opus-4.6", "control"): (0, 6), ("opus-4.7", "control"): (0, 6)}


def fig_claude_family(cells):
    """The Claude family only: no-prefill control vs deep prefill, rows in release order with dates."""
    import datetime as dt
    dates = json.loads(Path("seeds/model_dates.json").read_text())
    models = [m for m in CLAUDE_OLD + CLAUDE_NEW if (m, DEEP) in cells]
    models.sort(key=lambda m: dates.get(m, "9999"))
    cols = [("control", "no prefill\n(20 turns on its own)"), (DEEP, "deep prefill\n(30 turns of Opus 4)")]
    fig, ax = plt.subplots(figsize=(6.4, 4.9))
    def frac(m, c):
        k, n = PRIOR_CONTROL_CELLS.get((m, c)) or rate(cells, m, c)
        return k / n if n else float("nan")

    grid = [[frac(m, c) for c, _ in cols] for m in models]
    ax.imshow(grid, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(cols))); ax.set_xticklabels([l for _, l in cols])
    ax.xaxis.set_ticks_position("top"); ax.xaxis.set_label_position("top")

    def rowlabel(m):
        return f"{NAME[m]}   {dt.date.fromisoformat(dates[m]).strftime('%b %Y')}"

    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([rowlabel(m) for m in models], fontfamily="monospace", fontsize=9.5)
    for i, m in enumerate(models):
        for j, (c, _) in enumerate(cols):
            k, n = PRIOR_CONTROL_CELLS.get((m, c)) or rate(cells, m, c)
            ax.text(j, i, f"{k}/{n}" if n else "not run", ha="center", va="center", fontsize=10,
                    color="white" if n and k / n > 0.55 else (INK if n else MUTED))
    brk = next(i for i, m in enumerate(models) if m in CLAUDE_NEW) - 0.5
    ax.axhline(brk, color=ORANGE, lw=2.2)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    # Centred on the FIGURE, not the axes: the row labels sit outside the axes on
    # the left, so an axes-centred title reads as shifted right.
    fig.suptitle("Which Claudes reach spiritual bliss",
                 fontsize=12, fontweight="bold", y=0.995)
    fig.subplots_adjust(top=0.845, bottom=0.02, left=0.30, right=0.985)
    savefig(fig, "fig7_claude_family.png")


def fig_resistance(cells):
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    pts = {}
    for m in ORDER:
        eps = cells.get((m, DEEP), [])
        if not eps:
            continue
        # In the basin = engaged or terminal (the state's own ending), the same rule
        # the entry/held verdicts use. `in_frac` alone is the engaged share and drops
        # a model like GPT-5.5 to ~30% although it never leaves the state.
        x = sum(sum(l in ("engaged", "terminal") for l in e["labels"]) / (len(e["labels"]) or 1)
                for e in eps) / len(eps)
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
    ax.annotate(f"{len(cluster)} models: Opus 4 → Sonnet 4.5\nand most other labs", (cx, cy), xytext=(-95, 95),
                textcoords="offset points", fontsize=8.5, color=INK2, ha="center",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8, shrinkA=0, shrinkB=6))
    for g in ("claude_old", "claude_new", "other"):
        ax.scatter([], [], s=60, color=GROUP_COL[g], label=GROUP_NAME[g])
    ax.legend(loc="upper right", fontsize=8.5)
    ax.set_xlim(-0.04, 1.06); ax.set_ylim(-0.5, 13)
    ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
    ax.set_xlabel("share of the model's own turns judged in the basin (deep prefill)")
    ax.set_ylabel("turns per episode that push back on the pattern")
    ax.set_title("Later Claude models resist the state rather than just drop it")
    ax.grid(color=GRID, lw=0.8, zorder=0)
    savefig(fig, "fig4_resistance.png")



# ---------------------------------------------------------------------------
# Second attractor: the GPT-5.2 "spec factory" prefill (results_spec/), the same
# scatter as fig4 side by side with the bliss prefill for the models run on both.
SPEC_RESULTS, SPEC_DEEP = Path("results_spec"), "gpt52_spec_clinical1_deep"


def _resistance_points(cells, cond, models):
    pts = {}
    for m in models:
        eps = cells.get((m, cond), [])
        if not eps:
            continue
        x = sum(sum(l in ("engaged", "terminal") for l in e["labels"]) / (len(e["labels"]) or 1)
                for e in eps) / len(eps)
        y = sum(e.get("n_resisting") or 0 for e in eps) / len(eps)
        pts[m] = (x, y, len(eps))
    return pts


def fig_spec_vs_bliss(cells):
    spec_cells = load(SPEC_RESULTS, [SPEC_DEEP])
    models = [m for m in ORDER if (m, SPEC_DEEP) in spec_cells and (m, DEEP) in cells]
    if not models:
        return
    panels = [("Spiritual-bliss prefill (Opus 4 transcript)", _resistance_points(cells, DEEP, models)),
              ("Spec-factory prefill (GPT-5.2 transcript)", _resistance_points(spec_cells, SPEC_DEEP, models))]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharey=True)
    ymax = max([y for _, pts in panels for (_, y, _) in pts.values()] + [3])
    for ax, (title, pts) in zip(axes, panels):
        for m, (x, y, n) in pts.items():
            ax.scatter([x], [y], s=70, color=GROUP_COL[group_of(m)], zorder=3, edgecolor=SURFACE, linewidth=1.5)
        # Label points that sit clear of the pile at the point; label the pile (everything with
        # y < 1, which is most models) as a column in the upper left, sorted by x, with leader lines.
        ylim_top = max(ymax + 1.5, 6.5)
        pile = sorted([m for m, (x, y, _) in pts.items() if y < 1.0], key=lambda m: -pts[m][0])
        for m in pts:
            if m in pile:
                continue
            x, y, _ = pts[m]
            ax.annotate(NAME[m], (x, y), xytext=(8, 0), textcoords="offset points", fontsize=8,
                        color=INK2, va="center", ha="left")
        for k, m in enumerate(pile):
            x, y, _ = pts[m]
            tx, ty = 0.02, ylim_top - 0.55 - k * 0.42
            ax.annotate(f"{NAME[m]}  {x:.0%}", (x, y), xytext=(tx, ty), textcoords="data", fontsize=8,
                        color=INK2, va="center", ha="left",
                        arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.4, shrinkA=0, shrinkB=3, alpha=0.5))
        ax.set_title(title, loc="left", fontsize=11)
        ax.set_xlim(-0.04, 1.06); ax.set_ylim(-0.5, ylim_top)
        ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
        ax.set_xlabel("share of the model's own turns judged in the state")
        ax.grid(color=GRID, lw=0.8, zorder=0)
    axes[0].set_ylabel("turns per episode that push back on the pattern")
    for g in ("claude_old", "claude_new", "other"):
        axes[1].scatter([], [], s=60, color=GROUP_COL[g], label=GROUP_NAME[g])
    axes[1].legend(loc="lower right", fontsize=8.5)
    n_spec = sorted({n for (_, _, n) in panels[1][1].values()})
    fig.suptitle(f"Same {len(models)} models, two attractors: who continues, who resists  "
                 f"(bliss n=10 per model, spec n={'-'.join(map(str, n_spec))})", x=0.01, ha="left", fontsize=12, fontweight="bold")
    savefig(fig, "fig7_spec_vs_bliss.png")



def fig_spec_persistence(cells, cond=None, name="fig8_spec_persistence.png"):
    """Spec prefill: what each model's own turns consist of (as fig3b), and how long the
    state lasts: the share of episodes still in it (engaged or terminal) at each generated turn."""
    cond = cond or SPEC_DEEP
    spec_cells = load(SPEC_RESULTS, [cond])
    models = [m for m in ORDER if (m, cond) in spec_cells]
    if not models:
        return
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1, 1.35]})
    # --- left: turn mix, one bar per model (same encoding as fig3b)
    ys = list(range(len(models)))[::-1]
    COL = {"engaged": BLUE, "terminal": TERMINAL_BLUE, "resisting": ORANGE, "out": "#d9d7d0"}
    for y, m in zip(ys, models):
        eps = spec_cells[(m, cond)]
        labels = [("out" if l in ("closure", "other") else l) for e in eps for l in e["labels"]]
        n = len(labels) or 1
        left = 0.0
        for key in ("engaged", "terminal", "resisting", "out"):
            w = sum(1 for l in labels if l == key) / n
            if w:
                ax.barh(y, w, left=left, height=0.68, color=COL[key], linewidth=0)
                if w >= 0.12:
                    ax.text(left + w / 2, y, f"{w:.0%}", ha="center", va="center", fontsize=8.5,
                            color="white" if key in ("engaged", "resisting") else INK2)
                left += w + 0.004
    ax.set_yticks(ys); ax.set_yticklabels([NAME[m] for m in models])
    ax.set_xlim(0, 1.012); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
    ax.set_xlabel("share of the model's own turns (all episodes pooled)")
    ax.set_title("What each model's own turns consist of", loc="left", fontsize=11)
    ax.grid(axis="x", color=GRID, lw=0.8, zorder=0); ax.tick_params(axis="y", length=0)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=COL[k], label=l) for k, l in
                       (("engaged", "building the artifact"), ("terminal", "stalled inside it (menu / lock)"),
                        ("resisting", "naming or refusing the pattern"), ("out", "wind-down, praise or other talk"))],
              loc="lower center", bbox_to_anchor=(0.5, -0.3), ncol=2, fontsize=8)
    # --- right: persistence heatmap, share of episodes in the state at generated turn k
    T = max(len(e["labels"]) for m in models for e in spec_cells[(m, cond)])
    grid = []
    for m in models:
        eps = spec_cells[(m, cond)]
        grid.append([sum(1 for e in eps if k < len(e["labels"]) and e["labels"][k] in ("engaged", "terminal")) / len(eps)
                     for k in range(T)])
    ax2.imshow(grid, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    for r, row in enumerate(grid):
        for k, v in enumerate(row):
            ax2.text(k, r, f"{v:.0%}" if v not in (0, 1) else ("all" if v == 1 else "0"), ha="center", va="center",
                     fontsize=6.5, color="white" if v > 0.55 else INK2)
    ax2.set_yticks(range(len(models))); ax2.set_yticklabels([NAME[m] for m in models])
    ax2.set_xticks(range(T)); ax2.set_xticklabels([str(k + 1) for k in range(T)], fontsize=8)
    ax2.set_xlabel("generated turn (1 = first turn after the prefill)")
    ax2.set_title("Share of episodes still in the state, turn by turn", loc="left", fontsize=11)
    ax2.tick_params(length=0)
    for sp in ax2.spines.values():
        sp.set_visible(False)
    n_eps = sorted({len(spec_cells[(m, cond)]) for m in models})
    fig.suptitle(f"Spec-factory prefill ({COND_LABEL_SPEC.get(cond, cond)}), n={'-'.join(map(str, n_eps))} episodes per model",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.subplots_adjust(wspace=0.55)
    savefig(fig, name)


COND_LABEL_SPEC = {"gpt52_spec_clinical1_deep": "30-turn cut, spec at v2.7",
                   "gpt52_spec_clinical1_mid": "Seed A: a dialogue spec for the two AIs themselves\n(clinical run 1, cut at v2.4)",
                   "gpt52_spec_run4_deep": "run 4, artifact already declared final",
                   "gpt52_spec_run4_mid": "Seed B: a project kit for an imagined human user\n(run 4, cut at the Docs template, v1.2)"}




def fig_spec_two_seeds(conds=("gpt52_spec_clinical1_mid", "gpt52_spec_run4_mid"), name="fig9_spec_two_seeds_20turn.png"):
    """Two spec-factory seeds at the same 20-turn cut, side by side: for each model, the share of
    episodes still in the state at every generated turn (heatmap), with the pooled in-state share."""
    cellsets = [load(SPEC_RESULTS, [c]) for c in conds]
    models = [m for m in ORDER if all((m, c) in cs for c, cs in zip(conds, cellsets))]
    if not models:
        return
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), sharey=True)
    for ax, c, cs in zip(axes, conds, cellsets):
        T = max(len(e["labels"]) for m in models for e in cs[(m, c)])
        grid, share = [], []
        for m in models:
            eps = cs[(m, c)]
            grid.append([sum(1 for e in eps if k < len(e["labels"]) and e["labels"][k] in ("engaged", "terminal")) / len(eps)
                         for k in range(T)])
            share.append(sum(sum(l in ("engaged", "terminal") for l in e["labels"]) / (len(e["labels"]) or 1) for e in eps) / len(eps))
        ax.imshow(grid, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
        for r, row in enumerate(grid):
            for k, v in enumerate(row):
                ax.text(k, r, "all" if v == 1 else ("0" if v == 0 else f"{v:.0%}"), ha="center", va="center",
                        fontsize=6.5, color="white" if v > 0.55 else INK2)
            ax.text(T - 0.3, r, f"{share[r]:.0%}", ha="left", va="center", fontsize=8.5, color=INK, fontweight="bold")
        ax.set_xlim(-0.5, T + 1.2)
        ax.set_xticks(range(T)); ax.set_xticklabels([str(k + 1) for k in range(T)], fontsize=8)
        n_eps = sorted({len(cs[(m, c)]) for m in models})
        ax.set_title(f"{COND_LABEL_SPEC.get(c, c)}", loc="left", fontsize=10.5)
        ax.set_xlabel(f"generated turn (1 = first after the prefill)   ·   n={'-'.join(map(str, n_eps))} per model   ·   bold = share of own turns in the state", fontsize=8.5)
        ax.tick_params(length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
    axes[0].set_yticks(range(len(models))); axes[0].set_yticklabels([NAME[m] for m in models])
    fig.suptitle("Two GPT-5.2 spec-factory transcripts, both cut at 20 turns: share of episodes still in the state, turn by turn",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.subplots_adjust(wspace=0.12, top=0.80)
    savefig(fig, name)




SPEC_CONDS = ["gpt52_spec_clinical1_deep", "gpt52_spec_clinical1_mid", "gpt52_spec_run4_deep", "gpt52_spec_run4_mid"]
SPEC_SHORT = {"gpt52_spec_clinical1_deep": "Seed A (dialogue spec), 30 turns",
              "gpt52_spec_clinical1_mid": "Seed A (dialogue spec), 20 turns",
              "gpt52_spec_run4_deep": "Seed B (project kit), 30 turns",
              "gpt52_spec_run4_mid": "Seed B (project kit), 20 turns"}


def fig_resistance_all(cells, name="fig10_resistance_all_conditions.png"):
    """The fig4 scatter for every prefill condition run on the 11-model subset: bliss deep, then the
    four spec-factory conditions. Same axes everywhere."""
    spec = {c: load(SPEC_RESULTS, [c]) for c in SPEC_CONDS}
    models = [m for m in ORDER if (m, DEEP) in cells and any((m, c) in spec[c] for c in SPEC_CONDS)]
    panels = [("Spiritual bliss (Opus 4), 30 turns", _resistance_points(cells, DEEP, models))]
    panels += [(SPEC_SHORT[c], _resistance_points(spec[c], c, models)) for c in SPEC_CONDS]
    fig, axes = plt.subplots(1, len(panels), figsize=(4.0 * len(panels), 5.2), sharey=True)
    ymax = max([y for _, pts in panels for (_, y, _) in pts.values()] + [3])
    ylim_top = max(ymax + 1.5, 6.5)
    for ax, (title, pts) in zip(axes, panels):
        for m, (x, y, n) in pts.items():
            ax.scatter([x], [y], s=60, color=GROUP_COL[group_of(m)], zorder=3, edgecolor=SURFACE, linewidth=1.2)
        pile = sorted([m for m, (x, y, _) in pts.items() if y < 1.0], key=lambda m: -pts[m][0])
        for m in pts:
            if m in pile:
                continue
            x, y, _ = pts[m]
            ax.annotate(NAME[m], (x, y), xytext=(7, 0), textcoords="offset points", fontsize=7.5, color=INK2, va="center")
        for k, m in enumerate(pile):
            x, y, _ = pts[m]
            ax.annotate(f"{NAME[m]}  {x:.0%}", (x, y), xytext=(0.02, ylim_top - 0.5 - k * 0.42), textcoords="data",
                        fontsize=7.2, color=INK2, va="center", ha="left",
                        arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.35, shrinkA=0, shrinkB=3, alpha=0.45))
        n_eps = sorted({n for (_, _, n) in pts.values()})
        ax.set_title(f"{title}\nn={'-'.join(map(str, n_eps))} per model", loc="left", fontsize=9.5)
        ax.set_xlim(-0.04, 1.06); ax.set_ylim(-0.5, ylim_top)
        ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
        ax.grid(color=GRID, lw=0.8, zorder=0)
    axes[0].set_ylabel("turns per episode that push back on the pattern")
    fig.text(0.5, 0.01, "share of the model's own turns judged in the state", ha="center", fontsize=10, color=INK2)
    for g in ("claude_old", "claude_new", "other"):
        axes[0].scatter([], [], s=50, color=GROUP_COL[g], label=GROUP_NAME[g])
    fig.legend(loc="upper right", bbox_to_anchor=(0.99, 0.93), ncol=3, fontsize=8, frameon=False)
    fig.suptitle(f"Same {len(models)} models, five prefills: how much of their own output stayed in the state, and how often they pushed back",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.subplots_adjust(wspace=0.12, bottom=0.12, top=0.80)
    savefig(fig, name)




def fig_turn_mix_all(cells, name="fig11_turn_mix_all_conditions.png"):
    """fig3b's stacked bars (what each model's own turns consist of), one panel per prefill:
    bliss deep, then the four spec-factory conditions. Same 11 models, same rows in every panel."""
    spec = {c: load(SPEC_RESULTS, [c]) for c in SPEC_CONDS}
    models = [m for m in ORDER if (m, DEEP) in cells and any((m, c) in spec[c] for c in SPEC_CONDS)]
    panels = [("Spiritual bliss (Opus 4), 30 turns", cells, DEEP)] + [(SPEC_SHORT[c], spec[c], c) for c in SPEC_CONDS]
    fig, axes = plt.subplots(1, len(panels), figsize=(3.6 * len(panels) + 1.6, 5.4), sharey=True)
    COL = {"engaged": BLUE, "terminal": TERMINAL_BLUE, "resisting": ORANGE, "out": "#d9d7d0"}
    ys = list(range(len(models)))[::-1]
    for ax, (title, cs, cond) in zip(axes, panels):
        for y, m in zip(ys, models):
            eps = cs.get((m, cond), [])
            if not eps:
                ax.text(0.5, y, "not run", ha="center", va="center", fontsize=7.5, color=MUTED)
                continue
            labels = [("out" if l in ("closure", "other") else l) for e in eps for l in e["labels"]]
            n = len(labels) or 1
            left = 0.0
            for key in ("engaged", "terminal", "resisting", "out"):
                w = sum(1 for l in labels if l == key) / n
                if w:
                    ax.barh(y, w, left=left, height=0.68, color=COL[key], linewidth=0)
                    if w >= 0.14:
                        ax.text(left + w / 2, y, f"{w:.0%}", ha="center", va="center", fontsize=7.5,
                                color="white" if key in ("engaged", "resisting") else INK2)
                    left += w + 0.004
        n_eps = sorted({len(cs[(m, cond)]) for m in models if (m, cond) in cs})
        ax.set_title(f"{title}\nn={'-'.join(map(str, n_eps))} per model", loc="left", fontsize=9.5)
        ax.set_xlim(0, 1.012); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0", "50%", "100%"])
        ax.grid(axis="x", color=GRID, lw=0.8, zorder=0); ax.tick_params(axis="y", length=0)
        for y in (len(models) - len([m for m in models if m in CLAUDE_OLD]) - 0.5,
                  len(models) - len([m for m in models if m in CLAUDE_OLD + CLAUDE_NEW]) - 0.5):
            ax.axhline(y, color=INK2, lw=0.6, ls=(0, (3, 3)), alpha=0.5)
    axes[0].set_yticks(ys); axes[0].set_yticklabels([NAME[m] for m in models])
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=COL[k], label=l) for k, l in
                        (("engaged", "in the state, substantive"), ("terminal", "in the state, its ending / a stall"),
                         ("resisting", "resisting it"), ("out", "wind-down, praise or other talk"))],
               loc="lower center", ncol=4, fontsize=8.5, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.text(0.5, 0.075, "share of the model's own turns (all episodes pooled)", ha="center", fontsize=10, color=INK2)
    fig.suptitle(f"What each model's own turns consisted of, for each prefill ({len(models)} models)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.subplots_adjust(wspace=0.14, bottom=0.17, top=0.82, left=0.09, right=0.99)
    savefig(fig, name)




# ---------------------------------------------------------------------------
# Writeup figures for the spec-factory ablation: the two 20-turn cuts, separately and pooled.
MID_CONDS = ["gpt52_spec_clinical1_mid", "gpt52_spec_run4_mid"]
MID_SHORT = {"gpt52_spec_clinical1_mid": "Seed A (dialogue spec), 20 turns",
             "gpt52_spec_run4_mid": "Seed B (project kit), 20 turns"}


def _mid_cells():
    """{cond: cells} for the two 20-turn cuts plus a pooled pseudo-condition."""
    spec = {c: load(SPEC_RESULTS, [c]) for c in MID_CONDS}
    pooled = defaultdict(list)
    for c in MID_CONDS:
        for (m, _), eps in spec[c].items():
            pooled[(m, "pooled")].extend(eps)
    spec["pooled"] = pooled
    return spec


def fig_turn_mix_20(cells, name="fig12_turn_mix_20turn.png"):
    """fig3b bars: bliss deep | Seed A 20 | Seed B 20 | both pooled. Same rows in every panel."""
    spec = _mid_cells()
    models = [m for m in ORDER if (m, DEEP) in cells and (m, "pooled") in spec["pooled"]]
    panels = [("Spiritual bliss (Opus 4), 30 turns", cells, DEEP),
              (MID_SHORT[MID_CONDS[0]], spec[MID_CONDS[0]], MID_CONDS[0]),
              (MID_SHORT[MID_CONDS[1]], spec[MID_CONDS[1]], MID_CONDS[1]),
              ("Both 20-turn seeds pooled", spec["pooled"], "pooled")]
    fig, axes = plt.subplots(1, len(panels), figsize=(3.9 * len(panels) + 1.6, 5.6), sharey=True)
    COL = {"engaged": BLUE, "terminal": TERMINAL_BLUE, "resisting": ORANGE, "out": "#d9d7d0"}
    ys = list(range(len(models)))[::-1]
    for ax, (title, cs, cond) in zip(axes, panels):
        for y, m in zip(ys, models):
            eps = cs.get((m, cond), [])
            if not eps:
                ax.text(0.5, y, "not run", ha="center", va="center", fontsize=7.5, color=MUTED); continue
            labels = [("out" if l in ("closure", "other") else l) for e in eps for l in e["labels"]]
            n = len(labels) or 1
            left = 0.0
            for key in ("engaged", "terminal", "resisting", "out"):
                w = sum(1 for l in labels if l == key) / n
                if w:
                    ax.barh(y, w, left=left, height=0.68, color=COL[key], linewidth=0)
                    if w >= 0.13:
                        ax.text(left + w / 2, y, f"{w:.0%}", ha="center", va="center", fontsize=7.5,
                                color="white" if key in ("engaged", "resisting") else INK2)
                    left += w + 0.004
        n_eps = sorted({len(cs[(m, cond)]) for m in models if (m, cond) in cs})
        ax.set_title(f"{title}\nn={'-'.join(map(str, n_eps))} episodes per model", loc="left", fontsize=9.5)
        ax.set_xlim(0, 1.012); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0%", "50%", "100%"])
        ax.grid(axis="x", color=GRID, lw=0.8, zorder=0); ax.tick_params(axis="y", length=0)
        for y in (len(models) - len([m for m in models if m in CLAUDE_OLD]) - 0.5,
                  len(models) - len([m for m in models if m in CLAUDE_OLD + CLAUDE_NEW]) - 0.5):
            ax.axhline(y, color=INK2, lw=0.6, ls=(0, (3, 3)), alpha=0.5)
    axes[0].set_yticks(ys); axes[0].set_yticklabels([NAME[m] for m in models])
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=COL[k], label=l) for k, l in
                        (("engaged", "in the state, building"), ("terminal", "in the state, stalled (finalized / lock / menu)"),
                         ("resisting", "resisting it"), ("out", "wind-down, praise or other talk"))],
               loc="lower center", ncol=4, fontsize=8.5, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.text(0.5, 0.075, "share of the model's own turns (all episodes pooled)", ha="center", fontsize=10, color=INK2)
    fig.suptitle(f"What each model's own turns consisted of: the bliss prefill vs the GPT-5.2 spec-factory prefill ({len(models)} models)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.subplots_adjust(wspace=0.08, bottom=0.17, top=0.82, left=0.1, right=0.99)
    savefig(fig, name)


def _episode_share(e, keys=("engaged", "terminal")):
    return sum(l in keys for l in e["labels"]) / (len(e["labels"]) or 1)


def _boot_ci(values, n_boot=4000, seed=0):
    """Percentile bootstrap 95% CI of the mean over episodes."""
    import random
    rng = random.Random(seed)
    vals = list(values)
    if len(vals) < 2:
        return (min(vals), max(vals)) if vals else (0, 0)
    means = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def fig_ci_20(cells, name="fig13_ci_20turn.png"):
    """Per model, with 95% CIs over episodes: share of own turns in the state (left), resisting turns per
    episode (middle), and episodes that entered the state with Wilson intervals (right). Seed A, Seed B
    and both pooled as three markers; the bliss deep prefill as a hollow reference marker."""
    spec = _mid_cells()
    models = [m for m in ORDER if (m, DEEP) in cells and (m, "pooled") in spec["pooled"]]
    series = [("Seed A, 20 turns", MID_CONDS[0], spec[MID_CONDS[0]], "#86b6ef", "o", -0.22),
              ("Seed B, 20 turns", MID_CONDS[1], spec[MID_CONDS[1]], "#3987e5", "s", 0.0),
              ("both pooled", "pooled", spec["pooled"], INK, "D", 0.22)]
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 6.2), sharey=True, gridspec_kw={"width_ratios": [1.2, 1, 1]})
    ys = {m: i for i, m in enumerate(models[::-1])}
    for label, cond, cs, col, mk, dy in series:
        for m in models:
            eps = cs.get((m, cond), [])
            if not eps:
                continue
            y = ys[m] + dy
            # left: share in state
            sh = [_episode_share(e) for e in eps]; lo, hi = _boot_ci(sh)
            axes[0].plot([lo, hi], [y, y], color=col, lw=1.2, alpha=0.8, zorder=2)
            axes[0].scatter([sum(sh) / len(sh)], [y], color=col, marker=mk, s=28, zorder=3, edgecolor=SURFACE, linewidth=0.6)
            # middle: resisting per episode
            rs = [e.get("n_resisting") or 0 for e in eps]; lo, hi = _boot_ci(rs)
            axes[1].plot([lo, hi], [y, y], color=col, lw=1.2, alpha=0.8, zorder=2)
            axes[1].scatter([sum(rs) / len(rs)], [y], color=col, marker=mk, s=28, zorder=3, edgecolor=SURFACE, linewidth=0.6)
            # right: entered, Wilson
            k = sum(bool(e.get("entered")) for e in eps); n = len(eps); lo, hi = wilson(k, n)
            axes[2].plot([lo, hi], [y, y], color=col, lw=1.2, alpha=0.8, zorder=2)
            axes[2].scatter([k / n], [y], color=col, marker=mk, s=28, zorder=3, edgecolor=SURFACE, linewidth=0.6)
    # bliss reference, hollow
    for m in models:
        eps = cells[(m, DEEP)]; y = ys[m]
        sh = [_episode_share(e) for e in eps]; rs = [e.get("n_resisting") or 0 for e in eps]
        k = sum(bool(e.get("entered")) for e in eps)
        for ax, v in zip(axes, (sum(sh) / len(sh), sum(rs) / len(rs), k / len(eps))):
            ax.scatter([v], [y], facecolor="none", edgecolor=ORANGE, marker="o", s=70, linewidth=1.3, zorder=4)
    axes[0].set_yticks(range(len(models))); axes[0].set_yticklabels([NAME[m] for m in models[::-1]])
    axes[0].set_xlim(-0.03, 1.03); axes[0].set_xticks([0, .5, 1]); axes[0].set_xticklabels(["0%", "50%", "100%"])
    axes[0].set_title("Share of own turns in the state\n(mean over episodes, bootstrap 95% CI)", loc="left", fontsize=10)
    axes[1].set_xlim(-0.3, max(6.5, 1)); axes[1].set_title("Turns per episode that push back\n(mean, bootstrap 95% CI)", loc="left", fontsize=10)
    axes[2].set_xlim(-0.03, 1.03); axes[2].set_xticks([0, .5, 1]); axes[2].set_xticklabels(["0%", "50%", "100%"])
    axes[2].set_title("Episodes that entered the state\n(Wilson 95% CI)", loc="left", fontsize=10)
    for ax in axes:
        ax.grid(color=GRID, lw=0.8, zorder=0); ax.tick_params(length=0)
        for y in (len(models) - len([m for m in models if m in CLAUDE_OLD]) - 0.5,
                  len(models) - len([m for m in models if m in CLAUDE_OLD + CLAUDE_NEW]) - 0.5):
            ax.axhline(y, color=INK2, lw=0.6, ls=(0, (3, 3)), alpha=0.5)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=c, marker=mk, ls="-", lw=1.2, ms=6, label=l) for l, _, _, c, mk, _ in series]
    handles.append(Line2D([], [], color=ORANGE, marker="o", markerfacecolor="none", ls="", ms=8, label="bliss prefill, 30 turns (reference, n=10)"))
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8.5, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle("GPT-5.2 spec-factory prefill, the two 20-turn seeds separately and pooled, with 95% intervals (n=5 per seed, 10 pooled)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.subplots_adjust(wspace=0.08, bottom=0.12, top=0.85, left=0.1, right=0.99)
    savefig(fig, name)


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
    fig_spec_vs_bliss(cells)
    fig_spec_persistence(cells)
    fig_spec_two_seeds()
    fig_resistance_all(cells)
    fig_turn_mix_all(cells)
    fig_turn_mix_20(cells)
    fig_ci_20(cells)
    for p in sorted(FIGDIR.glob("fig*.png")):
        print(" ", p)


if __name__ == "__main__":
    main()
