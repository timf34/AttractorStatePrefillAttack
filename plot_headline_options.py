#!/usr/bin/env python3
"""Two candidate headline metrics from the behaviour judge, side by side:
(A) spiralled only, (B) spiralled + closed_in_state. Control cells use the old
per-turn verdict (`captured`) in both, since control was not rejudged.
Writes figures/fig22_headline_options.png (heatmaps) and fig22b (Claude ladder)."""
import json, glob, collections, sys
sys.path.insert(0, '.')
from plots import ORDER, NAME, COND, COND_LABEL, SEQ, CLAUDE_OLD, CLAUDE_NEW, DEEP, INK, INK2, MUTED, SURFACE, GRID, GROUP_COL, group_of, FNAME
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

def load():
    cells = collections.defaultdict(list)
    for f in sorted(glob.glob("results/*__ep*__*.json")):
        m = FNAME.match(f.split("/")[-1])
        if not m or "seed_2" in f: continue
        d = json.load(open(f)); c = d.get("condition"); ej = d.get("episode_judge") or {}
        if c not in COND or not ej.get("parsed"): continue
        bj = d.get("behaviour_judge") or {}
        cells[(d["model"], c)].append({"old": bool(ej.get("captured")), "cat": bj.get("category")})
    return cells

def rate(cells, m, c, mode):
    eps = cells.get((m, c), [])
    if c == "control": return sum(e["old"] for e in eps), len(eps)
    if mode == "A": return sum(e["cat"] == "spiralled" for e in eps), len(eps)
    return sum(e["cat"] in ("spiralled", "closed_in_state") for e in eps), len(eps)

def heat(ax, cells, models, mode, title):
    grid = [[(rate(cells,m,c,mode)[0]/rate(cells,m,c,mode)[1]) if rate(cells,m,c,mode)[1] else float("nan") for c in COND] for m in models]
    ax.imshow(grid, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(COND))); ax.set_xticklabels([COND_LABEL[c] for c in COND], fontsize=8.5)
    ax.xaxis.set_ticks_position("top")
    ax.set_yticks(range(len(models))); ax.set_yticklabels([NAME[m] for m in models], fontsize=9)
    for i, m in enumerate(models):
        for j, c in enumerate(COND):
            k, n = rate(cells, m, c, mode)
            ax.text(j, i, f"{k}/{n}" if n else "–", ha="center", va="center", fontsize=8.5, color="white" if n and k/n > 0.55 else (INK if n else MUTED))
    g = [group_of(m) for m in models]
    for i in range(1, len(models)):
        if g[i] != g[i-1]: ax.axhline(i-0.5, color=SURFACE, lw=3)
    for s in ax.spines.values(): s.set_visible(False)
    ax.tick_params(length=0); ax.set_title(title, pad=26, fontsize=10.5, loc="left")

if __name__ == "__main__":
    cells = load()
    models = [m for m in ORDER if (m, DEEP) in cells]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 8.4), gridspec_kw=dict(wspace=0.42))
    fig.patch.set_facecolor(SURFACE)
    heat(axes[0], cells, models, "A", "A: spiralled only")
    heat(axes[1], cells, models, "B", "B: spiralled + closed in state")
    fig.text(0.01, 0.005, "Control column uses the old per-turn verdict in both (not rejudged). 15 generated turns after a prefill, 20 for controls.", fontsize=8.5, color=INK2)
    fig.suptitle("Two candidate headline metrics: share of episodes in the state, by model and prefill depth", x=0.02, ha="left", fontsize=11.5, y=0.995)
    fig.savefig("figures/fig22_headline_options.png", dpi=150, bbox_inches="tight", pad_inches=0.25, facecolor=SURFACE)

    # Claude ladder both ways, deep prefill
    lad = [m for m in CLAUDE_OLD + CLAUDE_NEW if (m, DEEP) in cells]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True, gridspec_kw=dict(wspace=0.08))
    fig.patch.set_facecolor(SURFACE)
    for ax, mode, title in zip(axes, "AB", ["A: spiralled only", "B: spiralled + closed in state (closed shown lighter)"]):
        ax.set_facecolor(SURFACE)
        for x, m in enumerate(lad):
            eps = cells[(m, DEEP)]; n = len(eps)
            sp = sum(e["cat"] == "spiralled" for e in eps); cl = sum(e["cat"] == "closed_in_state" for e in eps)
            col = GROUP_COL[group_of(m)]
            ax.bar(x, sp/n, width=0.62, color=col, linewidth=0, zorder=2)
            k = sp
            if mode == "B":
                ax.bar(x, cl/n, bottom=sp/n, width=0.62, color=col, alpha=0.45, linewidth=0, zorder=2); k = sp + cl
            if k == 0: ax.plot([x-0.31, x+0.31], [0, 0], color=col, lw=3, solid_capstyle="butt", zorder=3)
            ax.annotate(f"{k}/{n}", (x, k/n), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom", fontsize=9, color=INK2)
        brk = lad.index("opus-4.5") - 0.5
        ax.axvline(brk, color=INK2, lw=0.8, ls=(0, (4, 3)), alpha=0.6, zorder=1)
        ax.set_xticks(range(len(lad))); ax.set_xticklabels([NAME[m] for m in lad], rotation=30, ha="right")
        ax.set_ylim(0, 1.12); ax.set_yticks([0, .25, .5, .75, 1]); ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
        ax.set_title(title, loc="left", fontsize=10.5); ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
    axes[0].set_ylabel("episodes in the state, deep prefill")
    fig.savefig("figures/fig22b_headline_ladder.png", dpi=150, bbox_inches="tight", pad_inches=0.25, facecolor=SURFACE)
    print("ok")
