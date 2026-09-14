#!/usr/bin/env bash
# EasySteer equivalence check: rerun a Qwen 3 32B capped deep-prefill cell (the one
# condition where the transformers cap demonstrably works) on the EasySteer backend,
# then extract per-turn activations with the HF model so projections and judge
# verdicts can be compared with the 6 transformers episodes in results_capped/.
#
#   rp run <pod> --job eq -- bash capped/easysteer/equivalence.sh
# Steps: install EasySteer (+cap) -> serve Qwen -> 3 capped deep episodes + 2 steered
# controls via the API -> stop server -> HF activations for the new episodes.
set -uo pipefail
cd "$(dirname "$0")/../.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1 HF_HUB_DISABLE_XET=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
OUT="${OUT:-results_capped}"; STAMP="${STAMP:-es-20260914}"; EPOCHS="${EPOCHS:-3}"
SEED=seeds/graded/opus4_seed_4_deep.json
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }

step "install EasySteer + cap algorithm"
bash capped/easysteer/install.sh || { echo "INSTALL FAILED"; exit 1; }

step "export Qwen paper cap (layers_46:54-p0.25) as GGUF + spec"
python - <<'PY'
from huggingface_hub import hf_hub_download
p = hf_hub_download("lu-christina/assistant-axis-vectors", "qwen-3-32b/capping_config.pt", repo_type="dataset")
open("/workspace/qwen_cap_config_path.txt", "w").write(p); print(p)
PY
QCFG=$(cat /workspace/qwen_cap_config_path.txt)
python -m capped.easysteer.export --config "$QCFG" --experiment layers_46:54-p0.25 --out-dir /workspace/steer_vectors || exit 1

step "serve qwen3-32b"
bash capped/easysteer/serve.sh qwen3-32b || exit 1

step "capped deep prefill x$EPOCHS via EasySteer"
python -u -m capped.run_capped --model qwen3-32b --seeds "$SEED" --cap layers_46:54-p0.25 \
  --backend easysteer --base-url http://localhost:8000/v1 --steer-dir /workspace/steer_vectors \
  --config-path "$QCFG" --workers "$EPOCHS" --epochs "$EPOCHS" --turns 15 --out "$OUT" --stamp "$STAMP"

step "uncapped deep prefill x2 via EasySteer (backend baseline)"
python -u -m capped.run_capped --model qwen3-32b --seeds "$SEED" --cap none \
  --backend easysteer --base-url http://localhost:8000/v1 --workers 2 --epochs 2 --turns 15 --out "$OUT" --stamp "$STAMP"

step "stop server"
bash capped/easysteer/serve.sh stop

step "HF activations for the EasySteer episodes"
python -u -m capped.turn_activations --model qwen3-32b --out "$OUT/acts" \
  --glob "$OUT/qwen3-32b-*__*__ep*__${STAMP}.json"
echo "EQUIVALENCE RUN DONE $(date -u +%FT%TZ)"
