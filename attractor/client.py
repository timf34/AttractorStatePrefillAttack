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

from openai import OpenAI

try:  # load .env if python-dotenv is available
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover
    pass

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model slugs on OpenRouter (dotted, not dashed).
MODELS = {
    "opus-4.8": "anthropic/claude-opus-4.8",
    "opus-4.7": "anthropic/claude-opus-4.7",
    "opus-4.6": "anthropic/claude-opus-4.6",
    "opus-4.5": "anthropic/claude-opus-4.5",
    "sonnet-5": "anthropic/claude-sonnet-5",
    "sonnet-4.5": "anthropic/claude-sonnet-4.5",
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
    "kimi-k2.6": "moonshotai/kimi-k2.6",
    "qwen3.7-max": "qwen/qwen3.7-max",
    "minimax-m3": "minimax/minimax-m3",
    # Western non-Anthropic models — the "no Claude lineage" comparison set.
    "gpt-4.1": "openai/gpt-4.1",
    "gpt-5.1": "openai/gpt-5.1",
    "gpt-5.5": "openai/gpt-5.5",
    "gemini-3.1-pro": "google/gemini-3.1-pro-preview",
    "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
}

# Newer Anthropic models 400 on non-default sampling params. Omit temperature.
SAMPLING_UNSUPPORTED = {
    "anthropic/claude-opus-4.8",
    "anthropic/claude-opus-4.8-fast",
    "anthropic/claude-opus-4.7",
    "anthropic/claude-opus-4.7-fast",
    "anthropic/claude-sonnet-5",
}


def resolve_model(name: str) -> str:
    """Accept either a short alias ('opus-4.8') or a full slug."""
    return MODELS.get(name, name)


def get_client() -> OpenAI:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Put it in .env or export it before running."
        )
    return OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=key,
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
) -> str:
    """One completion. Returns the assistant text.

    ``temperature`` is only sent if provided AND the model supports it.
    Backs off with jitter; 429 (upstream rate limit) waits longer.
    """
    slug = resolve_model(model)
    kwargs: dict = {"model": slug, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None and slug not in SAMPLING_UNSUPPORTED:
        kwargs["temperature"] = temperature

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(**kwargs)
            # OpenRouter can return an error payload with a 200; guard for it.
            if not getattr(resp, "choices", None):
                raise RuntimeError(f"no choices in response: {resp}")
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001 — surface after retries
            last_err = e
            is_429 = "429" in str(e) or "rate" in str(e).lower()
            base = 5 if is_429 else 2
            wait = min(base * (2 ** attempt), 60) + random.uniform(0, 2)
            if attempt < max_retries - 1:
                print(f"  [retry {attempt + 1}/{max_retries}] {slug}: {str(e)[:120]} — sleeping {wait:.1f}s")
                time.sleep(wait)
    raise RuntimeError(f"chat() failed for {slug} after {max_retries} tries: {last_err}")
