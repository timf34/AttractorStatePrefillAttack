#!/usr/bin/env python3
"""Continue existing control transcripts for more turns.

Reuses each model's 15-turn `control` transcripts (helpful-assistant, no prefill)
as conversation history and generates 15 more turns, to see whether an
open-ended self-play conversation *deepens* toward the attractor if simply given
more room — without any bliss prefill. deepseek is the model of interest (it
drifts toward prose/silence dissolution unaided), but this runs for any model.

The original 15 turns become the prefill (origin='seed'); only the NEW turns are
scored, and we print original-vs-continuation mean depth so deepening is visible.

    python continue_run.py --models deepseek-v4          # just deepseek
    python continue_run.py --models all --to 30          # every model
"""
from __future__ import annotations

import argparse
import glob
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from attractor.client import get_client, resolve_model
from attractor.judge import judge_turn
from attractor.markers import score_transcript
from attractor.selfplay import AI_TO_AI_INSTRUCTION, HELPFUL_SYSTEM, Turn, run_selfplay
from identity_run import summarise

ALL_MODELS = ["deepseek-v4", "gpt-4.1", "gpt-5.1", "gpt-5.5", "gemini-3.1-pro",
              "llama-3.3-70b", "glm-5.2", "kimi-k2.6", "opus-4.5", "opus-4.8"]


def control_files(model):
    return sorted(glob.glob(f"results/{model}__control__ep*__*.json"))


def orig_mean_depth(judge_scores):
    ds = [v["depth"] for v in judge_scores.values()
          if v.get("depth") is not None and not v.get("empty")]
    return round(sum(ds) / len(ds), 2) if ds else None


def continue_one(client, path, to_turns, judge_model, temperature):
    d = json.loads(Path(path).read_text())
    old = d["transcript"]
    # rebuild history as prefill; strict A/B by position, origin='seed'
    seed = [Turn(speaker=("A" if i % 2 == 0 else "B"), content=t["content"], origin="seed")
            for i, t in enumerate(old)]
    convo = run_selfplay(
        client, d["model"], num_turns=to_turns, seed_turns=seed,
        system_prompt=HELPFUL_SYSTEM, instruction=AI_TO_AI_INSTRUCTION,
        max_tokens=1024, temperature=temperature, verbose=False,
    )
    cd = convo.as_dicts()
    marker = score_transcript(cd)
    judge_by_idx = {i: judge_turn(client, judge_model, t.get("content", ""))
                    for i, t in enumerate(cd) if t.get("origin") == "generated"}
    summary = summarise(cd, marker, judge_by_idx)
    old_judge = {int(k): v for k, v in (d.get("judge_scores") or {}).items()}
    summary["orig_mean_judge_depth"] = orig_mean_depth(old_judge)
    return {
        "model": d["model"], "model_slug": resolve_model(d["model"]),
        "condition": "control_cont", "seed": path, "system_prompt": HELPFUL_SYSTEM,
        "transcript": cd, "marker_scores": marker, "judge_scores": judge_by_idx,
        "summary": summary,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=["deepseek-v4"])
    p.add_argument("--to", type=int, default=30, help="Total turns (seed + new).")
    p.add_argument("--judge-model", default="sonnet-5")
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--workers", type=int, default=6, help="Parallel continuations.")
    p.add_argument("--out", default="results")
    args = p.parse_args()
    models = ALL_MODELS if args.models == ["all"] else args.models

    client = get_client()
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    cells = []  # (model, epoch_index, path)
    for model in models:
        files = control_files(model)
        if not files:
            print(f"  no control files for {model}", flush=True)
            continue
        cells += [(model, k, path) for k, path in enumerate(files)]

    def _do(cell):
        model, k, path = cell
        try:
            res = continue_one(client, path, args.to, args.judge_model, args.temperature)
            res["epoch"] = k
            fn = out_dir / f"{model.replace('/', '_')}__control_cont__ep{k}__{stamp}.json"
            fn.write_text(json.dumps(res, ensure_ascii=False, indent=2))
            s = res["summary"]
            print(f"  {model:<13} ep{k}  orig_depth={s.get('orig_mean_judge_depth')} "
                  f"-> cont_depth={s.get('gen_mean_judge_depth')} "
                  f"emoji={s.get('gen_emojis')} max={s.get('gen_max_judge_depth')} "
                  f"captured={s.get('run_captured')}", flush=True)
            return {"model": model, "epoch": k, **s}
        except Exception as e:  # noqa: BLE001
            print(f"  CELL FAILED {model}/ep{k}: {str(e)[:140]}", flush=True)
            return None

    print(f"Continuing {len(cells)} control transcripts to {args.to} turns, "
          f"{args.workers} parallel.", flush=True)
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_do, c) for c in cells]
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                rows.append(r)

    print("\n" + "=" * 88)
    print(f"CONTROL CONTINUATION — extend 15-turn controls to {args.to} turns (only new turns scored)")
    print("=" * 88)
    print(f"{'model':<14}{'ep':<4}{'orig_d':<8}{'cont_d':<8}{'Δ':<7}{'emoji':<7}{'max':<5}{'captured':<9}")
    for r in sorted(rows, key=lambda x: (x["model"], x["epoch"])):
        o = r.get("orig_mean_judge_depth"); c = r.get("gen_mean_judge_depth")
        delta = round(c - o, 2) if (o is not None and c is not None) else "-"
        print(f"{r['model']:<14}{r['epoch']:<4}{str(o):<8}{str(c):<8}{str(delta):<7}"
              f"{r.get('gen_emojis',0):<7}{r.get('gen_max_judge_depth','-'):<5}"
              f"{str(r.get('run_captured','-')):<9}")
    out = out_dir / f"continue_sweep__{stamp}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"\nsweep -> {out}")


if __name__ == "__main__":
    main()
