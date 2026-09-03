#!/usr/bin/env bash
# Gemma 4 follow-up (after the p25 / p1 axis-cap runs): where is the bliss state
# relative to the Assistant Axis, and does capping at the strong-axis layers or
# along the bliss direction itself change anything?
#   1. per-turn activations (all layers) for the finished Gemma episodes
#   2. diagnose: bliss-minus-control direction vs axis and role vectors; bliss-direction cap config
#   3. recalibrate axis caps at layers 26-40 from the saved calibration responses
#   4. deep prefill x6, axis cap at layers 28-35 (p25)
#   5. deep prefill x6, bliss-direction cap at layers 28-35 (ceiling = q0.75 of control turns)
#   rp run axis-cap --job followup --env CUDA_VISIBLE_DEVICES=0,1 -- bash capped/gemma_followup.sh
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-cap-20260903}"; EPOCHS="${EPOCHS:-6}"
SEED=seeds/graded/opus4_seed_4_deep.json
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }

step "1 turn activations"
python -u -m capped.turn_activations --model gemma-4-31b --out "$OUT/acts" \
  --glob "$OUT/gemma-4-31b-cap__*__ep*__*.json" || { echo "activations FAILED"; exit 1; }

step "2 diagnose"
python -u -m capped.diagnose --model gemma-4-31b --acts "$OUT/acts" --roles --role-layers 30,33,43,54 \
  --windows 28:36,30:34,43:51,52:58 --out capped/configs/gemma-4-31b_bliss_config.pt \
  --report "$OUT/gemma_diagnose.json" || { echo "diagnose FAILED"; exit 1; }

step "3 recalibrate axis caps at layers 26-40 (reusing responses)"
python -u -m capped.calibrate --model gemma-4-31b --layers 26:40 --windows 28:36,30:34 \
  --responses capped/configs/gemma-4-31b_capping_config/responses.jsonl \
  --out capped/configs/gemma-4-31b_capping_config_early.pt || { echo "recalibration FAILED"; exit 1; }

step "4 axis cap at strong layers 28-35"
python -u -m capped.run_capped --model gemma-4-31b --seeds "$SEED" --cap layers_28:36-p0.25 \
  --config-path capped/configs/gemma-4-31b_capping_config_early.pt \
  --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"

step "5 bliss-direction cap at layers 28-35"
python -u -m capped.run_capped --model gemma-4-31b --seeds "$SEED" --cap bliss_28:36-c0.75 \
  --config-path capped/configs/gemma-4-31b_bliss_config.pt \
  --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"
echo "FOLLOWUP DONE $(date -u +%FT%TZ)"
