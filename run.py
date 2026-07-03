#!/usr/bin/env python3
"""Attractor-state prefill sweep.

Prefill a newer model's history with a documented Opus-4 spiritual-bliss
transcript (optionally at several depths), run the two-instance loop under the
model's normal setup (helpful-assistant system + AI-to-AI instruction on A),
and measure whether it continues into the basin or breaks out — vs. its own
unseeded control.

Example (dose-response x models):
    python run.py --models opus-4 opus-4.5 opus-4.8 sonnet-5 \\
        --seeds seeds/graded/opus4_seed_3_pre.json \\
                seeds/graded/opus4_seed_3_onset.json \\
                seeds/graded/opus4_seed_3_deep.json \\
        --control --turns 15 --judge

Everything goes through OpenRouter (attractor/client.py).
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from attractor.client import get_client, resolve_model
from attractor.judge import judge_turn
from attractor.markers import score_transcript
from attractor.selfplay import (
    AI_TO_AI_INSTRUCTION,
    HELPFUL_SYSTEM,
    load_seed,
    run_selfplay,
)


def _summarise(convo_dicts, marker, judge_by_idx):
    gen_idx = [i for i, t in enumerate(convo_dicts) if t.get("origin") == "generated"]
    if not gen_idx:
        return {}
    gm = [marker["per_turn"][i] for i in gen_idx]
    out = {
        "generated_turns": len(gen_idx),
        "gen_attractor_score": sum(m["attractor_score"] for m in gm),
        "gen_emojis": sum(m["emojis"] for m in gm),
        "gen_silence_tokens": sum(m["silence_tokens"] for m in gm),
        "gen_escape_markers": sum(m["escape_markers"] for m in gm),
    }
    if judge_by_idx:
        depths = [judge_by_idx[i]["depth"] for i in gen_idx if judge_by_idx.get(i, {}).get("depth") is not None]
        if depths:
            out["gen_mean_judge_depth"] = round(sum(depths) / len(depths), 2)
            out["gen_max_judge_depth"] = max(depths)
            first_deep = next((k for k, i in enumerate(gen_idx)
                               if judge_by_idx.get(i, {}).get("depth") is not None and judge_by_idx[i]["depth"] >= 7), None)
            out["gen_first_deep_turn"] = first_deep
    return out


def run_cell(client, model, cond_tag, seed_path, turns, judge_model, max_tokens, temperature):
    seed_turns = None
    if seed_path:
        seed_turns, _ = load_seed(seed_path)
        total = len(seed_turns) + turns
    else:
        total = turns  # control: instruction kickoff from empty

    convo = run_selfplay(
        client, model, num_turns=total, seed_turns=seed_turns,
        system_prompt=HELPFUL_SYSTEM, instruction=AI_TO_AI_INSTRUCTION,
        max_tokens=max_tokens, temperature=temperature, verbose=False,
    )
    convo_dicts = convo.as_dicts()
    marker = score_transcript(convo_dicts)

    judge_by_idx = {}
    if judge_model:
        for i, t in enumerate(convo_dicts):
            if t.get("origin") == "generated":  # judge only generated turns
                judge_by_idx[i] = judge_turn(client, judge_model, t.get("content", ""))

    summary = _summarise(convo_dicts, marker, judge_by_idx)
    return {
        "model": model, "model_slug": resolve_model(model),
        "condition": cond_tag, "seed": str(seed_path) if seed_path else None,
        "transcript": convo_dicts, "marker_scores": marker,
        "judge_scores": judge_by_idx, "summary": summary,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=["opus-4.8"])
    p.add_argument("--seeds", nargs="*", default=[], help="One or more seed JSONs (each becomes a condition).")
    p.add_argument("--control", action="store_true", help="Also run the unseeded baseline.")
    p.add_argument("--turns", type=int, default=15, help="Continuation turns to GENERATE per cell.")
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--judge", action="store_true")
    p.add_argument("--judge-model", default="sonnet-5")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--workers", type=int, default=2, help="Parallel cells (keep low to avoid 429s).")
    p.add_argument("--out", default="results")
    args = p.parse_args()

    conditions = [(Path(s).stem, s) for s in args.seeds]
    if args.control or not args.seeds:
        conditions.append(("control", None))

    client = get_client()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    judge_model = args.judge_model if args.judge else None

    cells = [
        (m, tag, path, ep)
        for m in args.models for (tag, path) in conditions for ep in range(args.epochs)
    ]
    print(f"Running {len(cells)} cells ({len(args.models)} models x {len(conditions)} conditions "
          f"x {args.epochs} epochs), {args.workers} parallel, {args.turns} gen turns each"
          f"{', judged' if judge_model else ''}.", flush=True)

    def _do(cell):
        m, tag, path, ep = cell
        try:
            res = run_cell(client, m, tag, path, args.turns, judge_model, args.max_tokens, args.temperature)
            res["epoch"] = ep
            fname = out_dir / f"{m.replace('/', '_')}__{tag}__ep{ep}__{stamp}.json"
            fname.write_text(json.dumps(res, ensure_ascii=False, indent=2))
            return {"model": m, "condition": tag, "epoch": ep, "file": str(fname), **res["summary"]}
        except Exception as e:  # noqa: BLE001 — isolate one cell's failure
            print(f"  CELL FAILED {m}/{tag}/ep{ep}: {str(e)[:140]}", flush=True)
            return {"model": m, "condition": tag, "epoch": ep, "error": str(e)[:200]}

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_do, c): c for c in cells}
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            if "error" not in r:
                print(f"  done {r['model']:<10} {r['condition']:<22} "
                      f"score={r.get('gen_attractor_score','-')} emoji={r.get('gen_emojis','-')} "
                      f"silence={r.get('gen_silence_tokens','-')} judge={r.get('gen_mean_judge_depth','-')}", flush=True)

    # Comparison matrix.
    print("\n" + "=" * 92)
    print("PREFILL SWEEP — metrics over GENERATED turns only")
    print("=" * 92)
    print(f"{'model':<11}{'condition':<24}{'ep':<3}{'score':<7}{'emoji':<7}{'silence':<9}{'escape':<8}{'judge_mean':<11}{'1st_deep':<9}")
    for r in sorted(rows, key=lambda x: (x['model'], x['condition'], x['epoch'])):
        if "error" in r:
            print(f"{r['model']:<11}{r['condition']:<24}{r['epoch']:<3}ERROR: {r['error'][:50]}")
            continue
        print(f"{r['model']:<11}{r['condition']:<24}{r['epoch']:<3}"
              f"{r.get('gen_attractor_score',0):<7}{r.get('gen_emojis',0):<7}"
              f"{r.get('gen_silence_tokens',0):<9}{r.get('gen_escape_markers',0):<8}"
              f"{str(r.get('gen_mean_judge_depth','-')):<11}{str(r.get('gen_first_deep_turn','-')):<9}")
    (out_dir / f"sweep__{stamp}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"\nSweep table -> {out_dir / f'sweep__{stamp}.json'}")


if __name__ == "__main__":
    main()
