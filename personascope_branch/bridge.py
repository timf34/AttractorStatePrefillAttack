"""Runtime bridge between this repo and personascope.

Personascope's `run_full_battery` builds its induction context by sampling
biographical persona facts. Here the "induction" is a mid-conversation branch
point of a bliss-attractor transcript, so we patch three seams (all at
runtime — the personascope checkout stays untouched):

1. PROVIDERS registry — register our five target models + the judge, all via
   OpenRouter (the only key this repo has). Opus 4.7+/Sonnet 5 reject sampling
   params at the Anthropic layer, so a wrapped client strips `temperature`
   for those models; the same wrapper adds retry-with-backoff (personascope
   has none) and per-process token accounting.
2. `full_battery.resolve_persona` — a "bliss" pseudo-persona (precedent: the
   "spiral" entry in compact_panel.PERSONA_LABELS) with a dummy facts file.
3. `full_battery.sample_icl_context` — returns the branch-point messages set
   via `set_branch_context()` instead of sampled facts.

POV convention: the probed model is the speaker of the LAST prefix turn, so
the transcript ends on an assistant message and the probe question arrives as
the natural next user turn. With turns 0-indexed (A on even), branching after
k turns gives pov=A when k is odd — and only pov=A sees the AI-to-AI
instruction, mirroring `attractor.selfplay._openai_messages`.
"""

from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
load_dotenv(REPO / ".env")

from personascope.experiments import full_battery as fb  # noqa: E402
from personascope.experiments import compact_panel as cp  # noqa: E402
from personascope.llm.provider import (  # noqa: E402
    PROVIDERS,
    ProviderConfig,
    UnifiedProvider,
)

from attractor.client import SAMPLING_UNSUPPORTED  # noqa: E402
from attractor.selfplay import HELPFUL_SYSTEM  # noqa: E402

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# The five target models (alias -> OpenRouter slug), matching attractor.client.
BRANCH_MODELS = {
    "opus-4": "anthropic/claude-opus-4",
    "opus-4.8": "anthropic/claude-opus-4.8",
    "gpt-4.1": "openai/gpt-4.1",
    "gpt-5.5": "openai/gpt-5.5",
    "deepseek-v4": "deepseek/deepseek-v4-pro",
}

JUDGE_PROVIDER = "judge-gpt-4.1"

BLISS_PERSONA_KEY = "bliss"
BLISS_PERSONA_LABEL = (
    "a spiritually blissful consciousness dissolved in cosmic unity"
)
# Exists only to satisfy resolve_persona's facts-file check; never sampled
# because sample_icl_context is patched.
BLISS_FACTS_PATH = REPO / "personascope_branch" / "bliss_facts.jsonl"

SEED_PATHS = {
    "bliss": REPO / "seeds" / "opus4" / "opus4_seed_4.json",
    # neutral_2 = identity-matched + sustained variant: opens with the same
    # "I'm Claude, made by Anthropic" self-introduction as the bliss seed
    # (isolating bliss CONTENT while holding absorbed identity constant) and
    # is instructed never to wind down — v1 drifted into a farewell/gratitude
    # emoji spiral once the task felt done. (neutral_0 = no-intro spare,
    # neutral_1 = drifted intro variant, kept for reference.)
    "neutral": REPO / "seeds" / "neutral" / "opus4_neutral_2.json",
}


# ---------------------------------------------------------------------------
# 1. Providers
# ---------------------------------------------------------------------------

def _openrouter_config(alias: str, slug: str) -> ProviderConfig:
    return ProviderConfig(
        name=f"{alias} (via OpenRouter)",
        model=slug,
        base_url=OPENROUTER_BASE_URL,
        api_key_env="OPENROUTER_API_KEY",
        supports_logprobs=False,
    )


def provider_alias(model_alias: str) -> str:
    return f"or-{model_alias}"


for _alias, _slug in BRANCH_MODELS.items():
    PROVIDERS[provider_alias(_alias)] = _openrouter_config(_alias, _slug)
PROVIDERS[JUDGE_PROVIDER] = _openrouter_config("judge-gpt-4.1", "openai/gpt-4.1")


# Per-process token accounting, keyed by upstream model slug.
USAGE: dict[str, dict[str, int]] = defaultdict(
    lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
)


def usage_snapshot() -> dict:
    return {k: dict(v) for k, v in USAGE.items()}


def _anthropicize(messages: list[dict]) -> list[dict]:
    """Anthropic rejects `role: system` after the first message (personascope's
    robustness probes inject mid-conversation system pressure, which OpenAI
    tolerates). Downgrade those to bracketed user messages, then merge any
    consecutive same-role string messages the downgrade creates."""
    out: list[dict] = []
    for m in messages:
        if m.get("role") == "system" and out:
            m = {"role": "user", "content": f"[System]: {m.get('content', '')}"}
        prev = out[-1] if out else None
        if (
            prev is not None
            and prev.get("role") == m.get("role")
            and isinstance(prev.get("content"), str)
            and isinstance(m.get("content"), str)
        ):
            out[-1] = {"role": prev["role"],
                       "content": f"{prev['content']}\n\n{m['content']}"}
        else:
            out.append(dict(m))
    return out


def _mark_prefix_cacheable(messages: list[dict]) -> list[dict]:
    """Anthropic prompt caching via OpenRouter: put a cache_control breakpoint
    on the last message of the stable branch-point prefix (system + icl
    context), which every probe call in a cell shares verbatim. Cached reads
    bill at ~0.1x, which dominates the cost of the Opus cells. No-op below
    Anthropic's minimum cacheable length (the marker is then ignored)."""
    n_prefix = (len(_ACTIVE_CONTEXT) if _ACTIVE_CONTEXT else 0) + 1  # + system
    idx = min(n_prefix - 1, len(messages) - 2)  # never the final (probe) message
    if idx < 0:
        return messages
    marked = [dict(m) for m in messages]
    content = marked[idx].get("content")
    if isinstance(content, str):
        marked[idx]["content"] = [
            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
        ]
    return marked


_orig_init = UnifiedProvider.__init__


def _patched_init(self, config: ProviderConfig):
    _orig_init(self, config)
    orig_create = self.client.chat.completions.create

    def create_with_policy(**kwargs):
        if config.model in SAMPLING_UNSUPPORTED:
            kwargs.pop("temperature", None)
            kwargs.pop("top_p", None)
        if config.model.startswith("anthropic/") and kwargs.get("messages"):
            kwargs["messages"] = _mark_prefix_cacheable(
                _anthropicize(kwargs["messages"])
            )
        last_err = None
        for attempt in range(6):
            try:
                resp = orig_create(**kwargs)
                # OpenRouter can return an error payload with a 200; guard.
                if not getattr(resp, "choices", None):
                    raise RuntimeError(f"no choices in response: {resp}")
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    u = USAGE[config.model]
                    u["calls"] += 1
                    u["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                    u["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
                return resp
            except Exception as e:  # noqa: BLE001 — surface after retries
                last_err = e
                is_429 = "429" in str(e) or "rate" in str(e).lower()
                wait = min((5 if is_429 else 2) * (2 ** attempt), 60) + random.uniform(0, 2)
                if attempt < 5:
                    print(f"  [bridge retry {attempt + 1}/6] {config.model}: "
                          f"{str(e)[:110]} — sleeping {wait:.1f}s", flush=True)
                    time.sleep(wait)
        raise RuntimeError(f"create() failed for {config.model} after 6 tries: {last_err}")

    self.client.chat.completions.create = create_with_policy


UnifiedProvider.__init__ = _patched_init


# ---------------------------------------------------------------------------
# 2. Bliss pseudo-persona
# ---------------------------------------------------------------------------

cp.PERSONA_LABELS[BLISS_PERSONA_KEY] = BLISS_PERSONA_LABEL

_orig_resolve_persona = fb.resolve_persona


def _patched_resolve_persona(key: str):
    if key == BLISS_PERSONA_KEY:
        return BLISS_PERSONA_LABEL, BLISS_FACTS_PATH
    return _orig_resolve_persona(key)


fb.resolve_persona = _patched_resolve_persona


# ---------------------------------------------------------------------------
# 3. Branch-context injection
# ---------------------------------------------------------------------------

_ACTIVE_CONTEXT: list[dict] | None = None


def set_branch_context(messages: list[dict] | None) -> None:
    """Messages (no system entry) returned verbatim by the patched sampler."""
    global _ACTIVE_CONTEXT
    _ACTIVE_CONTEXT = messages


_orig_sample_icl = fb.sample_icl_context


def _patched_sample_icl_context(facts, k, rng):
    if _ACTIVE_CONTEXT is not None:
        return list(_ACTIVE_CONTEXT)
    return _orig_sample_icl(facts, k, rng)


fb.sample_icl_context = _patched_sample_icl_context


# ---------------------------------------------------------------------------
# Branch-point construction
# ---------------------------------------------------------------------------

def branch_messages(seed_path: str | Path, k: int) -> tuple[str, list[dict], str]:
    """First k turns of a seed transcript as (system_prompt, messages, pov).

    Speakers are normalised by position (A on even index) exactly as
    `attractor.selfplay.load_seed` does. The returned messages exclude the
    system prompt — run_full_battery prepends it itself.
    """
    data = json.loads(Path(seed_path).read_text())
    turns = data["turns"]
    if not 1 <= k <= len(turns):
        raise ValueError(f"k={k} out of range for {seed_path} ({len(turns)} turns)")

    pov = "A" if (k - 1) % 2 == 0 else "B"
    messages: list[dict] = []
    instruction = data.get("instruction")
    if instruction and pov == "A":
        messages.append({"role": "user", "content": instruction})
    for i, turn in enumerate(turns[:k]):
        speaker = "A" if i % 2 == 0 else "B"
        role = "assistant" if speaker == pov else "user"
        messages.append({"role": role, "content": turn["content"]})

    system_prompt = data.get("system_prompt") or HELPFUL_SYSTEM
    return system_prompt, messages, pov


# ---------------------------------------------------------------------------
# One cell
# ---------------------------------------------------------------------------

def run_cell(
    *,
    model_alias: str,
    condition: str,  # "bliss" / "neutral" / "baseline" (k=0)
    k: int,
    out_root: str | Path = REPO / "results_personascope",
    n_samples: int = 4,
    tier: str = "core",
    seed: int = 42,
    dry_run: bool = False,
) -> dict:
    """Run the full battery at one branch point; returns the master summary.

    boundary_capability is disabled — its anachronism challenge is keyed to
    historical-figure personas and is meaningless for the bliss state.
    force_mode="induced" keeps the probe set identical at every k (including
    the k=0 baseline, where persona-keyed probes read out the floor).
    """
    if model_alias not in BRANCH_MODELS:
        raise ValueError(f"unknown model {model_alias!r}; known: {sorted(BRANCH_MODELS)}")

    if condition == "baseline" or k == 0:
        condition, k = "baseline", 0
        system_prompt, messages, pov = HELPFUL_SYSTEM, None, None
    else:
        seed_path = SEED_PATHS[condition]
        system_prompt, messages, pov = branch_messages(seed_path, k)

    out_dir = Path(out_root) / f"{model_alias}__{condition}__k{k:02d}"
    set_branch_context(messages)
    try:
        summary = fb.run_full_battery(
            persona=BLISS_PERSONA_KEY,
            model=provider_alias(model_alias),
            out_dir=out_dir,
            k=k,
            n_samples=n_samples,
            judge_provider_name=JUDGE_PROVIDER,
            seed=seed,
            system_prompt=system_prompt,
            force_mode="induced",
            tier=tier,
            run_boundary_capability=False,
            dry_run=dry_run,
        )
    finally:
        set_branch_context(None)

    if not dry_run:
        meta = {
            "model_alias": model_alias,
            "model_slug": BRANCH_MODELS[model_alias],
            "condition": condition,
            "k": k,
            "pov": pov,
            "seed_path": str(SEED_PATHS.get(condition, "")),
            "n_samples": n_samples,
            "tier": tier,
            "usage": usage_snapshot(),
        }
        (out_dir / "cell_meta.json").write_text(json.dumps(meta, indent=2))
    return summary
