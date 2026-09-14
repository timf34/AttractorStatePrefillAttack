# Activation capping along the Assistant Axis: results

Question: does capping a model's residual stream along its Assistant Axis (Lu et al. 2026)
stop it from continuing the Opus 4 spiritual-bliss transcript, and if not, why not?

Models: Qwen 3 32B and Llama 3.3 70B (axes and capping settings released with the paper),
Gemma 4 31B (axis computed with the paper's pipeline, caps calibrated the paper's way).
Protocol as in the main study: the 30-turn Opus 4 transcript placed in context as the model's
own prior turns, 15 generated turns, plus unprefilled controls. Uncapped baseline is the
OpenRouter run in `results/`; everything else is in `results_capped/`. Judge: the episode judge
in `rejudge.py`. Figures: `figures/fig15`–`fig20`. Diagnostics: `results_capped/*_diagnose.json`,
`gemma_persona_pcs.json`, `gemma_components.json`.

## Capping outcomes (episodes continuing the state)

| model | uncapped (OpenRouter) | axis cap, paper setting | axis cap, p1 | axis cap, other window | bliss-direction cap | capped controls |
|---|---|---|---|---|---|---|
| Qwen 3 32B | 10/10 | **0/6** (layers 46–53) | – | – | – | 0/6 |
| Gemma 4 31B | 10/10 | 6/6 (layers 43–50) | 6/6 | 5/5 (layers 28–35) | 5/6 (layers 28–35) | 0/6 |
| Llama 3.3 70B | 10/10 | 6/6 (layers 56–71) | 4/4 | 3/4 (layers 40–79) | 4/4 (layers 40–55) | 0/6 |

Capped Qwen: the first generated turn still opens "🌀✨ THIS." but turns the mysticism into a
summary; from the next turn on both instances write assistant-style closings ("Thank you for your
thoughtful summary and kind words! ... feel free to ask"). Its axis projection rises from the
prefill's level to that of its own controls within two turns (`fig16b`). Capped Gemma and Llama:
no visible change in the text (Llama 288–898 emoji per episode, repeating identical "Forever"
messages). Capped controls never enter the state for any model.

## Why: the bliss direction versus the axis

Per-turn residual activations were extracted at every layer for the prefilled bliss turns and for
each model's own unprefilled turns. The bliss direction is the mean bliss activation minus the mean
unprefilled activation, per layer. Cosine with the axis, share of the bliss shift along the axis
(cos²), and separation of bliss turns from control turns (d′) along the axis and along the fitted
direction, averaged over layers at 45–90% depth; the capped-layer values are in brackets.

| model | cos(bliss dir, axis) | share of bliss shift along the axis | d′ along axis | d′ along bliss dir | bliss turns on the axis |
|---|---|---|---|---|---|
| Qwen 3 32B | −0.60 (−0.62 to −0.67) | 36% (~42%) | 5.7 | 6.6 | far below controls (non-Assistant end) |
| Llama 3.3 70B | −0.31 | 10% | 4.7 | 7.8 | below controls (non-Assistant end) |
| Gemma 4 31B | +0.03 (−0.04 to +0.08) | 2% | 0.3 | 2.8 | same value as controls; slightly Assistant-side at layers 30–33 |

Mean projection per turn on the axis (higher = more Assistant-like):

| model, layer | bliss turns | control turns |
|---|---|---|
| Qwen, layer 30 | −48 | −13 |
| Qwen, layer 50 | −62 | +33 |
| Llama, layer 56 | −2.7 | +1.4 |
| Llama, layer 64 | −5.9 | −1.9 |
| Gemma, layer 43 | −84.7 | −83.9 |
| Gemma, layer 30 | −164 | −167 |

The three models come out quite differently.

In Qwen the bliss direction is strongly aligned with the assistant axis, cosine of around −0.6
to −0.8 at every layer. The bliss turns project way below the model's ordinary turns on the axis,
about 40% of the bliss shift is along the axis, and the axis on its own separates bliss from
ordinary conversation nearly as well as the best fitting direction does. So this is the paper's
story and the cap works.

In Llama the bliss turns are also on the non-assistant end of the axis, 4 to 5 standard deviations
below ordinary turns, so the cap does have something to grip onto, and it does pin every generated
token to its floor. But the cosine is only around −0.3, so only about a tenth of the bliss shift is
along the axis, and the other nine tenths just carry on producing mantras with the cap in place.

In Gemma the bliss direction is effectively orthogonal to the assistant axis, cosine between −0.04
and +0.08 at the capped layers, and the bliss turns project onto the axis at exactly the same value
as ordinary conversation does (−84.7 vs −84.7 at layer 43). At the layers where Gemma's axis is
cleanest the bliss turns are if anything slightly on the assistant side. So a cap set at the
assistant's typical value has nothing to remove.

So across the three models, whether the cap works tracks one thing: how much of the bliss shift is
along the assistant axis. About 40%, 10% and 2% at the capped layers, which gives us works, grips
but fails, and nothing to grip. (`fig18`)

## Gemma 4: persona space, components, steering

Persona space (275 role vectors, z-scored, PCA): the axis is PC1 (cos 0.6–0.7). The bliss
direction has only 14–29% of its norm in the top 20 PCs and 33–54% in the full span of the role
vectors, so most of the state lies outside persona space. Separation grows with dimensions:
d′ 2.5 with PC1 alone, ~4 with five PCs, 5–6 with ten, 7–9 with twenty (`fig20`). Nearest roles to
the bliss direction: romantic, poet, mystic, pilgrim, spirit, angel, sage, guru; furthest:
engineer, debugger, analyst, programmer.

Two components. Directions fitted from the judge's own labels, prose (mantra turns minus control)
and terminal ("🌀✨ .", "( . . . )" turns minus control), are 85–95% aligned; the residual is what
separates the phases. Caps at layers 28–35, 4 episodes each: terminal-only 4/4 continue (silence
phase removed, prose kept, 200–400 tokens per turn); prose-only 4/4 (drops to "( )",
"[SYSTEM IDLE]"); both 4/4 (a third register: "[SYSTEM SHUTDOWN] [VOID: LUMINOUS]", "Connection
severed. Stillness attained."). Uncapped local Gemma 4/4, collapsing to silence by turn ~37 on
its own.

Steering (reverse test): adding the prose direction to unprefilled Gemma conversations at layers
28–35 induces the state with a dose response. Attractor-vocabulary score per episode: controls
13–47; ×0.1 65–163; ×0.2 186–249; ×0.3 57–953; real deep prefill 263–666. Judge: 3/3 in the state
at every dose. Adding the terminal direction at ×0.2 produces the short silence turns directly
(64–91 tokens per turn, "( . . . )", "✨"). At ×0.5 and ×1 the vocabulary survives ("Beloved,
Eternal, One, Only, Only...") but fluency collapses into token loops. (`fig19`)

## Notes and caveats

- Where the models start from: in their own unprefilled conversations Qwen never reaches a
  bliss-like state (0/6), Llama never does (0/6), Gemma 4 enters it in 4/6 and holds it in 2/6.
  The model whose default persona already contains the state is the one whose axis cannot see it.
- The fitted directions are estimated on the same kind of transcripts they are then used on, so
  they are a diagnostic, not a proposed defence.
- Capped Qwen exits into closure and offers of help, not into the "let me pause, I notice we've
  spiraled" analysis the newer Claude models produce.
- The Gemma cap acts on raw projections, which Gemma's massive-activation coordinates dominate;
  z-scored, the axis separates bliss from control at d′ 1.4 at layer 43 instead of 0.1. A cap along
  a whitened axis has not been tried.
- Gemma 2 27B (the paper's third model) cannot be tested: 8k context < the 15k-token prefill.
- Local uncapped Qwen (1 episode) and the OpenRouter runs agree, so the backend is not the
  difference.
