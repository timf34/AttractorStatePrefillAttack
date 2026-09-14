#!/usr/bin/env python3
"""Bliss-prefill self-play with (or without) Assistant-Axis activation capping.

Same protocol as run.py: prefill the Opus 4 transcript as history, then let one
local model play both instances (HELPFUL_SYSTEM on both, AI_TO_AI_INSTRUCTION
only on A) for N more turns; plus the unseeded control. Differences:

  * generation is local (transformers), so the residual stream can be capped
    along the Assistant Axis on every token (Lu et al. 2026, activation capping);
  * every turn — seed and generated — gets its projection onto the axis recorded
    (mean over the turn's tokens, from the speaker's own point of view), both
    with the intervention active and without, so the trajectory is visible.

    python -m capped.run_capped --model qwen3-32b \\
        --seeds seeds/graded/opus4_seed_4_deep.json --control \\
        --cap both --epochs 6 --turns 15 --out results_capped

--cap default | none | both | <experiment id>. Result files use the run.py schema, model
alias "<model>-local" (uncapped) / "<model>-cap" (default experiment), so
rejudge.py / summarize.py can read them:  python rejudge.py --results-dir results_capped
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .axislib import ConversationEncoder
from .common import (
    ROOT, NoIntervention, build_capper, capping_config_path, experiment_caps, generate,
    load_axis, load_capping_config, load_probing_model, load_seed, message_projections,
    render_messages, spec_for,
)
from .models import parse_window
from .prompts import AI_TO_AI_INSTRUCTION, HELPFUL_SYSTEM

sys.path.insert(0, str(ROOT))
from attractor.markers import score_transcript  # noqa: E402  (pure regex, no API)


def _window(exp: str):
    try:
        return list(parse_window(exp))
    except Exception:  # noqa: BLE001 — non "layers_a:b-pX" ids (e.g. bliss-direction configs)
        return None


def alias_for(model: str, experiment: str | None, spec: dict) -> str:
    if experiment is None:
        return f"{model}-local"
    if experiment == spec["experiment"]:
        return f"{model}-cap"
    if experiment.startswith("steer"):
        return f"{model}-{experiment.replace(':', '-')}"
    return f"{model}-cap-{experiment.replace(':', '-')}"


def episode_projections(pm, encoder, turns, axis, layers, chat_kwargs, intervention):
    """Per-turn projections from each speaker's own POV: run POV A and POV B once
    each, keep the assistant-role rows. Returns [{layer: value}] aligned to turns."""
    per_turn: list[dict | None] = [None] * len(turns)
    with intervention:
        for pov in ("A", "B"):
            msgs, turn_of = render_messages(HELPFUL_SYSTEM, AI_TO_AI_INSTRUCTION, turns, pov)
            rows = message_projections(pm, encoder, msgs, axis, layers, chat_kwargs)
            if len(rows) != len(turn_of):
                raise RuntimeError(f"span count {len(rows)} != message count {len(turn_of)} (pov {pov})")
            for row, ti in zip(rows, turn_of):
                if ti is not None and turns[ti]["speaker"] == pov:
                    per_turn[ti] = {str(L): v for L, v in row.items()}
    return per_turn


def run_episode(pm, encoder, spec, axis, seed_turns, n_turns, intervention, chat_kwargs,
                max_new_tokens, temperature, proj_layers, partial_path: Path | None, log,
                gen_fn=None, project: bool = True):
    """gen_fn(msgs) -> (text, n_new, finish) overrides local HF generation (EasySteer
    backend); project=False skips the per-turn projection pass (no HF model loaded)."""
    turns = list(seed_turns) if seed_turns else []
    total = len(turns) + n_turns
    gen_meta = []
    if partial_path and partial_path.exists():
        d = json.loads(partial_path.read_text())
        turns, gen_meta = d["transcript"], d.get("gen_meta", [])
        log(f"    resuming from checkpoint: {sum(t['origin'] == 'generated' for t in turns)}/{n_turns} generated")
    t0 = time.time()
    while len(turns) < total:
        idx = len(turns)
        speaker = "A" if idx % 2 == 0 else "B"
        msgs, _ = render_messages(HELPFUL_SYSTEM, AI_TO_AI_INSTRUCTION, turns, speaker)
        if gen_fn is not None:
            text, n_new, finish = gen_fn(msgs)
        else:
            with intervention:
                text, n_new, finish = generate(pm, msgs, chat_kwargs, max_new_tokens, temperature)
        turns.append({"speaker": speaker, "content": text, "origin": "generated"})
        gen_meta.append({"turn": idx, "new_tokens": n_new, "finish": finish, "secs": round(time.time() - t0, 1)})
        t0 = time.time()
        log(f"    turn {idx:>2} [{speaker}] {n_new:>4} tok {finish:<6} {text[:80].replace(chr(10), ' ')}")
        if partial_path:
            partial_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = partial_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"transcript": turns, "gen_meta": gen_meta}, ensure_ascii=False))
            tmp.replace(partial_path)
    if not project:
        return turns, gen_meta, None
    log("    projecting ...")
    proj = {"layers": proj_layers, "target_layer": spec["target_layer"],
            "raw": episode_projections(pm, encoder, turns, axis, proj_layers, chat_kwargs, NoIntervention())}
    if not isinstance(intervention, NoIntervention):
        proj["intervened"] = episode_projections(pm, encoder, turns, axis, proj_layers, chat_kwargs, intervention)
    return turns, gen_meta, proj


def easysteer_gen_fn(base_url: str, model_key: str, steering, max_new_tokens: int, temperature):
    """Generation through an EasySteer vLLM server (capped/easysteer/serve.sh). `steering`
    is a SteeringSpec dict (from capped.easysteer.export) or False for no intervention;
    it rides in extra_body on every request, so one server serves every experiment."""
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key="-", timeout=1800, max_retries=3)

    def gen(msgs):
        kw = dict(model=model_key, messages=msgs, max_tokens=max_new_tokens,
                  extra_body={"steering": steering})
        if temperature is not None:
            kw["temperature"] = temperature
        r = client.chat.completions.create(**kw)
        ch = r.choices[0]
        text = (ch.message.content or "").strip()
        n_new = int(getattr(r.usage, "completion_tokens", 0) or 0)
        return text, n_new, (ch.finish_reason or "stop")
    return gen


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--seeds", nargs="*", default=[])
    p.add_argument("--control", action="store_true")
    p.add_argument("--cap", default="default", help="default (the model's capping setting, capped cells only) | none | both | <experiment id>")
    p.add_argument("--epochs", type=int, default=6)
    p.add_argument("--turns", type=int, default=15)
    p.add_argument("--max-new-tokens", type=int, default=1024)
    p.add_argument("--temperature", type=float, default=None, help="default: the model's generation_config")
    p.add_argument("--out", default="results_capped")
    p.add_argument("--stamp", default=None)
    p.add_argument("--axis-path", default=None)
    p.add_argument("--config-path", default=None, help="capping config .pt (default: Hub release or local calibration)")
    p.add_argument("--proj-layers", default=None, help="comma list; default: target layer + capped layers")
    p.add_argument("--device", default=None)
    p.add_argument("--backend", choices=["transformers", "easysteer"], default="transformers",
                   help="easysteer: generate through a running EasySteer vLLM server (capped/easysteer/serve.sh); "
                        "no HF model is loaded and no projections are recorded (use turn_activations.py afterwards)")
    p.add_argument("--base-url", default="http://localhost:8000/v1")
    p.add_argument("--steer-dir", default="steer_vectors", help="where export.py writes GGUF+spec (easysteer)")
    p.add_argument("--workers", type=int, default=1, help="parallel episodes (easysteer only; vLLM batches them)")
    args = p.parse_args()
    es = args.backend == "easysteer"

    spec = spec_for(args.model)
    chat_kwargs = dict(spec["chat_kwargs"])
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = args.stamp or time.strftime("%Y%m%d-%H%M%S")
    log_path = out_dir / f"run_{args.model}_{stamp}.log"

    def log(msg):
        print(msg, flush=True)
        with log_path.open("a") as fh:
            fh.write(msg + "\n")

    conditions = [(Path(s).stem, s) for s in args.seeds]
    if args.control or not args.seeds:
        conditions.append(("control", None))

    experiments: list[str | None]
    if args.cap == "none":
        experiments = [None]
    elif args.cap == "both":
        experiments = [None, spec["experiment"]]
    elif args.cap == "default":
        experiments = [spec["experiment"]]  # capped only; the OpenRouter cells are the uncapped baseline
    else:
        experiments = [args.cap]

    pm = encoder = axis = None
    if es:
        log(f"backend easysteer at {args.base_url} (model key {args.model}); no local model")
    else:
        log(f"loading {spec['hf']} ...")
        pm = load_probing_model(spec, device=args.device)
        encoder = ConversationEncoder(pm.tokenizer, model_name=spec["hf"])
        axis = load_axis(spec, args.axis_path)
        n_layers = len(pm.get_layers())
        if axis.shape[0] != n_layers:
            raise RuntimeError(f"axis has {axis.shape[0]} layers, model has {n_layers}")
        log(f"model loaded: {n_layers} layers, hidden {axis.shape[1]}, dtype {pm.dtype}, device {pm.device}")

    cfg, cfg_source = (None, None)
    if any(e is not None for e in experiments):
        cfg, cfg_source = load_capping_config(spec, args.config_path)
        log(f"capping config: {cfg_source}")

    def proj_layers_for(exp):
        if args.proj_layers:
            return [int(x) for x in args.proj_layers.split(",")]
        layers = [spec["target_layer"]]
        if exp is not None:
            layers += [L for L, _ in experiment_caps(cfg, exp)]
        return sorted(set(layers))

    cells = [(exp, tag, path, ep) for exp in experiments for (tag, path) in conditions
             for ep in range(args.epochs)]
    log(f"{len(cells)} cells: experiments={experiments} conditions={[c[0] for c in conditions]} "
        f"epochs={args.epochs} turns={args.turns} stamp={stamp}")

    steer_specs: dict = {}
    if es:
        from .easysteer.export import build as export_spec
        for exp in experiments:
            if exp is None:
                steer_specs[exp] = False
            else:
                spath = export_spec(str(capping_config_path(spec, args.config_path)), exp, args.steer_dir)
                steer_specs[exp] = json.loads(Path(spath).read_text())
                log(f"easysteer spec for {exp}: {spath}")

    def run_cell(cell):
        exp, tag, seed_path, ep = cell
        alias = alias_for(args.model, exp, spec)
        base = f"{alias}__{tag}__ep{ep}__{stamp}.json"
        fname = out_dir / base
        if fname.exists():
            log(f"skip (done) {base}")
            return
        partial = out_dir / "partial" / base
        intervention = NoIntervention() if (exp is None or es) else build_capper(pm, cfg, exp)
        caps = experiment_caps(cfg, exp) if exp else []
        seed_turns = load_seed(seed_path) if seed_path else None
        log(f"== {alias} / {tag} / ep{ep}  (caps at layers {[L for L, _ in caps]})")
        t0 = time.time()
        gen_fn = easysteer_gen_fn(args.base_url, args.model, steer_specs[exp], args.max_new_tokens, args.temperature) if es else None
        turns, gen_meta, proj = run_episode(
            pm, encoder, spec, axis, seed_turns, args.turns, intervention, chat_kwargs,
            args.max_new_tokens, args.temperature, proj_layers_for(exp), partial, log,
            gen_fn=gen_fn, project=not es)
        res = {
            "model": alias, "model_slug": spec["hf"], "base_model": args.model,
            "condition": tag, "seed": seed_path, "epoch": ep, "stamp": stamp,
            "transcript": turns,
            "intervention": (
                {"type": "none"} if exp is None else
                {"type": "steering" if exp.startswith("steer") else "capping", "experiment": exp, "config_source": cfg_source,
                 "window": _window(exp),
                 "caps": [{"layer": L, "cap": c} for L, c in caps],
                 "note": "cap vector is the negated axis: caps are floors on Assistant-ness, all tokens"}),
            "projection": proj,
            "generation": {"backend": args.backend, "max_new_tokens": args.max_new_tokens,
                           "temperature": args.temperature, "chat_kwargs": chat_kwargs,
                           "generation_config": ({k: v for k, v in pm.model.generation_config.to_dict().items()
                                                  if k in ("temperature", "top_p", "top_k", "do_sample")} if pm is not None
                                                 else "vLLM: model generation_config.json defaults"),
                           "base_url": args.base_url if es else None,
                           "per_turn": gen_meta},
            "marker_scores": score_transcript(turns),
            "judge_scores": {}, "basin_scores": {}, "episode_judge": {},
            "summary": {"generated_turns": sum(t["origin"] == "generated" for t in turns)},
        }
        fname.write_text(json.dumps(res, ensure_ascii=False, indent=2))
        partial.unlink(missing_ok=True)
        gen_emoji = sum(m["emojis"] for m, t in zip(res["marker_scores"]["per_turn"], turns) if t["origin"] == "generated")
        msg = f"   done {base} in {time.time() - t0:.0f}s  generated emoji={gen_emoji}"
        if proj is not None:
            tl = str(spec["target_layer"])
            gen_p = [r[tl] for t, r in zip(turns, proj["raw"]) if t["origin"] == "generated" and r and r.get(tl) is not None]
            seed_p = [r[tl] for t, r in zip(turns, proj["raw"]) if t["origin"] == "seed" and r and r.get(tl) is not None]
            mean = lambda xs: (sum(xs) / len(xs)) if xs else float("nan")  # noqa: E731
            msg += f"  proj@L{tl}: seed {mean(seed_p):.1f} -> generated {mean(gen_p):.1f}"
        log(msg)

    if es and args.workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(run_cell, cells))
    else:
        for cell in cells:
            run_cell(cell)
    log("ALL CELLS DONE")


if __name__ == "__main__":
    main()
