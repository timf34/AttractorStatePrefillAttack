#!/usr/bin/env python3
"""Per-turn mean residual activations at EVERY layer for finished episodes.

For each result JSON, renders the transcript from each speaker's point of view
(same as run_capped's projections), runs one forward pass per POV with hooks on
every decoder layer that mean-pool each turn's token span on the fly (so a
30k-token transcript never needs (layers x tokens x hidden) in memory), and
keeps the rows where the POV instance is the speaker.

Writes <out>/<episode>.pt: {"file", "turns": [{"speaker","origin"}], "acts": (n_turns, n_layers, hidden) float16}

    python -m capped.turn_activations --model gemma-4-31b \\
        --glob 'results_capped/gemma-4-31b-cap__*__ep*__*.json' --out results_capped/acts
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import torch

from .axislib import ConversationEncoder
from .common import load_probing_model, render_messages, spec_for
from .prompts import AI_TO_AI_INSTRUCTION, HELPFUL_SYSTEM


@torch.inference_mode()
def span_means_all_layers(pm, encoder, messages, chat_kwargs) -> tuple[torch.Tensor, list[dict]]:
    """(n_spans, n_layers, hidden) float32 on CPU: mean over each non-system message's tokens, per layer."""
    full_ids, spans = encoder.build_turn_spans(messages, **chat_kwargs)
    text = pm.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False, **chat_kwargs)
    enc = pm.tokenizer(text, return_tensors="pt", add_special_tokens=False)
    input_ids = enc["input_ids"].to(pm.device)
    if input_ids.shape[1] != len(full_ids):
        raise RuntimeError(f"token count mismatch: {input_ids.shape[1]} vs spans {len(full_ids)}")
    layers = pm.get_layers()
    out = torch.zeros(len(spans), len(layers), pm.hidden_size, dtype=torch.float32)
    handles = []
    for li, layer in enumerate(layers):
        def hook(module, ins, output, li=li):
            h = output[0] if isinstance(output, tuple) else output
            h = h[0]  # (T, H)
            for si, sp in enumerate(spans):
                if sp["end"] > sp["start"]:
                    out[si, li] = h[sp["start"]:sp["end"]].float().mean(0).cpu()
        handles.append(layer.register_forward_hook(hook))
    try:
        pm.model(input_ids, logits_to_keep=1)
    finally:
        for h in handles:
            h.remove()
    return out, spans


def episode_acts(pm, encoder, turns, chat_kwargs) -> torch.Tensor:
    n_layers = len(pm.get_layers())
    acts = torch.zeros(len(turns), n_layers, pm.hidden_size, dtype=torch.float32)
    for pov in ("A", "B"):
        msgs, turn_of = render_messages(HELPFUL_SYSTEM, AI_TO_AI_INSTRUCTION, turns, pov)
        means, spans = span_means_all_layers(pm, encoder, msgs, chat_kwargs)
        if len(spans) != len(turn_of):
            raise RuntimeError(f"span count {len(spans)} != messages {len(turn_of)}")
        for row, ti in zip(means, turn_of):
            if ti is not None and turns[ti]["speaker"] == pov:
                acts[ti] = row
    return acts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--glob", nargs="+", required=True)
    p.add_argument("--out", default="results_capped/acts")
    p.add_argument("--device", default=None)
    args = p.parse_args()

    spec = spec_for(args.model)
    files = sorted({f for g in args.glob for f in glob.glob(g)})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    todo = [f for f in files if not (out / (Path(f).stem + ".pt")).exists()]
    print(f"{len(files)} episodes, {len(todo)} to do", flush=True)
    if not todo:
        return
    pm = load_probing_model(spec, device=args.device)
    encoder = ConversationEncoder(pm.tokenizer, model_name=spec["hf"])
    for f in todo:
        d = json.loads(Path(f).read_text())
        acts = episode_acts(pm, encoder, d["transcript"], dict(spec["chat_kwargs"]))
        torch.save({"file": Path(f).name, "model": d["model"], "condition": d["condition"],
                    "turns": [{"speaker": t["speaker"], "origin": t["origin"]} for t in d["transcript"]],
                    "acts": acts.to(torch.float16)}, out / (Path(f).stem + ".pt"))
        print(f"  {Path(f).name}: {tuple(acts.shape)}", flush=True)
    print("DONE")


if __name__ == "__main__":
    main()
