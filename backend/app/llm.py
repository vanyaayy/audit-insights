"""LLM access: the Gemini API, behind a small provider interface.

Everything the pipeline needs from an LLM goes through `generate(system, prompt,
schema, tag)`, which returns a validated Pydantic object. Adding another provider
(e.g. a government-hosted endpoint or a local model) means one more class with
that method; prompts, schemas, verification and the UI don't change.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Protocol, TypeVar

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
RETRYABLE = {429, 500, 502, 503, 504}
ATTEMPTS_PER_MODEL = 4
# Waits before retrying an overloaded model; "high demand" spikes usually pass within a minute.
OVERLOAD_BACKOFF = (10, 30, 60)
RATE_LIMIT_WAIT = 30
# Low-cost default: extraction is a closely specified, schema-bound task and every
# quote is verified in code. Set GEMINI_MODEL to a larger model to trade cost for quality.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
# Fallbacks run on separate capacity, so one overloaded model doesn't stop a run.
DEFAULT_FALLBACKS = "gemini-3.6-flash,gemini-3.8-flash"

log = logging.getLogger("llm")


PROVIDERS = ("gemini",)


class LLMClient(Protocol):
    """What the pipeline needs from any provider."""

    provider: str
    model: str
    models_used: set[str]

    def generate(self, *, system: str, prompt: str, schema: type[T], tag: str) -> T: ...


class LLMError(RuntimeError):
    pass


def cache_file(model: str, system: str, prompt: str, schema: type[BaseModel], tag: str) -> Path:
    key_src = json.dumps([model, system, prompt, schema.model_json_schema()], sort_keys=True)
    return CACHE_DIR / f"{tag}-{hashlib.sha256(key_src.encode()).hexdigest()[:16]}.json"


def _save(path: Path, result: BaseModel) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2))


def llm_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def make_client(provider: str | None = None, model: str | None = None):
    provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower()
    if provider == "gemini":
        return GeminiClient(model)
    raise LLMError(f"Unknown LLM provider '{provider}' (use one of: {', '.join(PROVIDERS)})")


class GeminiClient:
    provider = "gemini"

    def __init__(self, model: str | None = None):
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise LLMError("Set GEMINI_API_KEY in backend/.env (free key: https://aistudio.google.com/apikey)")
        # Our largest calls take ~60s; an overloaded model can hang far longer.
        timeout_s = float(os.getenv("GEMINI_TIMEOUT", "150"))
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        # Newer Flash models are often overloaded on the free tier; fall back in order.
        fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACKS)
        self.models = [self.model] + [m.strip() for m in fallbacks.split(",") if m.strip() and m.strip() != self.model]
        # Spacing between calls. Paid keys need little; free-tier keys need ~12s (per-minute quota).
        self.min_interval = float(os.getenv("GEMINI_MIN_INTERVAL", "2"))
        self._last_call = 0.0
        self.exhausted: set[str] = set()  # models whose daily quota ran out this run
        self.models_used: set[str] = set()

    def list_models(self) -> list[str]:
        return [m.name for m in self.client.models.list()]

    def generate(self, *, system: str, prompt: str, schema: type[T], tag: str) -> T:
        for model in self.models:
            cached = cache_file(model, system, prompt, schema, tag)
            if cached.exists():
                log.info("%s: cached (%s)", tag, model)
                return schema.model_validate_json(cached.read_text())

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.0,
        )
        errors_seen: list[str] = []
        for model in self.models:
            if model in self.exhausted:
                continue
            for attempt in range(ATTEMPTS_PER_MODEL):
                wait = self.min_interval - (time.monotonic() - self._last_call)
                if wait > 0:
                    time.sleep(wait)
                self._last_call = time.monotonic()
                log.info("%s: calling %s (attempt %d, %d chars)", tag, model, attempt + 1, len(prompt))
                try:
                    resp = self.client.models.generate_content(model=model, contents=prompt, config=config)
                except errors.APIError as e:
                    errors_seen.append(f"{model}: {e.code} {(e.message or '')[:100]}")
                    log.warning("%s: %s returned %s: %s", tag, model, e.code, (e.message or "")[:120])
                    if e.code == 429:
                        if is_daily_quota(e):
                            # Retrying won't help until the quota resets; skip this model
                            # for the rest of the run.
                            log.warning("%s: daily quota used up for %s, switching model", tag, model)
                            self.exhausted.add(model)
                            break
                        if attempt + 1 < ATTEMPTS_PER_MODEL:
                            time.sleep(retry_delay(e) or RATE_LIMIT_WAIT)  # per-minute quota
                            continue
                        break
                    if e.code in RETRYABLE and attempt + 1 < ATTEMPTS_PER_MODEL:
                        time.sleep(OVERLOAD_BACKOFF[min(attempt, len(OVERLOAD_BACKOFF) - 1)])
                        continue
                    if e.code in RETRYABLE or e.code == 404:
                        break  # overloaded or unavailable: try the next model
                    raise LLMError(f"Gemini call failed ({e.code}): {e.message}") from e
                except httpx.TimeoutException:
                    errors_seen.append(f"{model}: client timeout")
                    log.warning("%s: %s timed out", tag, model)
                    break

                result = resp.parsed if isinstance(resp.parsed, schema) else None
                if result is None and resp.text:
                    result = schema.model_validate_json(resp.text)
                if result is None:
                    raise LLMError(f"Empty response for {tag}: {resp.candidates}")

                log.info("%s: ok from %s in %.1fs", tag, model, time.monotonic() - self._last_call)
                self.models_used.add(model)
                _save(cache_file(model, system, prompt, schema, tag), result)
                return result

        if self.exhausted and set(self.models) <= self.exhausted:
            raise LLMError(
                "Daily free-tier quota is used up for every configured model "
                f"({', '.join(self.models)}). It resets daily; re-run later and cached results are reused."
            )
        raise LLMError(f"All Gemini models failed for {tag}: " + " | ".join(errors_seen[-4:]))


def is_daily_quota(e: errors.APIError) -> bool:
    """Gemini's 429 body names the quota that was hit, e.g.
    'GenerateRequestsPerDayPerProjectPerModel-FreeTier'."""
    return "perday" in json.dumps(e.details, default=str).lower()


def retry_delay(e: errors.APIError) -> float | None:
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', json.dumps(e.details, default=str))
    return min(float(m.group(1)) + 1, 120) if m else None

