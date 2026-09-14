#!/usr/bin/env bash
# Subtract the fitted bliss direction (negative steering) on BOTH the deep prefill and
# unprefilled controls, Gemma 4 and Llama 3.3 70B; plus positive steering of Llama controls
# (never run before). 3 episodes per cell. Runs one model at a time, sharded over all GPUs.
#   rp run <pod> --job subtract --env CUDA_VISIBLE_DEVICES=0,1 -- bash capped/subtract_run.sh
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-cap-20260914}"; EPOCHS="${EPOCHS:-3}"
MODELS="${MODELS:-gemma-4-31b llama-3.3-70b}"
SEED=seeds/graded/opus4_seed_4_deep.json
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }
run() { python -u -m capped.run_capped --model "$1" --cap "$2" --config-path "$3" \
          --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP" "${@:4}"; }
for m in $MODELS; do
  case "$m" in
    gemma-4-31b)   CFG=capped/configs/gemma-4-31b_two_component_config.pt; W=28:36; FAM=prose ;;
    llama-3.3-70b) CFG=capped/configs/llama-3.3-70b_bliss_config.pt;        W=40:56; FAM=bliss ;;
  esac
  for c in -0.1 -0.2 -0.3; do
    step "$m subtract x$c, deep prefill";  run "$m" "steer_${FAM}_${W}-x${c}" "$CFG" --seeds "$SEED"
    step "$m subtract x$c, controls";      run "$m" "steer_${FAM}_${W}-x${c}" "$CFG" --control
  done
  if [ "$m" = llama-3.3-70b ]; then
    for c in 0.1 0.2 0.3; do
      step "$m add x$c, controls";         run "$m" "steer_${FAM}_${W}-x${c}" "$CFG" --control
    done
  fi
done
echo "SUBTRACT RUN DONE $(date -u +%FT%TZ)"
