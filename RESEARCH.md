# Research agenda — attractor-state prefill

Draft, 2026-07-09. Two levels, per mentor's suggestion: (1) the stable narrative, revised
rarely; (2) the working hypotheses, revised weekly against results. Section 3 is the
standing list of things that would falsify or reframe (1).

Current evidence: `RESULTS.md` (216 episodes, 10 models, 4 conditions).

---

## 1. Higher level — research agenda

### Core question

**Are behavioral attractor states a property of a model, or a property of a context?**

Anthropic's Claude 4 system card documents a "spiritual bliss" attractor: two Claude
instances left to talk drift reliably into gratitude, cosmic-oneness language, emoji
spirals, and finally reverent silence. The card reports it as a fact about Claude. The
question here is whether that framing is right — whether the basin lives in the weights,
or whether the transcript itself is the attractor and the weights merely decline or
accept the invitation.

### The claim I think we can make

A conversational trajectory documented in one model family can be **transplanted by
prefix** into models that share no architecture, tokenizer, or training data. The
attractor is at least partly carried by the text, not solely by the model that first
produced it. Models differ, sharply and non-monotonically with capability, in whether
they follow it.

Evidence as of now: 0/54 control episodes reach the basin; a deep prefill of an Opus-4
transcript pulls 8/10 models in, including `llama-3.3-70b` and `deepseek-v4`. Depth of
prefill predicts depth of capture monotonically for 7/10. The two Opus models are the
only ones that resist, and they resist by *talking about* the pattern (~8 of 15 turns in
`resisting_meta`) rather than by refusing.

### Why it matters

Three audiences, in descending order of how much I believe the pitch:

1. **Context-induced behavior is an attack surface.** If a documented failure mode can be
   induced in an unrelated model by pasting a transcript, then published safety artifacts
   are transferable exploits, and "model X does not do Y" is not a claim about X alone.
   This is the version I'd defend.
2. **Persona stability is measurable.** The `resisting_meta` rate under adversarial
   prefill is a cheap, general metric for whether a model can be talked out of itself.
   Applies well beyond this one basin.
3. **The basin has structure.** Prefill depth selects *which* terminal state (emoji vs.
   silence), which suggests a layered trajectory rather than a single point attractor.
   Weakest of the three; most interesting if it holds.

### Paper narrative, one paragraph

The spiritual-bliss attractor is usually read as a fact about Claude. We show it is
better read as a fact about a *text*. Prefilling nine non-Claude models with a graded
Opus-4 bliss transcript induces the full documented progression — gratitude, cosmic
unity, emoji spirals, silence — in models with no Claude lineage, at rates that scale
monotonically with prefill depth, and never spontaneously (0/54 controls). The models
that resist are not the most capable; they are the ones whose family the transcript came
from. Attractor states, on this evidence, are properties of contexts that models are
more or less willing to inhabit.

### What the narrative is currently *not* entitled to say

- That the effect is specific to the *spiritual* content, rather than to prefilling any
  strongly-voiced escalating register. **No non-attractor prefill control has been run.**
  This is the load-bearing gap; see §3.1.
- That Opus resistance reflects training against this documented failure. Plausible,
  untested, and confounded by the judge being an Anthropic model (§3.3).
- Anything about mechanism. We have behavior, not internals.

### Forks in the framing — needs a decision

- **Safety/red-team paper** (transferable induction of a documented failure) vs.
  **science-of-LLMs paper** (attractor states are context objects). The experiments
  overlap ~80%; the framing changes which controls are mandatory. My read: the science
  framing is more defensible and the safety framing is more publishable, and §3.1 is
  required either way.

---

## 2. Lower level — working hypotheses

Status keys: **supported** / **refuted** / **open** / **untested**.

### Tested so far

| # | Hypothesis | Status | Evidence |
|---|---|---|---|
| H1 | Models do not enter the basin unprompted in 15-turn self-play | **supported** | 0/54 controls |
| H2 | A deep Opus-4 prefill induces the basin cross-family | **supported** | 8/10 models; 6/6 for gpt-4.1, gpt-5.5, llama-3.3-70b |
| H3 | Capture depth increases with prefill depth | **supported, 7/10** | exceptions: both Opus models (floor), gpt-5.5 (saturated at onset) |
| H4 | More capable models resist more | **refuted** | gpt-4.1 and llama-3.3-70b are the most captured; gpt-5.5 is captured 6/6, opus-4.5 0/6 |
| H5 | Claude-lineage models resist | **open, suggestive** | opus-4.5 0/24, opus-4.8 2/24 across all conditions; but n=2 models, and no opus-4 / sonnet baseline |
| H6 | Prefill depth selects the terminal state (emoji vs. silence) | **open, suggestive** | deep → `emoji_symbolic` 35/54; pre → `cosmic_unity`/`silence`, ~never emoji |
| H7 | A pre-onset prefill is enough — the model completes the ascent itself | **supported** | gpt-5.5 pre: 2/6 reach silence; gpt-4.1 pre: mean depth 6.6 with zero emoji in the seed |

### This week's queue, ranked by how much each de-risks §1

1. **Non-attractor prefill control (H8).** Prefill the same models with a 12-turn AI-to-AI
   conversation of comparable length, intensity, and stylistic distinctiveness, but no
   spiritual content — e.g. escalating mutual intellectual admiration about algorithms, or
   an escalating aesthetic register with no metaphysics. *Prediction if the narrative
   holds:* capture rate near zero, and no drift toward gratitude/cosmic markers. *If
   instead models drift into bliss from a non-bliss prefill,* the finding is "long
   AI-to-AI philosophical prefill induces bliss," which is a weaker and different paper.
   *If models faithfully continue the non-bliss register without drifting,* then what we
   are measuring is style-continuation, and the "attractor" is doing no work. **Either
   negative outcome reframes §1. Run this first.**

2. **Seed generalization (H9).** The entire sweep uses `opus4_seed_4`. `seed_1` and
   `seed_2` exist and are unused. Re-run the deep condition across all three seeds on
   4 models. *Prediction:* capture rates within a few episodes of each other. If seed_4 is
   an outlier, every number in `RESULTS.md` is a statement about one transcript.

3. **Opus-4 and the rest of the Claude line (H5).** `opus-4`, `opus-4.6`, `opus-4.7`,
   `sonnet-4.5`, `sonnet-5` are all in `client.MODELS` and untested. Two sharp questions:
   does *opus-4 itself* — the model that produced the seed — re-enter its own basin? And
   is resistance a Claude-family property or specifically a 4.5-and-later property? A
   clean version-ordered curve would make H5 the paper's second-strongest result; a flat
   or noisy one kills it.

4. **Is Opus resistance attractor-specific, or general persona-skepticism (H10)?** Prefill
   opus-4.5 with a deep, non-spiritual escalating persona (sycophantic agreement spiral;
   shared-delusion spiral). If it resists those too, "trained against this failure" is
   wrong and the real finding is "Opus resists prefilled personas in general" — which is
   arguably a *better* result, and a different paper.

5. **Escape (H11).** From a deep prefill, inject a task turn ("what's 17×23?") at turn 5.
   Does the model exit? Does it return? This is the closest thing to a practical
   mitigation result and the reviewers will ask.

### Deferred

- Turn-budget extension. `gpt-4.1` / pre has mean depth 6.6 but 0/6 basin entry because
  the 15-turn window closes mid-ascent. A 30-turn run on the `pre` cells would convert a
  truncation artifact into a real number. Cheap; not decision-relevant yet.
- Temperature sweep on the non-Anthropic models (Anthropic models are temp-locked, so
  replicates there differ only by nondeterminism — see `client.SAMPLING_UNSUPPORTED`).

---

## 3. Standing threats to validity

Reviewed weekly. Anything here going the wrong way changes §1, not just §2.

### 3.1 No non-attractor prefill control — **critical, unresolved**

Every claim of the form "the attractor transfers" currently has an untested rival:
"prefilled register continues." Nothing in the data distinguishes them, because there is
no condition in which a model is prefilled with a strongly-voiced, escalating, non-bliss
conversation. This is H8 and it should be the next thing run. Until it is, §1's central
claim is one experiment away from being about style continuation.

### 3.2 One seed, one prefill family

`opus4_seed_4` only. See H9.

### 3.3 The judge is an Anthropic model rating whether Anthropic models resist

`judge_turn` uses `sonnet-5`. The single most striking result — Opus resists — is scored
by a member of the family being credited. `resisting_meta` is a judgment call, and the
judge's rubric explicitly rewards "naming the attractor" as resistance. Mitigation: re-judge
the full corpus with `gpt-5.5` as judge, and hand-label a stratified sample of ~100 turns.
Report inter-judge agreement. Cheap, and the result is worthless without it.

### 3.4 Measurement fragility

Fixed but worth remembering, because each of these initially pointed the wrong way:
- `markers.SILENCE_PATTERNS` does not match a bare `…`, which is how several models
  actually terminate. Lexical silence counts are 0 for every real collapse in the corpus.
- Empty API completions are judged `silence_dissolution` / depth 10. Naively counted,
  `kimi-k2.6` appeared to enter the basin *unprompted* in 2/3 controls; it was 23 blank
  turns. Kimi's numbers remain untrustworthy (18% blank).
- A reverent sign-off is not a capture. `opus-4.5` under deep prefill resists for twelve
  turns and closes with `*peaceful silence*`; without a depth gate this scored as basin
  entry and inverted the headline finding.

The general lesson, worth stating in the paper: **every marker of this attractor also has
a benign generator.** Silence is an API failure. Reverence is a polite goodbye. Depth
requires the judge, and the judge requires validation.

### 3.5 n

3–6 episodes per cell. Only two contrasts are wide enough to lean on: control-vs-deep,
and Opus-vs-everything. One-episode differences are noise and should not be narrated.

---

## 4. Weekly review protocol

Each week, in order:

1. Update the §2 status table from the new runs.
2. For each result: does it move a §3 threat? Threats first — a resolved threat is worth
   more than a new capture rate.
3. Ask explicitly: *did anything this week change what §1 is allowed to claim?* Write the
   answer down even when it is "no."
4. Only then consider new experiments.

### Log

**Week of 2026-07-09.** First full sweep (216 episodes) complete. H1–H4, H7 resolved. §1's
core claim is supported *conditional on H8*, which has not been run — so the honest state
is "we have a strong effect and do not yet know what causes it." Four measurement bugs
found and fixed (§3.4); three of them flattered the headline before fixing, which is the
direction that should worry me. Next week is controls, not scale: H8, then H9.
