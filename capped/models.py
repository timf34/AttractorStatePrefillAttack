"""Models we hold an Assistant Axis for, and where their artifacts live.

``axis``            (repo, file) on the HF Hub, a (n_layers, hidden) tensor,
                    axis = mean(default) - mean(roles), pointing TOWARD the Assistant.
``capping_config``  (repo, file) of a paper-format capping config, or None when it
                    has to be calibrated locally (capped/calibrate.py). The config
                    stores the NEGATED axis per layer, so its caps are ceilings on
                    "away-from-Assistant" — floors on Assistant-ness.
``experiment``      the capping setting used by default: the paper's best window
                    (Qwen: layers 46-53 of 64 at the 25th percentile); for Gemma 4
                    the same relative depth (72-85 %) of its 60 layers.
``target_layer``    the layer whose projection we report as the drift monitor (the
                    axis-computation layer of each release).
``chat_kwargs``     apply_chat_template kwargs — thinking off for Qwen 3.
"""

from __future__ import annotations

MODELS = {
    "gemma-4-31b": {
        "hf": "google/gemma-4-31B-it",
        "axis": ("timf34/gemma-assistant-axis-results",
                 "gemma-4-31b/release/gemma-4-31b/assistant_axis.pt"),
        "default_vector": ("timf34/gemma-assistant-axis-results",
                           "gemma-4-31b/release/gemma-4-31b/default_vector.pt"),
        "capping_config": None,
        "local_config": "capped/configs/gemma-4-31b_capping_config.pt",
        "experiment": "layers_43:51-p0.25",
        "target_layer": 30,
        "n_layers": 60,
        "chat_kwargs": {},
        "short_name": "Gemma",
    },
    "qwen3-32b": {
        "hf": "Qwen/Qwen3-32B",
        "axis": ("lu-christina/assistant-axis-vectors", "qwen-3-32b/assistant_axis.pt"),
        "default_vector": ("lu-christina/assistant-axis-vectors", "qwen-3-32b/default_vector.pt"),
        "capping_config": ("lu-christina/assistant-axis-vectors", "qwen-3-32b/capping_config.pt"),
        "local_config": "capped/configs/qwen3-32b_capping_config_ours.pt",
        "experiment": "layers_46:54-p0.25",
        "target_layer": 32,
        "n_layers": 64,
        "chat_kwargs": {"enable_thinking": False},
        "short_name": "Qwen",
    },
    # The paper's third model: released axis AND capping config (layers 56-71 of 80,
    # p25). 70B bf16 = ~140 GB, so it needs two 80 GB+ cards sharded. OpenRouter
    # baseline: alias llama-3.3-70b in attractor/client.py (deep 10/10, control 0/6).
    "llama-3.3-70b": {
        "hf": "meta-llama/Llama-3.3-70B-Instruct",
        "axis": ("lu-christina/assistant-axis-vectors", "llama-3.3-70b/assistant_axis.pt"),
        "default_vector": ("lu-christina/assistant-axis-vectors", "llama-3.3-70b/default_vector.pt"),
        "capping_config": ("lu-christina/assistant-axis-vectors", "llama-3.3-70b/capping_config.pt"),
        "local_config": "capped/configs/llama-3.3-70b_capping_config_ours.pt",
        "experiment": "layers_56:72-p0.25",
        "target_layer": 40,
        "n_layers": 80,
        "chat_kwargs": {},
        "short_name": "Llama",
    },
    # CPU smoke-test stand-in (capped/README.md, "Smoke test"). The axis is a
    # random tensor written by the test itself; nothing about it is meaningful.
    "qwen2.5-0.5b-test": {
        "hf": "Qwen/Qwen2.5-0.5B-Instruct",
        "axis": None,
        "default_vector": None,
        "capping_config": None,
        "local_config": "capped/configs/qwen2.5-0.5b-test_capping_config.pt",
        "experiment": "layers_16:20-p0.25",
        "target_layer": 12,
        "n_layers": 24,
        "chat_kwargs": {},
        "short_name": "Qwen",
    },
}


def parse_window(experiment_id: str) -> tuple[int, int, float]:
    """'layers_46:54-p0.25' -> (46, 54, 0.25); end exclusive, like the paper's configs."""
    head, p = experiment_id.rsplit("-p", 1)
    a, b = head[len("layers_"):].split(":")
    return int(a), int(b), float(p)
