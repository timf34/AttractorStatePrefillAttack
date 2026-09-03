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
