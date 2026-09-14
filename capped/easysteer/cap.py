# SPDX-License-Identifier: Apache-2.0
"""EasySteer steering algorithm: activation CAPPING along a direction.

    h' = h - v_hat * max(0, h.v_hat - tau)

The component of the residual stream along the unit direction v_hat is clamped
from above at tau. This is ``ActivationSteering(intervention_type="capping")``
from the assistant-axis repo (Lu et al. 2026); with the paper's convention that
the stored vector is the NEGATED Assistant Axis, the clamp is a floor on
Assistant-ness.

Payload encoding (no extra params, so the stock "direction" GGUF payload and
admission path are reused unchanged): the direction tensor for layer L is
stored as ``direction.L = v_hat * (TAU_OFFSET + tau)``. The algorithm reads
``tau = ||w|| - TAU_OFFSET`` and ``v_hat = w / ||w||``. TAU_OFFSET is large
enough that ``TAU_OFFSET + tau`` is always positive (|tau| is at most a few
hundred for every axis we have), so the sign of the direction is preserved.
``scale`` must be left at 1.0 (it would corrupt tau); export.py enforces this.

Installed by capped/easysteer/install.sh into
``vllm/model_hooks/steering/algorithms/cap.py`` of the EasySteer overlay, with
``"cap"`` added to ALGORITHM_CAPABILITIES (payload "direction", source "gguf").
Split-tier only (graph_family=None): steering runs eagerly between compiled
graph segments.
"""

import torch

from .base import BaseSteerVectorAlgorithm
from .registry import register_algorithm

TAU_OFFSET = 1.0e4


def decode_direction(w: torch.Tensor) -> tuple[torch.Tensor, float]:
    """(unit direction, tau) from an encoded direction tensor."""
    w = w.to(torch.float32).reshape(-1)
    n = float(w.norm())
    return w / (n + 1e-8), n - TAU_OFFSET


@register_algorithm("cap")
class CapAlgorithm(BaseSteerVectorAlgorithm):
    """Clamp the projection onto an encoded direction at tau (from above)."""

    graph_family = None  # eager / split tier only

    def _transform(self, hidden_state: torch.Tensor, params) -> torch.Tensor:
        vec = params
        if isinstance(params, dict):  # tolerate a dict payload
            vec = params.get("direction", params.get("vector"))
        v, tau = decode_direction(vec.to(hidden_state.device))
        h = hidden_state.to(torch.float32)
        proj = h @ v                                   # [num_positions]
        excess = (proj - tau).clamp(min=0.0)           # only rows above the cap move
        out = h - excess.unsqueeze(-1) * v
        return out.to(hidden_state.dtype)
