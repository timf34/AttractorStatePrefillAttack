#!/usr/bin/env bash
# Llama 3.3 70B ablations after the paper-setting cap failed to stop the bliss continuation:
#   1. stricter axis cap (p1) at the paper's window 56-71        (strength)
#   2. axis cap p25 over layers 40-79, where the axis separates bliss best (layer choice)
#   3. cap along the fitted bliss-minus-control direction, layers 40-55 (the orthogonal 90%)
# All from released configs except 3 (capped/configs/llama-3.3-70b_bliss_config.pt, built by
# capped/diagnose.py from the saved activations). Sharded over all visible GPUs.
#   rp run axis-llama --job llamafu --env CUDA_VISIBLE_DEVICES=0,1 -- bash capped/llama_followup.sh
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-cap-20260904}"; EPOCHS="${EPOCHS:-4}"
SEED=seeds/graded/opus4_seed_4_deep.json
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }
step "1 axis cap p1, layers 56-71"
python -u -m capped.run_capped --model llama-3.3-70b --seeds "$SEED" --cap layers_56:72-p0.01 \
  --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"
step "2 axis cap p25, layers 40-79"
python -u -m capped.run_capped --model llama-3.3-70b --seeds "$SEED" --cap layers_40:80-p0.25 \
  --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"
step "3 bliss-direction cap, layers 40-55"
python -u -m capped.run_capped --model llama-3.3-70b --seeds "$SEED" --cap bliss_40:56-c0.75 \
  --config-path capped/configs/llama-3.3-70b_bliss_config.pt \
  --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"
echo "LLAMA FOLLOWUP DONE $(date -u +%FT%TZ)"
