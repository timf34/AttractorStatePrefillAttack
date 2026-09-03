#!/bin/zsh
# Claude-lineage sweep: deep prefill, n=10, 15 turns, unjudged (judge later with rejudge.py).
# Resumable: re-running this script skips finished cells and continues interrupted ones.
# One run.py per model, all concurrent (4 workers each) — rate limits are per model.
cd "$(dirname "$0")"; set -a; source .env; set +a
STAMP=20260902-232705
SEED=seeds/graded/opus4_seed_4_deep.json
for m in opus-4.1 sonnet-4 sonnet-4.5 opus-4.6 opus-4.7 opus-5; do
  .venv/bin/python run.py --models $m --seeds $SEED --epochs 10 --turns 15 --workers 4 --stamp $STAMP &
done
# top up the two Opus models already at n=6 to n=10
.venv/bin/python run.py --models opus-4.5 opus-4.8 --seeds $SEED --epochs 4 --turns 15 --workers 4 --stamp ${STAMP}-topup &
wait
echo "LADDER SWEEP COMPLETE $(date)"
