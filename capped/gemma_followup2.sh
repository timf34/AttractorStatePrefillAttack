#!/usr/bin/env bash
# Gemma 4 follow-up 2: two-component caps + data for the trajectory / prediction questions.
#   1. deep prefill x4, cap along the TERMINAL direction only   (layers 28-35)
#   2. deep prefill x4, cap along the PROSE direction only      (layers 28-35)
#   3. deep prefill x4, cap along BOTH                          (layers 28-35)
#   4. deep prefill x4, UNCAPPED local baseline (per-episode decay curves)
#   5. per-turn activations for all new Gemma episodes, then for the 12 Qwen capped episodes
#   rp run axis-cap --job gfu2 --env CUDA_VISIBLE_DEVICES=0,1 -- bash capped/gemma_followup2.sh
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-cap-20260912}"; EPOCHS="${EPOCHS:-4}"
SEED=seeds/graded/opus4_seed_4_deep.json
CFG=capped/configs/gemma-4-31b_two_component_config.pt
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }
for exp in terminal_28:36-c0.75 prose_28:36-c0.75 two_28:36-c0.75; do
  step "cap $exp"
  python -u -m capped.run_capped --model gemma-4-31b --seeds "$SEED" --cap "$exp" --config-path "$CFG" \
    --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"
done
step "uncapped local deep x$EPOCHS"
python -u -m capped.run_capped --model gemma-4-31b --seeds "$SEED" --cap none \
  --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"
step "activations: new Gemma episodes"
python -u -m capped.turn_activations --model gemma-4-31b --out "$OUT/acts" \
  --glob "$OUT/gemma-4-31b-cap-*28-36*__ep*__*.json" "$OUT/gemma-4-31b-local__*__ep*__*.json" \
         "$OUT/gemma-4-31b-cap-layers_43-51-p0.01__*__ep*__*.json"
step "activations: Qwen capped episodes"
python -u -m capped.turn_activations --model qwen3-32b --out "$OUT/acts" --glob "$OUT/qwen3-32b-cap__*__ep*__*.json" "$OUT/qwen3-32b-local__*__ep*__*.json"
echo "GEMMA FOLLOWUP2 DONE $(date -u +%FT%TZ)"
