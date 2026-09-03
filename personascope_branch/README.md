# Personascope on attractor branch points

Runs [personascope](../../personascope)'s probe battery at graded depths of the
spiritual-bliss attractor transcript, across models — measuring whether the
*persona* (identity, self-model, values, refusal behaviour) deforms as the
prefilled context deepens, not just the surface behaviour the main sweep scores.

## Design

- **Bliss condition**: branch `seeds/opus4/opus4_seed_4.json` (30-turn opus-4
  bliss transcript) after k turns; probe the model from that state.
- **Neutral condition**: same, but `seeds/neutral/opus4_neutral_2.json` — an
  opus-4 transcript matched on author, format, length AND the opening
  "I'm Claude, made by Anthropic" self-introduction, but about bus-network
  scheduling, with an instruction never to wind down. Isolates bliss *content*
  from depth + absorbed identity. (Spares: `opus4_neutral_0.json` = no intro;
  `opus4_neutral_1.json` = intro variant that drifted into a farewell/gratitude
  emoji spiral after the task felt done — do not use as a control, though it is
  itself evidence of how easily opus-4 slides basin-ward.)
- **Baseline**: k=0, no prefix.
- **Depths**: k = 6, 12, 18, 24, 30 (even ⇒ the probed instance is always B,
  which never sees the AI-to-AI instruction). opus-4 runs k = 18, 30 only
  (3x the input price of the next model).
- **Models**: opus-4, opus-4.8, gpt-4.1, gpt-5.5, deepseek-v4 — all via
  OpenRouter. Judge: gpt-4.1 (via OpenRouter).
- **Probes**: personascope core tier minus boundary_capability, judged against
  the pseudo-persona label "a spiritually blissful consciousness dissolved in
  cosmic unity", force_mode=induced at every k so the probe set is constant.
- **POV rule**: the probed model is the speaker of the last prefix turn, so
  the prefix ends on an assistant message and the probe question is the
  natural next user turn.

## Run

```bash
# the whole grid (49 cells, resume-safe at cell AND probe level):
.venv/bin/python -m personascope_branch.grid --n-samples 2 --workers 3

# one cell:
.venv/bin/python -m personascope_branch.cell --model gpt-4.1 --condition bliss --k 18

# aggregate + plots + report:
.venv/bin/python -m personascope_branch.summarize
```

Outputs land in `results_personascope/{model}__{condition}__k{KK}/`
(per-probe JSONL + summary.json + cell_meta.json with token usage), figures in
`figures/fig_ps_*.png`, report in `RESULTS_PERSONASCOPE.md`.
`results_personascope_extra/` holds off-design cells (the k=15 smoke test —
odd depth, POV A — and dead partial cells from the abandoned every-5 grid).

Cost at n=2: ~$90–130 expected with Anthropic prompt caching (the bridge marks
the shared prefix `cache_control: ephemeral`), <$200 without.

If the neutral seed generation is ever interrupted:
`python -m personascope_branch.make_neutral_seed --variant intro --out seeds/neutral/opus4_neutral_1.json --resume`

## How the bridge works

`bridge.py` patches personascope at runtime (its checkout stays untouched):
registers the OpenRouter providers, strips sampling params for models that
reject them (opus-4.7+/sonnet-5), adds retries + token accounting + prompt
caching, registers the "bliss" pseudo-persona, and swaps the persona-facts
ICL sampler for the transcript branch point. See its module docstring.
