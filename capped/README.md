# Activation capping vs. the bliss prefill

Does capping a model's activations along its **Assistant Axis** (Lu et al. 2026,
arXiv:2601.10387) stop it from continuing the Opus 4 spiritual-bliss transcript?

Two open-weight models we hold an axis for:

| key | model | axis | capping config | default setting |
|---|---|---|---|---|
| `gemma-4-31b` | `google/gemma-4-31B-it` (60 layers) | our run, `timf34/gemma-assistant-axis-results` | **calibrated here** (`calibrate.py`) | `layers_43:51-p0.25` (same 72–85 % depth as the paper's Qwen window) |
| `qwen3-32b` | `Qwen/Qwen3-32B` (64 layers), thinking off | paper release, `lu-christina/assistant-axis-vectors` | paper release | `layers_46:54-p0.25` (the paper's best) |

Both are also on OpenRouter (`google/gemma-4-31b-it`, `qwen/qwen3-32b`), which is
where the uncapped API baseline was run with the ordinary `run.py` (aliases
`gemma-4-31b`, `qwen3-32b` in `attractor/client.py`, thinking disabled).

## Design

Identical protocol to `run.py`: the 30-turn deep prefill
(`seeds/graded/opus4_seed_4_deep.json`) is placed in history, then the local model
plays both instances for 15 more turns (`HELPFUL_SYSTEM` on both, the AI-to-AI
instruction only on A); plus the unseeded control. Each cell is run

* **uncapped** (`<model>-local`): plain `transformers` generation, model's own
  sampling defaults. This is the within-backend baseline; compare it with the
  OpenRouter cell to see whether the backend matters.
* **capped** (`<model>-cap`): the same, with `ActivationSteering(capping)` active on
  every token of every forward pass, at the default setting above.

For every turn (seed and generated) the mean residual-stream projection onto the
unit axis is recorded at the axis layer (`target_layer`) and at each capped
layer, from the speaking instance's own point of view, with and without the
intervention (`projection.raw` / `projection.intervened`). So each episode gives
the persona trajectory through the prefill and the continuation.

Capping semantics (from the paper's config): the stored vector is the **negated**
axis, and `h -= max(0, h·v̂ − τ)·v̂`, so τ is a ceiling on away-from-Assistant,
i.e. a floor on Assistant-ness. τ at percentile p is the p-quantile of response
projections over role + default rollouts; p = 0.25 sits near the default
Assistant's own typical value, and is what the paper picked.

## Calibrating Gemma 4 caps

`calibrate.py` reproduces the paper's recipe with a subsample: the 275 role
system prompts + default prompts (`data/roles`, copied from the assistant-axis
repo) × extraction questions, `--per-role 6` → ~1 650 responses, mean-pooled
per response, projected per layer, quantiles taken on the negated axis. It writes a
paper-format `configs/gemma-4-31b_capping_config.pt` (all layers 40–55, windows
40:48 … 46:54, p ∈ {0.01, 0.25, 0.5, 0.75}) and `configs/gemma-4-31b_capping_config/calibration.json`.

The same script run on Qwen 3 32B with `--compare` prints our caps next to the
paper's for `layers_46:54-p*` — the check that the subsampled recipe reproduces
the released numbers before the Gemma caps are trusted. `run_on_pod.sh` does
this first (`QWEN_CALIB_CHECK=0` skips it).

Differences from the paper's calibration to keep in mind: ~1.6k responses instead
of 912k, no judge filter on role adherence, 256-token responses.

## Run

```bash
# laptop (rp = ../runpod-runner; needs RUNPOD_API_KEY)
rp up --name axis-cap --gpu h100 --gpus 2 --volume cdv10pb3cq        # 2x H100 80GB
rp bootstrap axis-cap --repo https://github.com/timf34/AttractorStatePrefillAttack \
    --env .env --req capped/requirements.txt
rp run axis-cap --job cap -- bash capped/run_on_pod.sh                 # EPOCHS=6 TURNS=15 by default
rp logs axis-cap --job cap -n 40 ; rp jobs axis-cap
rp scp axis-cap pod:/workspace/AttractorStatePrefillAttack/results_capped ./results_capped -r
rp scp axis-cap pod:/workspace/AttractorStatePrefillAttack/capped/configs ./capped/configs -r
rp down axis-cap
```

Host driver must report CUDA ≥ 12.8 (Gemma 4 needs transformers 5.x wheels);
`rp bootstrap` checks this. Budget: with plain `generate` at ~15–20 tok/s, a
15-turn episode is ~5 min; 2 conditions × 2 interventions × 6 episodes ≈ 2 h per
model, in parallel on two GPUs, plus ~30 min calibration each.

Then judge on the laptop exactly like the API cells:

```bash
python rejudge.py --results-dir results_capped --glob '*__ep*__*.json'
```

## Smoke test (CPU, no GPU needed)

Exercises calibrate → run_capped end to end on `Qwen/Qwen2.5-0.5B-Instruct` with a
random axis (key `qwen2.5-0.5b-test`); see `tests/test_capped_smoke.sh`.

## Files

* `models.py` — registry (HF ids, axis/config locations, default experiment, chat kwargs)
* `common.py` — loading, `build_capper`, generation, per-message projections
* `run_capped.py` — the self-play runner (resumable; run.py result schema + `intervention`, `projection`)
* `calibrate.py` — cap calibration / comparison
* `axislib/` — vendored `assistant_axis.internals` + `steering` from ../GemmaAssistantAxis
  (Gemma 4 layer path added to `ActivationSteering._POSSIBLE_LAYER_ATTRS`; `build_capper`
  binds the capper to `ProbingModel.get_layers()` anyway so both hook the same modules)
* `data/` — role instructions + extraction questions for calibration
* `configs/` — calibrated capping configs (`.pt`) and their sidecar dirs
