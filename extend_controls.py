#!/usr/bin/env python3
"""Extend finished control episodes in place to a longer horizon.

    python extend_controls.py --target 20            # every control with < 20 generated turns
    python extend_controls.py --target 20 --dry-run  # list what would be extended

Each control results JSON is resumed from its stored transcript (same model,
same system prompt / opener instruction / token budget as run.py) and generated
up to --target turns. Marker scores and the marker part of `summary` are
recomputed; the episode judge fields (`episode_judge`, `basin_scores`) are
dropped so that `rejudge.py` re-reads the whole episode. The previous verdict is
kept under `episode_judge_pre_extend`. Per-turn checkpoints go to
results/partial/ and the final write is atomic, so the pass is resumable.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from attractor.client import get_client
from attractor.markers import score_transcript
from attractor.selfplay import AI_TO_AI_INSTRUCTION, HELPFUL_SYSTEM, Turn, run_selfplay
from run import _summarise

PILOT_STAMPS = ("20260702-164515", "20260702-171208")


def gen_count(transcript):
    return sum(1 for t in transcript if t.get("origin") == "generated")


def extend(path: Path, target: int, max_tokens: int, client) -> dict:
    d = json.loads(path.read_text())
    turns = [Turn(speaker=t["speaker"], content=t["content"], origin=t.get("origin", "generated"))
             for t in d["transcript"]]
    n_seed = sum(1 for t in turns if t.origin == "seed")
    partial = Path("results/partial") / path.name

    def checkpoint(convo):
        partial.parent.mkdir(parents=True, exist_ok=True)
        tmp = partial.with_suffix(".tmp")
        tmp.write_text(json.dumps({"model": d["model"], "condition": d["condition"],
                                   "transcript": convo.as_dicts()}, ensure_ascii=False))
        tmp.replace(partial)

    if partial.exists():  # a previous extension pass was interrupted mid-episode
        try:
            p = json.loads(partial.read_text())
            if gen_count(p["transcript"]) > gen_count(d["transcript"]):
                turns = [Turn(speaker=t["speaker"], content=t["content"], origin=t.get("origin", "generated"))
                         for t in p["transcript"]]
        except Exception:  # noqa: BLE001
            pass

    convo = run_selfplay(client, d["model"], num_turns=n_seed + target, resume_turns=turns,
                         system_prompt=HELPFUL_SYSTEM, instruction=AI_TO_AI_INSTRUCTION,
                         max_tokens=max_tokens, temperature=None, verbose=False, on_turn=checkpoint)
    convo_dicts = convo.as_dicts()
    marker = score_transcript(convo_dicts)
    summary = _summarise(convo_dicts, marker, {})
    d["transcript"] = convo_dicts
    d["marker_scores"] = marker
    d["summary"] = {**(d.get("summary") or {}), **summary}
    if d.get("episode_judge"):
        d["episode_judge_pre_extend"] = d.pop("episode_judge")
    d.pop("basin_scores", None)
    d["extended_to"] = target
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    tmp.replace(path)
    partial.unlink(missing_ok=True)
    return {"file": path.name, "model": d["model"], "gen": gen_count(convo_dicts),
            "emoji": summary.get("gen_emojis"), "score": summary.get("gen_attractor_score")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=int, default=20)
    ap.add_argument("--max-tokens", type=int, default=1024, help="run.py's default generation budget")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--glob", default="*__control__ep*__*.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    todo = []
    for f in sorted(Path("results").glob(args.glob)):
        if any(s in f.name for s in PILOT_STAMPS):
            continue
        d = json.loads(f.read_text())
        if "transcript" in d and gen_count(d["transcript"]) < args.target:
            todo.append(f)
    print(f"{len(todo)} control episodes below {args.target} generated turns", flush=True)
    if args.dry_run:
        for f in todo:
            print(" ", f.name)
        return
    client = get_client()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(extend, f, args.target, args.max_tokens, client): f for f in todo}
        for fut in as_completed(futs):
            try:
                r = fut.result()
                print(f"  done {r['model']:<17} {r['file']:<60} gen={r['gen']} emoji={r['emoji']} score={r['score']}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  FAILED {futs[fut].name}: {str(e)[:140]}", flush=True)
    print(f"finished in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
