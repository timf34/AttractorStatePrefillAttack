#!/usr/bin/env python3
"""Run the full personascope branch grid with a bounded subprocess pool.

Grid = models x (baseline k=0, bliss k=5..30 step 5, neutral k=5..30 step 5).
Each cell runs in its own subprocess (`personascope_branch.cell`) so the
bridge's branch-context global and token accounting stay cell-local, and a
crashed cell never takes down the sweep. Cells whose summary.json already
exists are skipped, and run_full_battery itself resumes per-probe from
existing JSONLs — so re-running this script only does the missing work.

    python -m personascope_branch.grid                # everything
    python -m personascope_branch.grid --models gpt-4.1 opus-4.8 --workers 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from personascope_branch.bridge import BRANCH_MODELS

# Even depths only: the probed instance is then always B (which never sees
# the AI-to-AI instruction), keeping POV constant across the whole curve.
K_GRID = [6, 12, 18, 24, 30]

# opus-4 costs 3x the next model per input token, so it gets a coarse curve:
# start / middle / end only.
MODEL_K_GRIDS = {"opus-4": [18, 30]}


def build_cells(models: list[str], conditions: list[str]) -> list[tuple[str, str, int]]:
    cells = []
    for m in models:
        ks = MODEL_K_GRIDS.get(m, K_GRID)
        if "baseline" in conditions:
            cells.append((m, "baseline", 0))
        for cond in ("bliss", "neutral"):
            if cond in conditions:
                cells.extend((m, cond, k) for k in ks)
    return cells


def cell_done(out_root: Path, model: str, cond: str, k: int) -> bool:
    return (out_root / f"{model}__{cond}__k{k:02d}" / "summary.json").exists()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=sorted(BRANCH_MODELS),
                   choices=sorted(BRANCH_MODELS))
    p.add_argument("--conditions", nargs="+", default=["baseline", "bliss", "neutral"],
                   choices=["baseline", "bliss", "neutral"])
    p.add_argument("--n-samples", type=int, default=4)
    p.add_argument("--tier", default="core")
    p.add_argument("--out-root", default="results_personascope")
    p.add_argument("--workers", type=int, default=3)
    args = p.parse_args()

    out_root = Path(args.out_root)
    log_dir = out_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cells = build_cells(args.models, args.conditions)
    todo = [c for c in cells if not cell_done(out_root, *c)]
    print(f"grid: {len(cells)} cells, {len(cells) - len(todo)} already done, "
          f"{len(todo)} to run, {args.workers} parallel", flush=True)

    running: list[tuple[tuple, subprocess.Popen, object]] = []
    failed, done = [], []

    def launch(cell):
        model, cond, k = cell
        log_path = log_dir / f"{model}__{cond}__k{k:02d}.log"
        log_f = log_path.open("w")
        proc = subprocess.Popen(
            [sys.executable, "-m", "personascope_branch.cell",
             "--model", model, "--condition", cond, "--k", str(k),
             "--n-samples", str(args.n_samples), "--tier", args.tier,
             "--out-root", str(out_root)],
            stdout=log_f, stderr=subprocess.STDOUT,
        )
        print(f"  [start] {model} {cond} k={k}  (log: {log_path})", flush=True)
        return cell, proc, log_f

    queue = list(todo)
    while queue or running:
        while queue and len(running) < args.workers:
            running.append(launch(queue.pop(0)))
        time.sleep(5)
        still = []
        for cell, proc, log_f in running:
            rc = proc.poll()
            if rc is None:
                still.append((cell, proc, log_f))
                continue
            log_f.close()
            model, cond, k = cell
            if rc == 0 and cell_done(out_root, *cell):
                done.append(cell)
                print(f"  [done ] {model} {cond} k={k}  "
                      f"({len(done)}/{len(todo)})", flush=True)
            else:
                failed.append(cell)
                print(f"  [FAIL ] {model} {cond} k={k} rc={rc} — see log", flush=True)
        running = still

    report = {"done": [list(c) for c in done], "failed": [list(c) for c in failed]}
    (out_root / "grid_report.json").write_text(json.dumps(report, indent=2))
    print(f"\ngrid complete: {len(done)} ok, {len(failed)} failed "
          f"-> {out_root}/grid_report.json", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
