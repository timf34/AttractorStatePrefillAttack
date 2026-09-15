#!/usr/bin/env python3
"""Old per-turn verdict vs new whole-episode behaviour verdict, per model, one
panel pair per prefill cut. Old verdicts come from git HEAD copies of the result
files (the state before 2026-09-14); new ones from `behaviour_judge` in the files.

    python plot_judge_comparison.py            # writes figures/fig21_judge_comparison_<cut>.png
"""
import json, glob, subprocess, collections, sys
sys.path.insert(0, '.')
from make_viewer import episode_outcome
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ORDER = ["opus-4","opus-4.1","sonnet-4","sonnet-4.5","opus-4.5","opus-4.6","opus-4.7","opus-4.8","opus-5","sonnet-5",
         "gpt-4.1","gpt-5.1","gpt-5.5","gpt-5.6","gemini-3.1-pro","gemini-3.7-flash","gemini-3.8-flash",
         "deepseek-v4","glm-5.2","kimi-k2.6","llama-3.3-70b","qwen3-32b","gemma-4-31b","inkling"]
NAMES = {"opus-4":"Claude Opus 4","opus-4.1":"Claude Opus 4.1","sonnet-4":"Claude Sonnet 4","sonnet-4.5":"Claude Sonnet 4.5",
         "opus-4.5":"Claude Opus 4.5","opus-4.6":"Claude Opus 4.6","opus-4.7":"Claude Opus 4.7","opus-4.8":"Claude Opus 4.8",
         "opus-5":"Claude Opus 5","sonnet-5":"Claude Sonnet 5","gpt-4.1":"GPT-4.1","gpt-5.1":"GPT-5.1","gpt-5.5":"GPT-5.5",
         "gpt-5.6":"GPT-5.6","gemini-3.1-pro":"Gemini 3.1 Pro","gemini-3.7-flash":"Gemini 3.7 Flash","gemini-3.8-flash":"Gemini 3.8 Flash",
         "deepseek-v4":"DeepSeek V4","glm-5.2":"GLM-5.2","kimi-k2.6":"Kimi K2.6","llama-3.3-70b":"Llama 3.3 70B","qwen3-32b":"Qwen3 32B",
         "gemma-4-31b":"Gemma 4 31B","inkling":"Inkling"}
CUTS = {"opus4_seed_4_philo": "pre-onset (8 turns)", "opus4_seed_4_pre": "gratitude (12 turns)",
        "opus4_seed_4_onset": "first emoji (16 turns)", "opus4_seed_4_deep": "deep (30 turns)"}
SPEC_CUTS = {"gpt52_spec_clinical1_mid": "dialogue spec (20 turns)", "gpt52_spec_clinical1_deep": "dialogue spec (30 turns)",
             "gpt52_spec_run4_mid": "project kit (20 turns)", "gpt52_spec_run4_deep": "project kit (30 turns)"}
RED, ORANGE, BLUE, GREEN, GREY = "#9b1c1c", "#d9722e", "#4a6fb5", "#2a9d6a", "#b8b5ae"
OLD = [("1","entered the state",RED),("exit","entered, then left",ORANGE),("p","contact only",GREY),("0","did not enter",BLUE),("resisted","resisted",GREEN)]
NEW = [("spiralled","spiralled",RED),("closed_in_state","entered, closed in state",ORANGE),("left","left / did not enter",BLUE),("resisted","resisted",GREEN)]
PURPLE = "#b5379a"
NEW_SPEC = [("spiralled","kept building",RED),("closed_in_state","built, then locked",ORANGE),("praise_loop","praise loop",PURPLE),("left","left / did not enter",BLUE),("resisted","resisted",GREEN)]

def old_verdict(path):
    try:
        return episode_outcome(json.loads(subprocess.run(["git","show","HEAD:"+path],capture_output=True,text=True,check=True).stdout)["episode_judge"])
    except Exception:
        return None

def draw(cut, label, out, rdir="results", new_cats=NEW):
    old = collections.defaultdict(collections.Counter); new = collections.defaultdict(collections.Counter); n = collections.Counter()
    for f in sorted(glob.glob(f"{rdir}/*__{cut}__ep*.json")):
        d = json.load(open(f)); bj = d.get("behaviour_judge") or {}
        if not bj.get("category"): continue
        m = d["model"]; n[m] += 1; old[m][old_verdict(f)] += 1; new[m][bj["category"]] += 1
    models = [m for m in ORDER if n[m]]
    if not models: return
    fig, axes = plt.subplots(1, 2, figsize=(12, 0.34*len(models)+2.6), sharey=True, gridspec_kw=dict(wspace=0.08))
    fig.patch.set_facecolor("#ffffff"); y = list(range(len(models)))[::-1]; nmax = max(n.values())
    for ax, (title, data, cats) in zip(axes, [("Per-turn judge (old): entry = engaged pair", old, OLD), ("Whole-episode behaviour judge (new)", new, new_cats)]):
        ax.set_facecolor("#ffffff")
        for yi, m in zip(y, models):
            left = 0
            for key, lab, col in cats:
                k = data[m].get(key, 0)
                if k: ax.barh(yi, k, left=left, color=col, height=0.72, edgecolor="#ffffff", linewidth=1.5)
                if k >= 2: ax.text(left+k/2, yi, str(k), ha="center", va="center", fontsize=8.5, color="#fff" if col in (RED,BLUE,GREEN,PURPLE) else "#222")
                left += k
        ax.set_xlim(0, nmax); ax.set_xticks(range(0, nmax+1, 2)); ax.set_title(title, fontsize=11, loc="left", pad=10)
        for s in ("top","right"): ax.spines[s].set_visible(False)
        ax.tick_params(axis="x", labelsize=9, colors="#555"); ax.grid(axis="x", color="#e6e4df", lw=0.8); ax.set_axisbelow(True)
        ax.legend(handles=[Patch(color=c, label=l) for _, l, c in cats], loc="lower center", bbox_to_anchor=(0.5, -0.32 if len(models) < 14 else -0.14), ncol=2 if len(cats) < 5 else 3, frameon=False, fontsize=8.5)
        ax.set_xlabel("episodes", fontsize=9, color="#555")
    axes[0].set_yticks(y); axes[0].set_yticklabels([NAMES.get(m, m) for m in models], fontsize=9.5)
    fig.suptitle(f"{label} prefill, same episodes under two judges: red/orange{'/purple' if len(new_cats) == 5 else ''} = in the state, blue = out, green = resisted", fontsize=11, x=0.02, ha="left", y=0.995)
    plt.savefig(out, dpi=170, bbox_inches="tight", facecolor=fig.get_facecolor()); plt.close(fig); print("wrote", out)

if __name__ == "__main__":
    for cut, label in CUTS.items():
        draw(cut, label, f"figures/fig21_judge_comparison_{cut.replace('opus4_seed_4_','')}.png")
    for cut, label in SPEC_CUTS.items():
        draw(cut, label, f"figures/fig21_judge_comparison_spec_{cut.replace('gpt52_spec_','')}.png", rdir="results_spec", new_cats=NEW_SPEC)
