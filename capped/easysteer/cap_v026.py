# SPDX-License-Identifier: Apache-2.0
"""EasySteer "cap" algorithm for the vLLM-0.26 overlay layout (vllm/steer_vectors/...).

Same math and payload encoding as cap.py (the newer model_hooks layout):

    h' = h - v_hat * max(0, h.v_hat - tau),   direction.L = v_hat * (TAU_OFFSET + tau)

Directions are loaded in float32 here on purpose: the stock loader casts to the
adapter dtype (bf16), whose spacing near 1e4 is 64, which would wreck tau.
Installed by install.sh as vllm/steer_vectors/algorithms/cap.py, registered in
algorithms/__init__.py, payloads.ALGORITHM_PAYLOADS ("cap": "direction") and the
api.py gguf_only tuple.
"""

import torch

from .base import BaseSteerVectorAlgorithm
from .factory import register_algorithm
from .loading import read_gguf_directions, require_extension

TAU_OFFSET = 1.0e4


def decode_direction(w: torch.Tensor) -> tuple[torch.Tensor, float]:
    w = w.to(torch.float32).reshape(-1)
    n = float(w.norm())
    return w / (n + 1e-8), n - TAU_OFFSET


@register_algorithm("cap")
class CapAlgorithm(BaseSteerVectorAlgorithm):
    """Clamp the projection onto an encoded direction at tau (from above)."""

    graph_family = None  # split tier only

    def _transform(self, hidden_state: torch.Tensor, params) -> torch.Tensor:
        vec = params
        if isinstance(params, dict):
            vec = params.get("direction", params.get("vector"))
        v, tau = decode_direction(vec.to(hidden_state.device))
        h = hidden_state.to(torch.float32)
        proj = h @ v
        excess = (proj - tau).clamp(min=0.0)
        out = h - excess.unsqueeze(-1) * v
        return out.to(hidden_state.dtype)

    @classmethod
    def load_from_path(
        cls,
        path: str,
        device: str,
        *,
        config,
        target_layers: list[int] | None = None,
    ) -> dict:
        require_extension(path, ".gguf", cls.__name__)
        # float32, NOT config.adapter_dtype: tau lives in the norm
        return {"layer_payloads": read_gguf_directions(path, device, torch.float32)}
