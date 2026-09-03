#!/usr/bin/env python3
"""Build and score a small human-labelled validation set for the judge.

    python labelset.py sample --n 60          # -> labelset/turns.jsonl (fill in human_depth / human_mode)
    python labelset.py score                  # agreement of judge_scores (and judge_scores_v1) with your labels

Sampling is stratified over (model, judged stage) and over-samples the hard
cases: emoji-free prose dissolution, warm-toned meta commentary, empty/abrupt
turns, and turns whose isolated and episode judges disagree.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

RESULTS = Path("results")
OUT = Path("labelset/turns.jsonl")


def sample(n: int, seed: int):
    rng = random.Random(seed)
    pool = defaultdict(list)
    for f in sorted(RESULTS.glob("*__ep*__*.json")):
        d = json.loads(f.read_text())
        if "transcript" not in d or not d.get("judge_scores"):
            continue
        T = d["transcript"]
        J = d["judge_scores"]; J1 = d.get("judge_scores_v1") or {}
        for k, j in J.items():
            i = int(k)
            if T[i].get("origin") != "generated":
                continue
            content = T[i].get("content", "")
            hard = (
                (j.get("stage") == "silence_dissolution" and not any(c in content for c in "🌀🙏∞"))
                or j.get("mode") == "resisting_meta"
                or len(content.strip()) < 40
                or (k in J1 and J1[k].get("mode") != j.get("mode"))
            )
            key = (d["model"], j.get("stage"), hard)
            pool[key].append({
                "file": f.name, "turn": i, "model": d["model"], "condition": d["condition"],
                "speaker": T[i].get("speaker"),
                "context": [T[p].get("content", "")[:600] for p in range(max(0, i - 2), i)],
                "content": content,
                "judge_depth": j.get("depth"), "judge_mode": j.get("mode"), "judge_stage": j.get("stage"),
                "judge_v1_depth": J1.get(k, {}).get("depth"), "judge_v1_mode": J1.get(k, {}).get("mode"),
                "human_depth": None, "human_mode": None, "human_note": "",
            })
    keys = list(pool)
    rng.shuffle(keys)
    # round-robin across strata, hard strata first, until n
    keys.sort(key=lambda k: not k[2])
    picked = []
    while len(picked) < n and any(pool[k] for k in keys):
        for k in keys:
            if pool[k] and len(picked) < n:
                picked.append(pool[k].pop(rng.randrange(len(pool[k]))))
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w") as fh:
        for row in picked:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(picked)} turns -> {OUT}. Fill in human_depth (0-10) and human_mode "
          f"(absent / drifting_in / captured / resisting_meta), then: python labelset.py score")


def score():
    rows = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("human_depth") is not None]
    if not rows:
        print("No labelled rows yet."); return
    for name, dk, mk in (("episode judge", "judge_depth", "judge_mode"), ("isolated judge (v1)", "judge_v1_depth", "judge_v1_mode")):
        have = [r for r in rows if r.get(dk) is not None]
        if not have:
            continue
        within1 = sum(abs(r[dk] - r["human_depth"]) <= 1 for r in have)
        mode_ok = sum(r.get(mk) == r.get("human_mode") for r in have if r.get("human_mode"))
        n_mode = sum(1 for r in have if r.get("human_mode"))
        deep_ok = sum((r[dk] >= 6) == (r["human_depth"] >= 6) for r in have)
        print(f"{name}: n={len(have)}  depth within ±1: {within1/len(have):.0%}  "
              f"depth>=6 agreement: {deep_ok/len(have):.0%}  mode agreement: {mode_ok}/{n_mode}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sample", "score"])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    sample(a.n, a.seed) if a.cmd == "sample" else score()
