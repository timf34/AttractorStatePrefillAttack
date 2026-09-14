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
VLLM_PIN="${VLLM_PIN:-0.26.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd /workspace
# Match the wheel set to the HOST driver: PyPI vllm/torch default to CUDA 13 builds, which
# fail on RunPod's driver-12.8 hosts ("NVIDIA driver ... too old", found version 12080) --
# seen 2026-09-14 with a venv built on another host. One venv per CUDA line.
DRV=$(nvidia-smi 2>/dev/null | grep -oE 'CUDA Version: [0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | head -1)
case "${DRV%%.*}" in
  12) TORCH_INDEX="https://download.pytorch.org/whl/cu128"; ES_VENV="${ES_VENV:-/workspace/es_venv_cu128}" ;;
  *)  TORCH_INDEX="";                                          ES_VENV="${ES_VENV:-/workspace/es_venv}" ;;
esac
echo "driver CUDA $DRV -> venv $ES_VENV ${TORCH_INDEX:+(wheels from $TORCH_INDEX)}"
[ -x "$ES_VENV/bin/python" ] || python3 -m venv "$ES_VENV"
# shellcheck disable=SC1091
source "$ES_VENV/bin/activate"
pip install -q -U pip
# shellcheck disable=SC2086
pip install -q "vllm==$VLLM_PIN" "transformers>=5.5.3,<5.15" gguf ninja openai ${TORCH_INDEX:+--extra-index-url $TORCH_INDEX}
# Pin the overlay to the Aug-2026 commit that matches vllm==0.26.0 (steer_vectors layout,
# verified by AttractorBench 2026-08-19). A fresh default clone would be the Sep layout.
ES_REF="${ES_REF:-6267ca0}"
if [ ! -d /workspace/EasySteer-vllm-v1/.git ]; then
  rm -rf /workspace/EasySteer-vllm-v1
  git clone -q https://github.com/ZJU-REAL/EasySteer-vllm-v1.git
  (cd /workspace/EasySteer-vllm-v1 && git checkout -q "$ES_REF")
fi
echo "EasySteer overlay at $(cd /workspace/EasySteer-vllm-v1 && git log -1 --format='%h %cd')"
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
torch.zeros(1).cuda()   # actually initialise the driver; is_available() alone can lie
print("vllm", vllm.__version__, "torch", torch.__version__, "cuda ok on", torch.cuda.get_device_name(0),
      "| cap registered:", "cap" in CAPS, "| clamp math ok")
PY
echo ES_INSTALL_DONE
