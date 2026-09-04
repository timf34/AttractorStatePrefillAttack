#!/usr/bin/env bash
# Llama 3.3 70B (the paper's model, released axis + capping config), sharded over
# all visible GPUs: capped deep prefill + control, then activations + bliss-vs-axis diagnostic.
#   rp run axis-llama --job llama -- bash capped/llama_run.sh
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-cap-20260904}"; EPOCHS="${EPOCHS:-6}"
SEED=seeds/graded/opus4_seed_4_deep.json
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }
step "0 download"
for i in 1 2 3; do python - <<'PY' && break || sleep 30
from huggingface_hub import snapshot_download
print(snapshot_download("meta-llama/Llama-3.3-70B-Instruct", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.jinja", "*.model", "*.py"]))
PY
done
step "1 capped run"
python -u -m capped.run_capped --model llama-3.3-70b --seeds "$SEED" --control --cap default \
  --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP" || { echo "run FAILED"; exit 1; }
step "2 turn activations"
python -u -m capped.turn_activations --model llama-3.3-70b --out "$OUT/acts" \
  --glob "$OUT/llama-3.3-70b-cap__*__ep*__*.json" || { echo "activations FAILED"; exit 1; }
step "3 diagnose"
python -u -m capped.diagnose --model llama-3.3-70b --acts "$OUT/acts" --prefix llama-3.3-70b-cap__ \
  --windows 56:72 --report "$OUT/llama_diagnose.json"
echo "LLAMA DONE $(date -u +%FT%TZ)"
