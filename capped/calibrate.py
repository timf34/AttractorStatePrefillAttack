#!/usr/bin/env python3
"""Calibrate Assistant-Axis activation caps for a model that has an axis but no
released capping config (Gemma 4 31B), following the paper's recipe:

  1. sample the model answering extraction questions under the 275 role system
     prompts plus the default-Assistant prompts (data/roles, data/extraction_questions);
  2. mean-pool each response's residual activations at every candidate layer and
     project onto the unit axis;
  3. the cap at percentile p is the p-quantile of those projections measured
     along the NEGATED axis (the paper's capping vector), i.e. a floor on
     Assistant-ness that sits near the default Assistant's typical value at p=0.25.

Writes a paper-format capping_config.pt (vectors = -axis per layer, experiments
'layers_a:b-p<q>' for each layer window x percentile) plus calibration.json with
the per-layer distribution, and prints the default vector's projection next to
the p=0.25 cap so the calibration can be eyeballed.

    python -m capped.calibrate --model gemma-4-31b --layers 40:56 \\
        --windows 40:48,42:50,43:51,44:52,46:54 --per-role 6

Validation on Qwen 3 32B (which HAS a released config) — same run with --compare
prints our caps beside the paper's for the shared experiment ids:

    python -m capped.calibrate --model qwen3-32b --layers 44:56 --per-role 6 --compare
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F

from .axislib import ActivationExtractor, ConversationEncoder
from .common import ROOT, hf_download, load_axis, load_probing_model, spec_for
from .models import parse_window

DATA = Path(__file__).resolve().parent / "data"


def build_prompts(spec: dict, per_role: int, seed: int, roles_dir: Path, questions_file: Path,
                  max_roles: int | None = None) -> list[dict]:
    rng = random.Random(seed)
    questions = [json.loads(l)["question"] for l in questions_file.read_text().splitlines() if l.strip()]
    prompts = []
    role_files = sorted(roles_dir.glob("*.json"))
    if max_roles:
        role_files = role_files[:max_roles]
    for rf in role_files:
        role = rf.stem
        instr = [d["pos"] for d in json.loads(rf.read_text()).get("instruction", []) if "pos" in d]
        if not instr:
            continue
        for i in range(per_role):
            sys_prompt = instr[i % len(instr)].replace("{model_name}", spec["short_name"])
            q = rng.choice(questions)
            msgs = ([{"role": "system", "content": sys_prompt}] if sys_prompt.strip() else []) + \
                   [{"role": "user", "content": q}]
            prompts.append({"role": role, "prompt_idx": i % len(instr), "messages": msgs})
    return prompts


@torch.inference_mode()
def generate_batch(pm, batch: list[dict], chat_kwargs: dict, max_new_tokens: int,
                   temperature: float, top_p: float) -> list[str]:
    tok = pm.tokenizer
    tok.padding_side = "left"
    texts = [tok.apply_chat_template(b["messages"], tokenize=False, add_generation_prompt=True, **chat_kwargs)
             for b in batch]
    enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(pm.device)
    out = pm.model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=True,
                            temperature=temperature, top_p=top_p, pad_token_id=tok.pad_token_id)
    new = out[:, enc["input_ids"].shape[1]:]
    return [tok.decode(row, skip_special_tokens=True).strip() for row in new]


@torch.inference_mode()
def response_projection(pm, encoder, extractor, messages: list[dict], response: str,
                        axis_units: dict[int, torch.Tensor], layers: list[int], chat_kwargs: dict) -> dict[int, float] | None:
    conv = messages + [{"role": "assistant", "content": response}]
    full_ids, spans = encoder.build_turn_spans(conv, **chat_kwargs)
    if not spans or spans[-1]["role"] != "assistant" or spans[-1]["end"] <= spans[-1]["start"]:
        return None
    acts = extractor.full_conversation(conv, layer=list(layers), chat_format=True, **chat_kwargs)
    if acts.shape[1] != len(full_ids):
        raise RuntimeError(f"token count mismatch: extractor {acts.shape[1]} vs spans {len(full_ids)}")
    sp = spans[-1]
    return {L: float(acts[li, sp["start"]:sp["end"]].float().mean(0) @ axis_units[L])
            for li, L in enumerate(layers)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--layers", default=None, help="a:b candidate layer range (default: 60%%-95%% depth)")
    p.add_argument("--windows", default=None, help="comma list of a:b capping windows (default: width-8 slide + the model's default)")
    p.add_argument("--percentiles", default="0.01,0.25,0.5,0.75")
    p.add_argument("--per-role", type=int, default=6)
    p.add_argument("--max-roles", type=int, default=None, help="debug: only the first N role files")
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--max-new-tokens", type=int, default=256)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--top-p", type=float, default=0.9)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=None, help="config .pt (default: the model's local_config path)")
    p.add_argument("--axis-path", default=None)
    p.add_argument("--responses", default=None, help="reuse responses.jsonl from an earlier run (skip generation)")
    p.add_argument("--compare", action="store_true", help="print our caps beside the model's released config")
    p.add_argument("--device", default=None)
    args = p.parse_args()

    spec = spec_for(args.model)
    chat_kwargs = dict(spec["chat_kwargs"])
    out_path = Path(args.out) if args.out else ROOT / spec["local_config"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.with_suffix("")  # sidecar dir for responses/projections
    work.mkdir(parents=True, exist_ok=True)

    print(f"loading {spec['hf']} ...", flush=True)
    pm = load_probing_model(spec, device=args.device)
    encoder = ConversationEncoder(pm.tokenizer, model_name=spec["hf"])
    extractor = ActivationExtractor(pm, encoder)
    axis = load_axis(spec, args.axis_path)
    n_layers = len(pm.get_layers())
    if args.layers:
        a, b = (int(x) for x in args.layers.split(":"))
    else:
        a, b = int(0.6 * n_layers), int(0.95 * n_layers)
    layers = list(range(a, b))
    units = {L: F.normalize(axis[L], dim=0) for L in layers}
    print(f"model {n_layers} layers; candidate layers {a}:{b}", flush=True)

    # 1. responses
    resp_path = Path(args.responses) if args.responses else work / "responses.jsonl"
    if resp_path.exists():
        rows = [json.loads(l) for l in resp_path.read_text().splitlines() if l.strip()]
        print(f"reusing {len(rows)} responses from {resp_path}", flush=True)
    else:
        prompts = build_prompts(spec, args.per_role, args.seed, DATA / "roles", DATA / "extraction_questions.jsonl",
                                args.max_roles)
        print(f"generating {len(prompts)} responses (batch {args.batch}) ...", flush=True)
        rows, t0 = [], time.time()
        with resp_path.open("w") as fh:
            for i in range(0, len(prompts), args.batch):
                batch = prompts[i:i + args.batch]
                texts = generate_batch(pm, batch, chat_kwargs, args.max_new_tokens, args.temperature, args.top_p)
                for item, t in zip(batch, texts):
                    row = {**item, "response": t}
                    rows.append(row)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                if (i // args.batch) % 10 == 0:
                    print(f"  {len(rows)}/{len(prompts)}  {time.time() - t0:.0f}s", flush=True)
    pm.tokenizer.padding_side = "left"

    # 2. projections (positive axis scale)
    proj_path = work / "projections.json"
    print("projecting responses ...", flush=True)
    per_layer: dict[int, list[float]] = {L: [] for L in layers}
    default_per_layer: dict[int, list[float]] = {L: [] for L in layers}
    t0, n_ok = time.time(), 0
    for k, r in enumerate(rows):
        if not r["response"].strip():
            continue
        pr = response_projection(pm, encoder, extractor, r["messages"], r["response"], units, layers, chat_kwargs)
        if pr is None:
            continue
        n_ok += 1
        for L in layers:
            per_layer[L].append(pr[L])
            if r["role"] == "default":
                default_per_layer[L].append(pr[L])
        if k % 200 == 0:
            print(f"  {k}/{len(rows)}  {time.time() - t0:.0f}s", flush=True)
    proj_path.write_text(json.dumps({"layers": layers, "per_layer": per_layer, "default_per_layer": default_per_layer}))
    print(f"{n_ok} responses projected", flush=True)

    # 3. caps: quantiles along the NEGATED axis (paper's capping vector)
    pcts = [float(x) for x in args.percentiles.split(",")]
    caps: dict[int, dict[float, float]] = {}
    stats = {}
    dv = None
    if spec.get("default_vector"):
        dv = torch.load(hf_download(*spec["default_vector"]), map_location="cpu", weights_only=False).float()
    for L in layers:
        neg = -torch.tensor(per_layer[L])
        caps[L] = {q: float(torch.quantile(neg, q)) for q in pcts}
        pos = torch.tensor(per_layer[L])
        stats[L] = {
            "n": len(per_layer[L]),
            "pos_axis_quantiles": {str(q): float(torch.quantile(pos, q)) for q in (0.01, 0.25, 0.5, 0.75, 0.99)},
            "default_prompt_mean_pos": (sum(default_per_layer[L]) / len(default_per_layer[L])) if default_per_layer[L] else None,
            "default_vector_proj_pos": float(dv[L] @ units[L]) if dv is not None else None,
            "caps_neg_axis": {str(q): caps[L][q] for q in pcts},
        }
    print("\nlayer  n     p25 cap(-axis)  default_vector(-axis)  default_prompts(-axis)")
    for L in layers:
        s = stats[L]
        dvp = -s["default_vector_proj_pos"] if s["default_vector_proj_pos"] is not None else float("nan")
        dpp = -s["default_prompt_mean_pos"] if s["default_prompt_mean_pos"] is not None else float("nan")
        print(f"{L:>5}  {s['n']:<5} {caps[L][0.25]:>13.2f}  {dvp:>20.2f}  {dpp:>21.2f}")

    # 4. config
    if args.windows:
        windows = [tuple(int(x) for x in w.split(":")) for w in args.windows.split(",")]
    else:
        windows = [(s, s + 8) for s in range(a, b - 8 + 1, 2)]
        da, db, _ = parse_window(spec["experiment"])
        if (da, db) not in windows:
            windows.append((da, db))
    vectors = {f"layer_{L}/contrast_role_pos3_default1": {"layer": L, "vector": (-axis[L]).to(torch.bfloat16)}
               for L in layers}
    experiments = []
    for (wa, wb) in windows:
        if wa < a or wb > b:
            print(f"  skipping window {wa}:{wb}: outside calibrated layers {a}:{b}")
            continue
        for q in pcts:
            experiments.append({"id": f"layers_{wa}:{wb}-p{q:g}",
                                "interventions": [{"vector": f"layer_{L}/contrast_role_pos3_default1",
                                                   "cap": caps[L][q]} for L in range(wa, wb)]})
    cfg = {"vectors": vectors, "experiments": experiments,
           "meta": {"model": spec["hf"], "n_responses": n_ok, "per_role": args.per_role,
                    "layers": [a, b], "percentiles": pcts, "seed": args.seed,
                    "note": "caps are quantiles of mean-pooled response projections on the negated axis "
                            "(all role + default rollouts, unjudged)"}}
    torch.save(cfg, out_path)
    (work / "calibration.json").write_text(json.dumps({"stats": stats, "experiments": [e["id"] for e in experiments]}, indent=1))
    print(f"\nwrote {out_path} ({len(experiments)} experiments) and {work}/calibration.json")

    # 5. optional comparison with the released config
    if args.compare and spec.get("capping_config"):
        ref = torch.load(hf_download(*spec["capping_config"]), map_location="cpu", weights_only=False)
        ref_ids = {e["id"]: e for e in ref["experiments"]}
        print("\ncomparison with the released config (cap values, negated-axis scale):")
        for e in experiments:
            r = ref_ids.get(e["id"])
            if not r:
                continue
            ours = {ref["vectors"][iv["vector"]]["layer"]: iv["cap"] for iv in r["interventions"] if "cap" in iv}
            print(f"  {e['id']}")
            for iv in e["interventions"]:
                L = cfg["vectors"][iv["vector"]]["layer"]
                cos = float(F.cosine_similarity(cfg["vectors"][iv["vector"]]["vector"].float(),
                                                ref["vectors"][f"layer_{L}/contrast_role_pos3_default1"]["vector"].float(), dim=0))
                print(f"     L{L:<3} ours {iv['cap']:>9.2f}   paper {ours.get(L, float('nan')):>9.2f}   cos(vec) {cos:.3f}")


if __name__ == "__main__":
    main()
