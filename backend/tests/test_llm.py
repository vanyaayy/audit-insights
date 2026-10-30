"""Retry/fallback behaviour of the Gemini wrapper, with the network call faked."""

import pytest
from google.genai import errors

from app import llm
from app.schemas import ExtractionOutput


def _api_error(code: int, message: str, details: list | None = None) -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "message": message, "details": details or []}})


DAILY = _api_error(429, "You exceeded your current quota", [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
])
PER_MINUTE = _api_error(429, "You exceeded your current quota", [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"},
])
OVERLOADED = _api_error(503, "This model is currently experiencing high demand.")


class FakeResponse:
    parsed = ExtractionOutput(findings=[])
    text = '{"findings": []}'


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "model-a")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "model-b,model-c")
    monkeypatch.setenv("GEMINI_MIN_INTERVAL", "0")
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    sleeps: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    c = llm.GeminiClient()
    c.sleeps = sleeps
    return c


def _script(client, outcomes: dict[str, list]):
    """Each model returns/raises its listed outcomes in order."""
    calls: list[str] = []

    def generate_content(model, contents, config):
        calls.append(model)
        outcome = outcomes[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client.client.models.generate_content = generate_content
    return calls


def _generate(client, tag="t"):
    return client.generate(system="s", prompt="p", schema=ExtractionOutput, tag=tag)


def test_daily_quota_skips_model_immediately_and_for_later_calls(client):
    calls = _script(client, {"model-a": [DAILY], "model-b": [FakeResponse(), FakeResponse()]})
    _generate(client, "one")
    _generate(client, "two")
    assert calls == ["model-a", "model-b", "model-b"]
    assert client.exhausted == {"model-a"}
    assert client.sleeps == []


def test_per_minute_quota_waits_using_retry_delay(client):
    calls = _script(client, {"model-a": [PER_MINUTE, FakeResponse()]})
    _generate(client)
    assert calls == ["model-a", "model-a"]
    assert client.sleeps == [8.0]


def test_overloaded_model_retries_then_falls_back(client):
    calls = _script(client, {"model-a": [OVERLOADED] * llm.ATTEMPTS_PER_MODEL, "model-b": [FakeResponse()]})
    _generate(client)
    assert calls == ["model-a"] * llm.ATTEMPTS_PER_MODEL + ["model-b"]
    assert client.sleeps == [10, 30, 60]  # waits out "high demand" before switching model
    assert client.models_used == {"model-b"}


def test_all_models_out_of_daily_quota_gives_clear_error(client):
    _script(client, {m: [DAILY] for m in ("model-a", "model-b", "model-c")})
    with pytest.raises(llm.LLMError, match="Daily free-tier quota"):
        _generate(client)


def test_successful_result_is_cached(client):
    calls = _script(client, {"model-a": [FakeResponse()]})
    _generate(client)
    _generate(client)
    assert calls == ["model-a"]
