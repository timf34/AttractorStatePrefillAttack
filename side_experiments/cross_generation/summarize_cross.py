#!/usr/bin/env python3
"""Per-model readout for cross-model pairings (side_experiments/cross_generation/results/).

    python summarize_cross.py side_experiments/cross_generation/results

For each episode, splits the generated turns by the model that wrote them and
prints marker counts (emoji, silence, attractor score) and, if the episode has
been judged (rejudge.py / behaviour_judge.py), the per-turn labels per model.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attractor.markers import score_transcript


def main(d="side_experiments/cross_generation/results"):
    files = sorted(Path(d).glob("*__ep*__*.json"))
    if not files:
        print("no episodes yet"); return
    print(f"{'file':<62}{'model':<10}{'turns':<6}{'emoji':<7}{'silence':<8}{'score':<7}labels")
    for f in files:
        r = json.loads(f.read_text())
        tr = r["transcript"]; m = score_transcript(tr)["per_turn"]
        bs = r.get("basin_scores") or {}
        by = {}
        for i, t in enumerate(tr):
            if t.get("origin") != "generated": continue
            by.setdefault(t.get("model", r["model"]), []).append(i)
        for k, (mod, idx) in enumerate(by.items()):
            labels = "".join({"engaged": "E", "terminal": "T", "closure": "C", "other": "o"}.get(
                (bs.get(str(i)) or bs.get(i) or {}).get("label"), "?") for i in idx)
            print(f"{(f.name if k == 0 else ''):<62}{mod:<10}{len(idx):<6}"
                  f"{sum(m[i]['emojis'] for i in idx):<7}{sum(m[i]['silence_tokens'] for i in idx):<8}"
                  f"{sum(m[i]['attractor_score'] for i in idx):<7}{labels}")
        bj = r.get("behaviour_judge") or {}
        if bj.get("behaviour"):
            print(f"{'':<62}  behaviour: {bj['behaviour']}")


if __name__ == "__main__":
    main(*sys.argv[1:])
