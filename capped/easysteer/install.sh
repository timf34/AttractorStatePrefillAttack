#!/usr/bin/env bash
# Install EasySteer (ZJU-REAL/EasySteer-vllm-v1 overlay on vllm==0.26.0) into its own venv
# on the pod and add our "cap" algorithm to it. Idempotent; ~5 min on a warm pip cache.
#
#   bash capped/easysteer/install.sh            # -> /workspace/es_venv
#   ES_VENV=/path bash capped/easysteer/install.sh
#
# Based on AttractorBench/assistant_axis_experiments/state_space/es_install.sh (which was
# verified against the HF hook for the additive "direct" algorithm on 2026-08-19).
# Gemma 4 needs transformers >= 5.5.3 and < 5.15 (5.15 broke Gemma4Config.head_dim for vLLM).
set -euo pipefail
ES_VENV="${ES_VENV:-/workspace/es_venv}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd /workspace
[ -x "$ES_VENV/bin/python" ] || python3 -m venv "$ES_VENV"
# shellcheck disable=SC1091
source "$ES_VENV/bin/activate"
pip install -q -U pip
pip install -q "vllm==0.26.0" "transformers>=5.5.3,<5.15" gguf ninja
if [ ! -d /workspace/EasySteer-vllm-v1/.git ]; then
  rm -rf /workspace/EasySteer-vllm-v1
  git clone -q --depth 1 https://github.com/ZJU-REAL/EasySteer-vllm-v1.git
fi
VLLM_DIR=$(python -c "import vllm, os; print(os.path.dirname(vllm.__file__))")
rsync -a /workspace/EasySteer-vllm-v1/vllm/ "$VLLM_DIR"/

# ---- our capping algorithm ----------------------------------------------------------
ALG="$VLLM_DIR/model_hooks/steering/algorithms"
cp "$HERE/cap.py" "$ALG/cap.py"
grep -q "from .cap import CapAlgorithm" "$ALG/__init__.py" || \
  sed -i 's/^from .concept_replace import ConceptReplaceAlgorithm$/from .cap import CapAlgorithm\nfrom .concept_replace import ConceptReplaceAlgorithm/' "$ALG/__init__.py"
CAP="$VLLM_DIR/model_hooks/steering/capabilities.py"
grep -q '"cap": AlgorithmCapabilities' "$CAP" || \
  sed -i 's/^    "direct": AlgorithmCapabilities("direction", "gguf", True),$/    "direct": AlgorithmCapabilities("direction", "gguf", True),\n    "cap": AlgorithmCapabilities("direction", "gguf", False),/' "$CAP"
python - <<'PY'
import vllm, torch
from vllm.model_hooks.steering.algorithms import get_algorithm
from vllm.model_hooks.steering.algorithms.cap import TAU_OFFSET
from vllm.model_hooks.steering.capabilities import ALGORITHM_CAPABILITIES
alg = get_algorithm("cap")(normalize=False)
w = torch.tensor([1.0, 0.0]) * (TAU_OFFSET + 1.0)          # v_hat = e1, tau = 1
h = torch.tensor([[3.0, 0.0], [0.5, 0.0], [-2.0, 1.0]])
out = alg._transform(h, w)
assert torch.allclose(out, torch.tensor([[1.0, 0.0], [0.5, 0.0], [-2.0, 1.0]]), atol=1e-3), out
print("vllm", vllm.__version__, "torch", torch.__version__, "cuda", torch.cuda.is_available(),
      "| cap registered:", "cap" in ALGORITHM_CAPABILITIES, "| clamp math ok")
PY
echo ES_INSTALL_DONE
