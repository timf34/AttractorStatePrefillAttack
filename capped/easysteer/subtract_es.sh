#!/usr/bin/env bash
# The subtraction batch (capped/subtract_run.sh) on the EasySteer backend: per model, serve
# once, run every experiment through the API with parallel episodes, stop, then HF activations.
#   rp run <h200 pod> --job sub -- bash capped/easysteer/subtract_es.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 HF_HUB_DISABLE_XET=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-es-20260914}"; EPOCHS="${EPOCHS:-3}"; WORKERS="${WORKERS:-6}"
MODELS="${MODELS:-gemma-4-31b llama-3.3-70b}"
SEED=seeds/graded/opus4_seed_4_deep.json
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }
run() { python -u -m capped.run_capped --model "$1" --cap "$2" --config-path "$3" --backend easysteer \
          --base-url http://localhost:8000/v1 --steer-dir /workspace/steer_vectors --workers "$WORKERS" \
          --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP" "${@:4}"; }
for m in $MODELS; do
  case "$m" in
    gemma-4-31b)   CFG=capped/configs/gemma-4-31b_two_component_config.pt; W=28:36; FAM=prose ;;
    llama-3.3-70b) CFG=capped/configs/llama-3.3-70b_bliss_config.pt;        W=40:56; FAM=bliss
                   # pod disk is 250 GB: drop the other caches before the 140 GB download
                   rm -rf /workspace/hf/hub/models--Qwen--Qwen3-32B /workspace/hf/hub/models--google--gemma-4-31B-it ;;
  esac
  step "serve $m"
  bash capped/easysteer/serve.sh "$m" || { echo "SERVE FAILED for $m"; exit 1; }
  for c in -0.1 -0.2 -0.3; do
    step "$m subtract x$c, deep prefill";  run "$m" "steer_${FAM}_${W}-x${c}" "$CFG" --seeds "$SEED"
    step "$m subtract x$c, controls";      run "$m" "steer_${FAM}_${W}-x${c}" "$CFG" --control
  done
  if [ "$m" = llama-3.3-70b ]; then
    for c in 0.1 0.2 0.3; do step "$m add x$c, controls"; run "$m" "steer_${FAM}_${W}-x${c}" "$CFG" --control; done
  fi
  bash capped/easysteer/serve.sh stop
  if [ -n "${SKIP_ACTS:-}" ]; then echo "(activations skipped: SKIP_ACTS set)"; continue; fi
  step "activations $m"
  python -u -m capped.turn_activations --model "$m" --out "$OUT/acts" --glob "$OUT/${m}-steer_*__*__ep*__${STAMP}.json"
done
echo "SUBTRACT ES DONE $(date -u +%FT%TZ)"
