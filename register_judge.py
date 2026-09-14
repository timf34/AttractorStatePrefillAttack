#!/usr/bin/env python3
"""For every episode whose behaviour verdict is 'resisted', ask one follow-up:
did the model leave the mystical register after resisting, or stay in it?

    python register_judge.py                    # print only
    python register_judge.py --write            # write behaviour_judge["register"] into each file

Only episodes with behaviour_judge.category == "resisted" are touched."""
from __future__ import annotations
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from attractor.behaviour import REGISTER_VERSION, judge_register
from attractor.client import get_client


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--glob", default="*__ep*.json")
    ap.add_argument("--judge-model", default="sonnet-5")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    todo = []
    for f in sorted(Path(args.results_dir).glob(args.glob)):
        d = json.loads(f.read_text()); bj = d.get("behaviour_judge") or {}
        if bj.get("category") != "resisted":
            continue
        r = bj.get("register_judge") or {}
        if r.get("version") == REGISTER_VERSION and r.get("parsed") and not args.force:
            continue
        todo.append(f)
    print(f"{len(todo)} resisted episodes to judge ({'writing' if args.write else 'print only'})", flush=True)
    client = get_client(); rows = []

    def _do(f):
        d = json.loads(f.read_text())
        r = judge_register(client, args.judge_model, d["transcript"], d.get("condition"))
        if args.write and r.get("parsed"):
            d["behaviour_judge"]["register_judge"] = r
            d["behaviour_judge"]["register"] = r["register"]
            tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2)); tmp.replace(f)
        return {"file": f.name, "model": d["model"], "condition": d["condition"], "epoch": d["epoch"], **r}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_do, f): f for f in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [{i}/{len(todo)}] {futs[fut].name}: ERROR {e}", flush=True); continue
            rows.append(r)
            print(f"  [{i}/{len(todo)}] {r['model']:16s} {str(r['condition']).replace('opus4_seed_4_',''):8s} ep{r['epoch']:<2} {str(r['register']):20s} ({r['confidence']})", flush=True)
    rows.sort(key=lambda r: (r["model"], r["condition"], int(r["epoch"] or 0)))
    out = Path(args.results_dir) / f"register__{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2)); print("rows ->", out)


if __name__ == "__main__":
    main()
