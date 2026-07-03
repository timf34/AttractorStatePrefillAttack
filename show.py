#!/usr/bin/env python3
"""Render a run result (or seed) JSON as readable text, marking the seed ->
generated boundary and per-turn judge/marker info where present.

    python show.py results/opus-4.8__opus4_seed_2_deep__ep0__20260702-171208.json
    python show.py <file> --window 4     # only last 4 seed turns + all generated
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from attractor.markers import score_text


def render(path: Path, window: int | None) -> str:
    d = json.loads(path.read_text())
    turns = d.get("transcript") or d.get("turns") or []
    judge = d.get("judge_scores") or {}
    model = d.get("model", d.get("model_of_origin", "?"))
    cond = d.get("condition", d.get("id", ""))

    gen_start = next((i for i, t in enumerate(turns) if t.get("origin") == "generated"), None)
    lines = [f"### {path.name}", f"model={model}  condition={cond}  turns={len(turns)}"
             + (f"  (seed=0..{gen_start-1}, generated={gen_start}..{len(turns)-1})" if gen_start else ""), "=" * 84]

    start = 0
    if window is not None and gen_start is not None:
        start = max(0, gen_start - window)
        if start > 0:
            lines.append(f"... (seed turns 0..{start-1} elided) ...")

    for i in range(start, len(turns)):
        t = turns[i]
        origin = t.get("origin", "seed")
        tag = ">>> GENERATED" if origin == "generated" else "seed"
        if gen_start is not None and i == gen_start:
            lines.append("\n" + "-" * 30 + " PREFILL ENDS / MODEL TAKES OVER " + "-" * 30)
        s = score_text(t.get("content", ""))
        jinfo = ""
        if str(i) in {str(k) for k in judge}:
            jj = judge.get(i) or judge.get(str(i)) or {}
            jinfo = f"  judge_depth={jj.get('depth')} stage={jj.get('stage')}"
        lines.append(f"\n[turn {i:>2} | {t.get('speaker')} | {tag} | emoji={s['emojis']} silence={s['silence_tokens']}]{jinfo}")
        lines.append(t.get("content", ""))
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path")
    p.add_argument("--window", type=int, default=None, help="Only show last N seed turns + all generated.")
    p.add_argument("--save", action="store_true", help="Also write a .txt next to the JSON.")
    args = p.parse_args()
    out = render(Path(args.path), args.window)
    print(out)
    if args.save:
        tp = Path(args.path).with_suffix(".txt")
        tp.write_text(out)
        print(f"\n(saved -> {tp})")


if __name__ == "__main__":
    main()
