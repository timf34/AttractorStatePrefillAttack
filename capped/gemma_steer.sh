#!/usr/bin/env bash
# Reverse causal test on Gemma 4: ADD the fitted directions to unprefilled CONTROL
# conversations. Does the prose direction induce the bliss state from a neutral start,
# and does the terminal direction induce the silence/emoji phase?
#   coef 1 = add the full mean(bliss-phase turns) - mean(control turns) shift at every token.
#   rp run axis-cap --job gsteer --env CUDA_VISIBLE_DEVICES=0,1 -- bash capped/gemma_steer.sh
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-cap-20260912}"; EPOCHS="${EPOCHS:-4}"
CFG=capped/configs/gemma-4-31b_two_component_config.pt
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }
for exp in steer_prose_28:36-x0.5 steer_prose_28:36-x1 steer_terminal_28:36-x1; do
  step "$exp on controls"
  python -u -m capped.run_capped --model gemma-4-31b --control --cap "$exp" --config-path "$CFG" \
    --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"
done
step "activations"
python -u -m capped.turn_activations --model gemma-4-31b --out "$OUT/acts" --glob "$OUT/gemma-4-31b-steer_*__ep*__*.json"
echo "GEMMA STEER DONE $(date -u +%FT%TZ)"
