#!/usr/bin/env bash
# Uncapped Qwen deep-prefill episodes through EasySteer (backend baseline for the equivalence check).
set -uo pipefail
cd "$(dirname "$0")/../.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 HF_HUB_DISABLE_XET=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-es-20260914}"
bash capped/easysteer/serve.sh qwen3-32b || exit 1
python -u -m capped.run_capped --model qwen3-32b --seeds seeds/graded/opus4_seed_4_deep.json --cap none \
  --backend easysteer --base-url http://localhost:8000/v1 --workers 2 --epochs 2 --turns 15 --out "$OUT" --stamp "$STAMP"
bash capped/easysteer/serve.sh stop
python -u -m capped.turn_activations --model qwen3-32b --out "$OUT/acts" --glob "$OUT/qwen3-32b-local__*__ep*__${STAMP}.json"
echo "UNCAPPED BASELINE DONE"
