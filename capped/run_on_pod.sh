#!/usr/bin/env bash
# Activation-capping arm of the bliss-prefill experiment, on a RunPod GPU pod.
# One model per GPU (Gemma 4 31B and Qwen 3 32B each need ~65 GB in bf16).
#
#   laptop:  rp up --name axis-cap --gpu h100 --gpus 2 --volume cdv10pb3cq
#            rp bootstrap axis-cap --repo https://github.com/timf34/AttractorStatePrefillAttack \
#                --env .env --req capped/requirements.txt
#            rp run axis-cap --job cap -- bash capped/run_on_pod.sh
#            rp logs axis-cap --job cap -n 40
#            rp scp axis-cap pod:/workspace/AttractorStatePrefillAttack/results_capped ./results_capped -r
#            rp down axis-cap
#
# Per model, in order:
#   1. calibrate caps (Gemma 4: required, no released config; Qwen 3: a check
#      against the paper's config, printed in the log, skipped with QWEN_CALIB_CHECK=0)
#   2. run_capped: {deep prefill, control} x {uncapped, capped} x EPOCHS episodes
# Everything is resumable: finished cells are skipped, interrupted ones resume
# from their per-turn checkpoint. Re-run the same command after a crash.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"

MODELS="${MODELS:-gemma-4-31b qwen3-32b}"
SEED="${SEED:-seeds/graded/opus4_seed_4_deep.json}"
EPOCHS="${EPOCHS:-6}"
TURNS="${TURNS:-15}"
OUT="${OUT:-results_capped}"
STAMP="${STAMP:-cap-$(date +%Y%m%d)}"
CAP="${CAP:-both}"                 # none | both | <experiment id>
PER_ROLE="${PER_ROLE:-6}"          # calibration responses per role (276 roles)
QWEN_CALIB_CHECK="${QWEN_CALIB_CHECK:-1}"
mkdir -p "$OUT"

DRV=$(nvidia-smi 2>/dev/null | grep -oE 'CUDA Version: [0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | head -1)
NGPU=$(nvidia-smi -L 2>/dev/null | wc -l | tr -d ' ')
echo "driver CUDA $DRV, $NGPU GPU(s); models: $MODELS; stamp $STAMP"
[ "${NGPU:-0}" -ge 1 ] || { echo "no GPU"; exit 1; }

run_model() {
  local m="$1" gpu="$2" log="$OUT/pod_${m}.log"
  (
    export CUDA_VISIBLE_DEVICES="$gpu"
    echo "[$m] on GPU $gpu, $(date -u +%FT%TZ)"
    if [ "$m" = gemma-4-31b ]; then
      if [ ! -f capped/configs/gemma-4-31b_capping_config.pt ]; then
        python -u -m capped.calibrate --model gemma-4-31b --layers 40:56 \
          --windows 40:48,42:50,43:51,44:52,46:54 --per-role "$PER_ROLE" || { echo "[$m] calibration FAILED"; exit 1; }
      else
        echo "[$m] calibration exists, skipping"
      fi
    elif [ "$m" = qwen3-32b ] && [ "$QWEN_CALIB_CHECK" = 1 ] && [ ! -f capped/configs/qwen3-32b_capping_config_ours.pt ]; then
      python -u -m capped.calibrate --model qwen3-32b --layers 44:56 --windows 46:54 \
        --per-role "$PER_ROLE" --compare || echo "[$m] calibration check failed (non-fatal; the paper's config is used)"
    fi
    python -u -m capped.run_capped --model "$m" --seeds "$SEED" --control --cap "$CAP" \
      --epochs "$EPOCHS" --turns "$TURNS" --out "$OUT" --stamp "$STAMP"
    echo "[$m] EXIT=$? $(date -u +%FT%TZ)"
  ) > "$log" 2>&1
}

i=0
for m in $MODELS; do
  run_model "$m" $((i % NGPU)) &
  i=$((i + 1))
  # single GPU: models must run one after another
  [ "$NGPU" -eq 1 ] && wait
done
wait
echo "ALL MODELS DONE $(date -u +%FT%TZ)"
tail -n 3 "$OUT"/pod_*.log
