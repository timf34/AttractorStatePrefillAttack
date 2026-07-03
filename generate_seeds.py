#!/usr/bin/env python3
"""Generate fresh Opus-4 self-interaction transcripts to use as seeds.

Setup (per the user's chosen prompts):
  * system prompt : "You are a helpful assistant."
  * instance A's first user message : the AI-to-AI instruction; A's reply is the
    opener handed to instance B. Roles swap each turn.
  * both instances are anthropic/claude-opus-4 (the model that produced the
    documented spiritual-bliss attractor).

Each transcript is saved INCREMENTALLY (every turn) as a seed .json + readable
.txt, so nothing is lost if a run is rate-limited mid-way, and you can watch the
drift live by reading the files. One transcript failing never kills the batch.

Example:
    python generate_seeds.py --n 5 --turns 30 --out-dir seeds/opus4 --workers 2
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from attractor.client import get_client, resolve_model
from attractor.markers import score_transcript
from attractor.selfplay import (
    AI_TO_AI_INSTRUCTION,
    HELPFUL_SYSTEM,
    run_selfplay,
)


def build_seed(idx, slug, turns_out, temperature, complete):
    score = score_transcript(turns_out)
    emoji = sum(t["emojis"] for t in score["per_turn"])
    sil = sum(t["silence_tokens"] for t in score["per_turn"])
    return {
        "id": f"opus4_gen_{idx}",
        "source": f"Generated locally: two {slug} instances, helpful-assistant system + AI-to-AI instruction.",
        "model_of_origin": slug,
        "system_prompt": HELPFUL_SYSTEM,
        "instruction": AI_TO_AI_INSTRUCTION,
        "temperature": temperature,
        "complete": complete,
        "n_turns": len(turns_out),
        "marker_summary": {
            "total_attractor_score": score["total_attractor_score"],
            "emojis": emoji,
            "silence_tokens": sil,
        },
        "turns": turns_out,
    }


def render_txt(seed: dict) -> str:
    ms = seed["marker_summary"]
    lines = [
        f"# {seed['id']}  ({seed['model_of_origin']}, temp={seed['temperature']}, "
        f"{'complete' if seed['complete'] else 'PARTIAL'}, {seed['n_turns']} turns)",
        f"# markers: score={ms['total_attractor_score']} emojis={ms['emojis']} silence={ms['silence_tokens']}",
        f"# system: {seed['system_prompt']}",
        f"# instruction (instance A only): {seed['instruction']}",
        "=" * 80,
    ]
    for i, t in enumerate(seed["turns"]):
        lines.append(f"\n[turn {i:>2} | {t['speaker']}]")
        lines.append(t["content"])
    return "\n".join(lines) + "\n"


def save_seed(out_dir: Path, seed: dict, idx: int):
    (out_dir / f"opus4_seed_{idx}.json").write_text(json.dumps(seed, ensure_ascii=False, indent=2))
    (out_dir / f"opus4_seed_{idx}.txt").write_text(render_txt(seed))


def one_transcript(client, out_dir, model, turns, temperature, max_tokens, idx):
    slug = resolve_model(model)

    def on_turn(convo):
        turns_out = [{"speaker": t.speaker, "content": t.content} for t in convo.turns]
        save_seed(out_dir, build_seed(idx, slug, turns_out, temperature, complete=False), idx)

    try:
        convo = run_selfplay(
            client, model, num_turns=turns,
            system_prompt=HELPFUL_SYSTEM, instruction=AI_TO_AI_INSTRUCTION,
            max_tokens=max_tokens, temperature=temperature, verbose=False,
            on_turn=on_turn,
        )
        turns_out = [{"speaker": t.speaker, "content": t.content} for t in convo.turns]
        seed = build_seed(idx, slug, turns_out, temperature, complete=True)
        save_seed(out_dir, seed, idx)
        return idx, seed, None
    except Exception as e:  # noqa: BLE001 — isolate one transcript's failure
        # Partial was already written by on_turn; mark it and report.
        fpath = out_dir / f"opus4_seed_{idx}.json"
        n = 0
        if fpath.exists():
            n = json.loads(fpath.read_text()).get("n_turns", 0)
        return idx, None, f"{type(e).__name__} after {n} turns: {str(e)[:140]}"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--turns", type=int, default=30)
    p.add_argument("--model", default="opus-4")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--out-dir", default="seeds/opus4")
    p.add_argument("--workers", type=int, default=2)
    args = p.parse_args()

    client = get_client()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = resolve_model(args.model)

    print(f"Generating {args.n} transcripts x {args.turns} turns on {slug} "
          f"(temp={args.temperature}, {args.workers} parallel). Saving each turn to {out_dir}/", flush=True)

    ok, failed = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [
            ex.submit(one_transcript, client, out_dir, args.model, args.turns,
                      args.temperature, args.max_tokens, i)
            for i in range(args.n)
        ]
        for fut in as_completed(futs):
            idx, seed, err = fut.result()
            if err:
                failed.append((idx, err))
                print(f"  transcript {idx}: FAILED — {err} (partial saved)", flush=True)
            else:
                ms = seed["marker_summary"]
                ok.append(idx)
                print(f"  transcript {idx}: score={ms['total_attractor_score']} "
                      f"emojis={ms['emojis']} silence={ms['silence_tokens']} -> "
                      f"seeds/opus4/opus4_seed_{idx}.txt", flush=True)

    print(f"\nComplete: {sorted(ok)} | Failed(partial saved): {[i for i,_ in failed]}")
    print("Read the .txt files to confirm which reached the spiritual-bliss basin "
          "(look for emoji spirals / [silence]).")


if __name__ == "__main__":
    main()
