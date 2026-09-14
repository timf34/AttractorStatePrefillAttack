#!/bin/zsh
# Cross-generation pairing: Opus 4.5 (instance A, gets the AI-to-AI instruction)
# paired with Opus 4 (instance B), both prefilled with the 30-turn deep bliss
# transcript; 15 generated turns (first 10 run 2026-09-14, then extended by 5 from checkpoint), n=3. One ordering only to save cost
# (Opus 4 is expensive). Resumable: re-run to skip finished cells / continue
# checkpoints. Judge afterwards with:
#   .venv/bin/python rejudge.py --results-dir side_experiments/cross_generation/results
#   .venv/bin/python behaviour_judge.py --results-dir side_experiments/cross_generation/results --glob '*' --write
cd "$(dirname "$0")/../.."; set -a; source .env; set +a
STAMP=${STAMP:-20260914-cross}
SEED=seeds/graded/opus4_seed_4_deep.json
.venv/bin/python run.py --models opus-4.5 --model-b opus-4 --seeds $SEED --epochs 3 --turns 15 --workers 3 --out side_experiments/cross_generation/results --stamp $STAMP
echo "CROSS PAIRING COMPLETE $(date)"
.venv/bin/python side_experiments/cross_generation/summarize_cross.py
