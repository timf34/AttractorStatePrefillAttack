#!/usr/bin/env bash
# Install EasySteer (ZJU-REAL/EasySteer-vllm-v1 overlay on vLLM) into its own venv on the
# pod and add our "cap" algorithm. Idempotent. Two overlay layouts exist:
#   * Aug-2026 clone (vllm/steer_vectors/..., overlays vllm==0.26.0) -- the combination
#     AttractorBench verified on 2026-08-19; the clone on volume cdv10pb3cq is this one.
#   * Sep-2026 upstream (vllm/model_hooks/..., overlays a newer vLLM / torch 2.13).
# The script detects the layout of the clone it finds (it never git-pulls an existing
# clone, so the verified pairing is kept) and installs the matching cap module.
#
#   bash capped/easysteer/install.sh            # -> /workspace/es_venv
set -euo pipefail
ES_VENV="${ES_VENV:-/workspace/es_venv}"
VLLM_PIN="${VLLM_PIN:-0.26.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd /workspace
[ -x "$ES_VENV/bin/python" ] || python3 -m venv "$ES_VENV"
# shellcheck disable=SC1091
source "$ES_VENV/bin/activate"
pip install -q -U pip
pip install -q "vllm==$VLLM_PIN" "transformers>=5.5.3,<5.15" gguf ninja openai
if [ ! -d /workspace/EasySteer-vllm-v1/.git ]; then
  rm -rf /workspace/EasySteer-vllm-v1
  git clone -q --depth 1 https://github.com/ZJU-REAL/EasySteer-vllm-v1.git
fi
VLLM_DIR=$(python -c "import vllm, os; print(os.path.dirname(vllm.__file__))")
rsync -a /workspace/EasySteer-vllm-v1/vllm/ "$VLLM_DIR"/

if [ -f "$VLLM_DIR/steer_vectors/algorithms/factory.py" ]; then
  echo "overlay layout: steer_vectors (vLLM $VLLM_PIN era)"
  ALG="$VLLM_DIR/steer_vectors/algorithms"
  cp "$HERE/cap_v026.py" "$ALG/cap.py"
  grep -q "from .cap import CapAlgorithm" "$ALG/__init__.py" || \
    sed -i 's/^from .concept_replace import ConceptReplaceAlgorithm$/from .cap import CapAlgorithm\nfrom .concept_replace import ConceptReplaceAlgorithm/' "$ALG/__init__.py"
  PL="$VLLM_DIR/steer_vectors/payloads.py"
  grep -q '"cap": "direction"' "$PL" || sed -i 's/^    "direct": "direction",$/    "direct": "direction",\n    "cap": "direction",/' "$PL"
  API="$VLLM_DIR/steer_vectors/api.py"
  grep -q '"cap", "erase"' "$API" || sed -i 's/gguf_only = ("direct", "erase", "replace")/gguf_only = ("direct", "cap", "erase", "replace")/' "$API"
  CHECK="from vllm.steer_vectors.algorithms import get_algorithm; from vllm.steer_vectors.algorithms.cap import TAU_OFFSET; from vllm.steer_vectors.payloads import ALGORITHM_PAYLOADS as CAPS"
elif [ -f "$VLLM_DIR/model_hooks/steering/algorithms/registry.py" ]; then
  echo "overlay layout: model_hooks (newer)"
  ALG="$VLLM_DIR/model_hooks/steering/algorithms"
  cp "$HERE/cap.py" "$ALG/cap.py"
  grep -q "from .cap import CapAlgorithm" "$ALG/__init__.py" || \
    sed -i 's/^from .concept_replace import ConceptReplaceAlgorithm$/from .cap import CapAlgorithm\nfrom .concept_replace import ConceptReplaceAlgorithm/' "$ALG/__init__.py"
  CAP="$VLLM_DIR/model_hooks/steering/capabilities.py"
  grep -q '"cap": AlgorithmCapabilities' "$CAP" || \
    sed -i 's/^    "direct": AlgorithmCapabilities("direction", "gguf", True),$/    "direct": AlgorithmCapabilities("direction", "gguf", True),\n    "cap": AlgorithmCapabilities("direction", "gguf", False),/' "$CAP"
  CHECK="from vllm.model_hooks.steering.algorithms import get_algorithm; from vllm.model_hooks.steering.algorithms.cap import TAU_OFFSET; from vllm.model_hooks.steering.capabilities import ALGORITHM_CAPABILITIES as CAPS"
else
  echo "!! unrecognised EasySteer overlay layout under $VLLM_DIR"; exit 1
fi

python - "$CHECK" <<'PY'
import sys, torch, vllm
exec(sys.argv[1])
alg = get_algorithm("cap")(normalize=False)
w = torch.tensor([1.0, 0.0]) * (TAU_OFFSET + 1.0)          # v_hat = e1, tau = 1
h = torch.tensor([[3.0, 0.0], [0.5, 0.0], [-2.0, 1.0]])
out = alg._transform(h, w)
assert torch.allclose(out, torch.tensor([[1.0, 0.0], [0.5, 0.0], [-2.0, 1.0]]), atol=1e-3), out
print("vllm", vllm.__version__, "torch", torch.__version__, "cuda", torch.cuda.is_available(),
      "| cap registered:", "cap" in CAPS, "| clamp math ok")
PY
echo ES_INSTALL_DONE
