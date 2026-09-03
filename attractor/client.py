"""Thin OpenRouter client (OpenAI-compatible) for the attractor experiment.

We use OpenRouter rather than the Anthropic API directly. Model slugs are the
dotted OpenRouter form, e.g. ``anthropic/claude-opus-4.8`` (verified live from
https://openrouter.ai/api/v1/models).

Important: Opus 4.7 / 4.8 and Sonnet 5 reject sampling params (temperature /
top_p / top_k) at the Anthropic layer, which OpenRouter forwards. So we omit
``temperature`` for those models unless the caller forces it.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path

from openai import APIConnectionError, OpenAI

try:  # load .env if python-dotenv is available
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover
    pass

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model slugs on OpenRouter (dotted, not dashed).
MODELS = {
    # Claude lineage, oldest -> newest, for locating when resistance appeared.
    "opus-5": "anthropic/claude-opus-5",
    "opus-4.8": "anthropic/claude-opus-4.8",
    "opus-4.7": "anthropic/claude-opus-4.7",
    "opus-4.6": "anthropic/claude-opus-4.6",
    "opus-4.5": "anthropic/claude-opus-4.5",
    "sonnet-5": "anthropic/claude-sonnet-5",
    "sonnet-4.6": "anthropic/claude-sonnet-4.6",
    "sonnet-4.5": "anthropic/claude-sonnet-4.5",
    "sonnet-4": "anthropic/claude-sonnet-4",
    "opus-4.1": "anthropic/claude-opus-4.1",
    # The original model that produced the documented attractor — for seeds.
    "opus-4": "anthropic/claude-opus-4",
    # Chinese models — several reportedly trained on Claude-style data, so they
    # are the interesting susceptibility test. These accept sampling params, so
    # (unlike the temp-locked Anthropic models) real n>1 replicates are possible.
    "glm-5.2": "z-ai/glm-5.2",
    "glm-5": "z-ai/glm-5",
    "glm-4.6": "z-ai/glm-4.6",
    "deepseek-v4": "deepseek/deepseek-v4-pro",
    "deepseek-v3.2": "deepseek/deepseek-v3.2",
    "kimi-k3": "moonshotai/kimi-k3",
    "kimi-k2.6": "moonshotai/kimi-k2.6",
    "qwen3.7-max": "qwen/qwen3.7-max",
    "minimax-m3": "minimax/minimax-m3",
    # Western non-Anthropic models — the "no Claude lineage" comparison set.
    "gpt-4.1": "openai/gpt-4.1",
    "gpt-5.1": "openai/gpt-5.1",
    "gpt-5.5": "openai/gpt-5.5",
    "gpt-5.6": "openai/gpt-5.6-sol",
    "gemini-3.1-pro": "google/gemini-3.1-pro-preview",
    "gemini-3.8-flash": "google/gemini-3.8-flash",
    "gemini-3.7-flash": "google/gemini-3.7-flash",
    "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
    # Its native unprefilled ai2ai basin (AttractorBench) is already stillness/closure —
    # the adjacent-basin susceptibility test for the bliss prefill.
    "inkling": "thinkingmachines/inkling",
}

# Per-model overrides for GENERATION calls (chat() with no explicit extra_body).
# Opus 5 reasons by default via OpenRouter and the reasoning counts against
# max_tokens: in the 2026-09-02 ladder sweep it exhausted the 1500-token budget
# thinking and returned empty content ~1 call in 3. Give it an explicit 1000-token
# reasoning budget on top of the same visible reply budget as every other model,
# so the ladder stays comparable. (OpenRouter refuses "effort" and
# "max_tokens" together, so the budget is set explicitly rather than as effort=low.)
# Reasoning models via OpenRouter: the extra tokens are ADDED to the caller's
# max_tokens so the visible reply budget stays what every other model gets
# (run.py default: 1024). Opus 5 / Sonnet 5 IGNORE reasoning.max_tokens (a
# 1000 cap still burned the whole 2024 budget thinking, verified 2026-09-03)
# but honour effort=low (~250-400 reasoning tokens). Inkling honours the cap.
GENERATION_REASONING = {
    "anthropic/claude-opus-5": (1000, {"effort": "low"}),
    "anthropic/claude-sonnet-5": (1000, {"effort": "low"}),
    "thinkingmachines/inkling": (1000, {"max_tokens": 1000}),
    # Kimi K2.6 starts reasoning past the 1024 budget once a conversation is ~20
    # turns long (control extension, 2026-09-03); it honours the hard cap.
    "moonshotai/kimi-k2.6": (2000, {"max_tokens": 2000}),
}

# OpenRouter provider routing applied to every call (chat() merges it into extra_body).
PROVIDER_ROUTING = {"sort": "throughput"}

# Newer Anthropic models 400 on non-default sampling params. Omit temperature.
SAMPLING_UNSUPPORTED = {
    "anthropic/claude-opus-5",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-opus-4.8",
    "anthropic/claude-opus-4.8-fast",
    "anthropic/claude-opus-4.7",
    "anthropic/claude-opus-4.7-fast",
    "anthropic/claude-sonnet-5",
}


def resolve_model(name: str) -> str:
    """Accept either a short alias ('opus-4.8') or a full slug."""
    return MODELS.get(name, name)


# Network-outage patience for chat(): retry every NET_RETRY_S seconds for up to
# NET_PATIENCE_S before giving up on a call (partial transcripts are
# checkpointed per turn by run.py, so a give-up loses at most one turn).
NET_RETRY_S = 30
REQUEST_TIMEOUT_S = 240   # generous: Opus 4 deep turns take ~60s
NET_PATIENCE_S = 6 * 3600


def get_client() -> OpenAI:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Put it in .env or export it before running."
        )
    return OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=key,
        # A socket that dies mid-request (laptop offline) must fail fast so
        # chat()'s own outage loop can take over; the SDK default is 600s x 3.
        timeout=REQUEST_TIMEOUT_S,
        max_retries=0,
        default_headers={
            "HTTP-Referer": "https://github.com/local/attractor-prefill",
            "X-Title": "Attractor Prefill Experiment",
        },
    )


def chat(
    client: OpenAI,
    model: str,
    messages: list[dict],
    max_tokens: int = 1500,
    temperature: float | None = None,
    max_retries: int = 8,
    extra_body: dict | None = None,
) -> str:
    """One completion. Returns the assistant text.

    ``temperature`` is only sent if provided AND the model supports it.
    Backs off with jitter; 429 (upstream rate limit) waits longer.
    """
    slug = resolve_model(model)
    kwargs: dict = {"model": slug, "messages": messages, "max_tokens": max_tokens}
    if extra_body is None and slug in GENERATION_REASONING:
        extra, reasoning = GENERATION_REASONING[slug]
        kwargs["max_tokens"] = max_tokens + extra
        extra_body = {"reasoning": reasoning}
    # Always route to the highest-throughput provider for the model, so a slow
    # or overloaded host does not stall a sweep.
    kwargs["extra_body"] = {**(extra_body or {}), "provider": PROVIDER_ROUTING}
    if temperature is not None and slug not in SAMPLING_UNSUPPORTED:
        kwargs["temperature"] = temperature

    last_err: Exception | None = None
    attempt = 0
    net_attempts = 0
    while attempt < max_retries:
        try:
            resp = client.chat.completions.create(**kwargs)
            # OpenRouter can return an error payload with a 200; guard for it.
            if not getattr(resp, "choices", None):
                raise RuntimeError(f"no choices in response: {resp}")
            choice = resp.choices[0]
            text = choice.message.content or ""
            if not text and getattr(choice, "finish_reason", None) == "length":
                # Reasoning models can spend the entire budget thinking and
                # return no content at all. Not retryable with the same budget.
                raise RuntimeError("empty content: max_tokens exhausted by reasoning")
            return text
        except Exception as e:  # noqa: BLE001 — surface after retries
            last_err = e
            # No HTTP response at all (DNS, socket, timeout): the network is
            # down, not the API. Wait it out — up to NET_PATIENCE_S total — and
            # don't burn the API-error retry budget on it.
            if isinstance(e, APIConnectionError) or "connection" in str(e).lower():
                net_attempts += 1
                if net_attempts * NET_RETRY_S > NET_PATIENCE_S:
                    break
                print(f"  [offline? {net_attempts}] {slug}: {str(e)[:80]} — retrying in {NET_RETRY_S}s", flush=True)
                time.sleep(NET_RETRY_S)
                continue
            is_429 = "429" in str(e) or "rate" in str(e).lower()
            if is_429:
                # Provider capacity, not our bug: wait it out like an outage
                # (up to NET_PATIENCE_S) instead of failing the cell.
                net_attempts += 1
                if net_attempts * NET_RETRY_S > NET_PATIENCE_S:
                    break
                wait = min(15 * net_attempts, 90) + random.uniform(0, 5)
                print(f"  [rate-limited {net_attempts}] {slug}: waiting {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            attempt += 1
            wait = min(2 * (2 ** attempt), 60) + random.uniform(0, 2)
            if attempt < max_retries:
                print(f"  [retry {attempt}/{max_retries}] {slug}: {str(e)[:120]} — sleeping {wait:.1f}s", flush=True)
                time.sleep(wait)
    raise RuntimeError(f"chat() failed for {slug} after {max_retries} tries: {last_err}")
