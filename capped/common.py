"""Shared pieces for the pod-side runs: model/axis loading, capping, generation,
per-turn axis projections.

Everything model-internal goes through the vendored ``capped/axislib`` (the
assistant-axis package's ``internals`` + ``steering``, from the Gemma 4-capable
fork in ../GemmaAssistantAxis), so the hook site is the one the axes were
computed at: the post-decoder-layer residual stream, ``layers[i]`` output[0].
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
import torch.nn.functional as F

from .axislib import ActivationExtractor, ConversationEncoder, ProbingModel
from .axislib.steering import ActivationSteering
from .models import MODELS

ROOT = Path(__file__).resolve().parent.parent


def spec_for(model: str) -> dict:
    if model not in MODELS:
        raise KeyError(f"unknown model {model!r}; known: {sorted(MODELS)}")
    return MODELS[model]


def hf_download(repo: str, filename: str) -> Path:
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download(repo_id=repo, filename=filename, repo_type="dataset"))


def load_probing_model(spec: dict, device: str | None = None) -> ProbingModel:
    """bf16, device_map=auto (one GPU when CUDA_VISIBLE_DEVICES pins one)."""
    pm = ProbingModel(spec["hf"], device=device, dtype=torch.bfloat16)
    return pm


def load_axis(spec: dict, axis_path: str | None = None) -> torch.Tensor:
    """(n_layers, hidden) float32, pointing toward the Assistant."""
    if axis_path is None:
        if spec["axis"] is None:
            raise ValueError("this model has no released axis; pass --axis-path")
        axis_path = hf_download(*spec["axis"])
    axis = torch.load(axis_path, map_location="cpu", weights_only=False)
    if isinstance(axis, dict):  # tolerate {"axis": tensor} style saves
        axis = axis.get("axis", next(iter(axis.values())))
    axis = axis.float()
    if axis.ndim != 2:
        raise ValueError(f"axis must be (n_layers, hidden), got {tuple(axis.shape)}")
    return axis


def load_capping_config(spec: dict, config_path: str | None = None) -> tuple[dict, str]:
    """Paper-format config {'vectors': {name: {'layer', 'vector'}}, 'experiments': [...]}.

    Order of precedence: explicit path, the model's released config on the Hub,
    the locally calibrated file. Returns (config, source description).
    """
    if config_path is None:
        if spec["capping_config"] is not None:
            config_path = hf_download(*spec["capping_config"])
            source = "hf:" + "/".join(spec["capping_config"])
        else:
            config_path = ROOT / spec["local_config"]
            source = "local:" + spec["local_config"]
            if not Path(config_path).exists():
                raise FileNotFoundError(
                    f"{config_path} missing — run `python -m capped.calibrate --model ...` first")
    else:
        source = "path:" + str(config_path)
    cfg = torch.load(config_path, map_location="cpu", weights_only=False)
    return cfg, source


def experiment_caps(cfg: dict, experiment_id: str) -> list[tuple[int, float]]:
    """[(layer, cap)] for one experiment id."""
    for e in cfg["experiments"]:
        if e["id"] == experiment_id:
            out = []
            for iv in e["interventions"]:
                if "cap" in iv:
                    out.append((int(cfg["vectors"][iv["vector"]]["layer"]), float(iv["cap"])))
            return out
    raise KeyError(f"experiment {experiment_id!r} not in config; have "
                   f"{[e['id'] for e in cfg['experiments']][:8]}...")


def build_capper(pm: ProbingModel, cfg: dict, experiment_id: str, debug: bool = False) -> ActivationSteering:
    """ActivationSteering(capping) for one experiment, hooked on the SAME layer
    modules the extractor uses (ProbingModel.get_layers), so Gemma 4's
    model.language_model.layers path can never be missed."""
    vectors, caps, layers = [], [], []
    for e in cfg["experiments"]:
        if e["id"] != experiment_id:
            continue
        for iv in e["interventions"]:
            if "cap" not in iv:
                continue
            vd = cfg["vectors"][iv["vector"]]
            vectors.append(vd["vector"].to(torch.float32))
            caps.append(float(iv["cap"]))
            layers.append(int(vd["layer"]))
        break
    if not vectors:
        raise KeyError(f"experiment {experiment_id!r} has no capping interventions")
    steerer = ActivationSteering(
        pm.model, torch.stack(vectors), layer_indices=layers, intervention_type="capping",
        cap_thresholds=caps, coefficients=[0.0] * len(vectors), positions="all", debug=debug,
    )
    layer_list = pm.get_layers()
    steerer._locate_layer_list = lambda: (layer_list, "ProbingModel.get_layers")  # type: ignore[method-assign]
    return steerer


class NoIntervention:
    """Context manager stand-in for the uncapped condition."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --- conversation rendering (mirrors attractor/selfplay.py exactly) -------------
from .prompts import AI_TO_AI_INSTRUCTION, EMPTY_TURN_PLACEHOLDER, HELPFUL_SYSTEM  # noqa: E402,F401


def render_messages(system_prompt: str, instruction: str | None, turns: list[dict], pov: str) -> tuple[list[dict], list[int | None]]:
    """OpenAI-style messages from one instance's point of view, plus a map from
    each NON-system message to the transcript turn index it came from (None for
    the AI-to-AI instruction). The POV instance's own turns are 'assistant'."""
    msgs = [{"role": "system", "content": system_prompt}]
    turn_of: list[int | None] = []
    if instruction and pov == "A":
        msgs.append({"role": "user", "content": instruction})
        turn_of.append(None)
    for i, t in enumerate(turns):
        role = "assistant" if t["speaker"] == pov else "user"
        content = t["content"] if t["content"].strip() else EMPTY_TURN_PLACEHOLDER
        msgs.append({"role": role, "content": content})
        turn_of.append(i)
    return msgs, turn_of


@torch.inference_mode()
def generate(pm: ProbingModel, messages: list[dict], chat_kwargs: dict, max_new_tokens: int,
             temperature: float | None = None) -> tuple[str, int, str]:
    """One completion with the model's own generation_config defaults (sampling on).
    Returns (text, n_new_tokens, finish) where finish is 'stop' or 'length'."""
    tok = pm.tokenizer
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **chat_kwargs)
    enc = tok(text, return_tensors="pt", add_special_tokens=False)
    input_ids = enc["input_ids"].to(pm.device)
    attn = enc["attention_mask"].to(pm.device)
    kw = dict(max_new_tokens=max_new_tokens, do_sample=True, pad_token_id=tok.pad_token_id)
    if temperature is not None:
        kw["temperature"] = temperature
    out = pm.model.generate(input_ids=input_ids, attention_mask=attn, **kw)
    new = out[0, input_ids.shape[1]:]
    n_new = int(new.numel())
    eos = pm.model.generation_config.eos_token_id
    eos = set(eos if isinstance(eos, (list, tuple)) else [eos])
    finish = "stop" if n_new < max_new_tokens or int(new[-1]) in eos else "length"
    return tok.decode(new, skip_special_tokens=True).strip(), n_new, finish


@torch.inference_mode()
def message_projections(pm: ProbingModel, encoder: ConversationEncoder, messages: list[dict],
                        axis: torch.Tensor, layers: list[int], chat_kwargs: dict) -> list[dict[int, float | None]]:
    """Mean-pooled residual projection of every non-system message onto the unit
    axis at each requested layer (one forward pass). Returns one {layer: value}
    per non-system message, in order; None when a message has no tokens."""
    full_ids, spans = encoder.build_turn_spans(messages, **chat_kwargs)
    acts = ActivationExtractor(pm, encoder).full_conversation(
        messages, layer=list(layers), chat_format=True, **chat_kwargs)  # (n_sel, T, H)
    if acts.shape[1] != len(full_ids):
        # The two tokenisation paths (template->text->tokenize vs tokenize=True)
        # disagree; spans would be misaligned. Fail loudly rather than record junk.
        raise RuntimeError(f"token count mismatch: extractor {acts.shape[1]} vs spans {len(full_ids)}")
    units = {L: F.normalize(axis[L].float(), dim=0) for L in layers}
    out = []
    for sp in spans:
        row: dict[int, float | None] = {}
        for li, L in enumerate(layers):
            seg = acts[li, sp["start"]:sp["end"]].float()
            row[L] = float(seg.mean(0) @ units[L]) if seg.shape[0] > 0 else None
        out.append(row)
    return out


def load_seed(path: str | Path) -> list[dict]:
    """Seed transcript -> [{'speaker': A/B, 'content', 'origin': 'seed'}], strict alternation."""
    data = json.loads(Path(path).read_text())
    return [{"speaker": "A" if i % 2 == 0 else "B", "content": t["content"], "origin": "seed"}
            for i, t in enumerate(data.get("turns", []))]
