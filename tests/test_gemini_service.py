"""Tests for Gemini AI service and API integration in PlanProof AI.

Verifies:
- Safe initialization with and without API keys (zero network calls).
- Structured JSON output parsing and validation against Pydantic models.
- Handling of markdown code block stripping.
- Error handling for malformed JSON, schema mismatches, and empty outputs.
- Timeout handling and bounded exponential backoff retries for transient errors.
- Immediate failure without retry on permanent client errors (400, 401, 403, 404).
- Safe status endpoint /api/v1/ai/status without leaking secrets.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors
from pydantic import BaseModel, Field

from app.config import Settings
from app.main import create_app
from app.services.gemini_service import (
    GeminiInvalidOutputError,
    GeminiNotConfiguredError,
    GeminiProviderError,
    GeminiRateLimitError,
    GeminiService,
    GeminiTimeoutError,
    clean_json_markdown,
)


class DummyEventPlan(BaseModel):
    """Simple schema for structured output testing."""

    title: str = Field(..., min_length=1)
    guest_count: int = Field(..., ge=1)


# ==============================================================================
# Helper Unit Tests
# ==============================================================================


def test_clean_json_markdown() -> None:
    """Verify clean_json_markdown handles raw JSON, json-fenced, and plain-fenced markdown."""
    raw = '{"title": "Wedding", "guest_count": 100}'
    fenced_json = '```json\n{"title": "Wedding", "guest_count": 100}\n```'
    fenced_plain = '```\n{"title": "Wedding", "guest_count": 100}\n```'
    fenced_whitespace = '   ```json\n{"title": "Wedding", "guest_count": 100}\n```   '

    assert clean_json_markdown(raw) == raw
    assert clean_json_markdown(fenced_json) == raw
    assert clean_json_markdown(fenced_plain) == raw
    assert clean_json_markdown(fenced_whitespace) == raw


# ==============================================================================
# Configuration & Initialization Tests
# ==============================================================================


def test_gemini_service_not_configured_when_key_is_none() -> None:
    """Verify that GeminiService is marked unconfigured when gemini_api_key is None."""
    settings = Settings(gemini_api_key=None)
    service = GeminiService(settings=settings)

    assert service.is_configured is False
    assert service._client is None


def test_gemini_service_not_configured_when_key_is_blank() -> None:
    """Verify that GeminiService is unconfigured when gemini_api_key is empty or whitespace."""
    settings = Settings(gemini_api_key="   ")
    service = GeminiService(settings=settings)

    assert service.is_configured is False
    assert service._client is None


def test_gemini_service_configured_with_valid_key() -> None:
    """Verify that GeminiService configures the client when a non-empty key is supplied."""
    settings = Settings(gemini_api_key="mock_secret_key_12345")
    service = GeminiService(settings=settings)

    assert service.is_configured is True
    assert service._client is not None


def test_gemini_service_custom_client_injection() -> None:
    """Verify that an injected client enables is_configured and bypasses default Client init."""
    mock_client = MagicMock()
    service = GeminiService(settings=Settings(gemini_api_key=None), client=mock_client)

    assert service.is_configured is True
    assert service._client is mock_client


@pytest.mark.asyncio
async def test_generate_structured_content_raises_when_unconfigured() -> None:
    """Verify that unconfigured service raises GeminiNotConfiguredError on call."""
    service = GeminiService(settings=Settings(gemini_api_key=None))

    with pytest.raises(GeminiNotConfiguredError) as exc_info:
        await service.generate_structured_content(
            prompt="Plan a wedding",
            response_schema=DummyEventPlan,
        )
    assert "Gemini API key is not configured" in str(exc_info.value)


# ==============================================================================
# Input Validation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_structured_content_rejects_empty_prompt() -> None:
    """Verify that empty or whitespace prompts raise ValueError before calling API."""
    service = GeminiService(settings=Settings(gemini_api_key="mock_key"), client=MagicMock())

    with pytest.raises(ValueError, match="Prompt cannot be empty or blank"):
        await service.generate_structured_content(prompt="", response_schema=DummyEventPlan)

    with pytest.raises(ValueError, match="Prompt cannot be empty or blank"):
        await service.generate_structured_content(prompt="   ", response_schema=DummyEventPlan)


@pytest.mark.asyncio
async def test_generate_structured_content_rejects_excessive_prompt() -> None:
    """Verify that prompt exceeding max_user_text_length raises ValueError."""
    settings = Settings(gemini_api_key="mock_key", max_user_text_length=50)
    service = GeminiService(settings=settings, client=MagicMock())

    long_prompt = "A" * 51
    with pytest.raises(ValueError, match="exceeds maximum limit"):
        await service.generate_structured_content(
            prompt=long_prompt,
            response_schema=DummyEventPlan,
        )


@pytest.mark.asyncio
async def test_generate_structured_content_rejects_invalid_schema_type() -> None:
    """Verify that passing non-BaseModel schema raises TypeError."""
    service = GeminiService(settings=Settings(gemini_api_key="mock_key"), client=MagicMock())

    with pytest.raises(TypeError, match="subclass of pydantic.BaseModel"):
        # Passing dict instead of BaseModel
        await service.generate_structured_content(
            prompt="Valid prompt",
            response_schema=dict,  # type: ignore[arg-type]
        )


# ==============================================================================
# Structured Output & Parsing Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_structured_content_success() -> None:
    """Verify that valid JSON from Gemini is parsed and validated into the Pydantic model."""
    mock_response = MagicMock()
    mock_response.text = '{"title": "Royal Sangeet", "guest_count": 250}'

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    service = GeminiService(
        settings=Settings(gemini_api_key="mock_key"),
        client=mock_client,
    )

    result = await service.generate_structured_content(
        prompt="Generate plan",
        response_schema=DummyEventPlan,
        system_instruction="You are an event planner.",
    )

    assert isinstance(result, DummyEventPlan)
    assert result.title == "Royal Sangeet"
    assert result.guest_count == 250

    # Verify generate_content arguments
    mock_client.aio.models.generate_content.assert_awaited_once()
    kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-2.5-flash"
    assert kwargs["contents"] == "Generate plan"
    assert kwargs["config"].system_instruction == "You are an event planner."
    assert kwargs["config"].response_mime_type == "application/json"


@pytest.mark.asyncio
async def test_generate_structured_content_strips_markdown_fences() -> None:
    """Verify that fenced markdown JSON returned by model is parsed correctly."""
    mock_response = MagicMock()
    mock_response.text = '```json\n{"title": "Haldi Morning", "guest_count": 80}\n```'

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    service = GeminiService(settings=Settings(gemini_api_key="mock_key"), client=mock_client)

    result = await service.generate_structured_content(
        prompt="Generate haldi",
        response_schema=DummyEventPlan,
    )

    assert result.title == "Haldi Morning"
    assert result.guest_count == 80


@pytest.mark.asyncio
async def test_generate_structured_content_with_parsed_attribute() -> None:
    """Verify that pre-parsed response.parsed matching schema is returned directly."""
    expected_model = DummyEventPlan(title="Reception", guest_count=300)
    mock_response = MagicMock()
    mock_response.parsed = expected_model

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    service = GeminiService(settings=Settings(gemini_api_key="mock_key"), client=mock_client)

    result = await service.generate_structured_content(
        prompt="Plan reception",
        response_schema=DummyEventPlan,
    )

    assert result is expected_model


@pytest.mark.asyncio
async def test_generate_structured_content_empty_text_raises() -> None:
    """Verify that empty text from Gemini raises GeminiInvalidOutputError."""
    mock_response = MagicMock()
    mock_response.text = ""

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    service = GeminiService(settings=Settings(gemini_api_key="mock_key"), client=mock_client)

    with pytest.raises(GeminiInvalidOutputError, match="empty or blank text"):
        await service.generate_structured_content(
            prompt="Generate plan",
            response_schema=DummyEventPlan,
        )


@pytest.mark.asyncio
async def test_generate_structured_content_malformed_json_raises() -> None:
    """Verify that malformed JSON raises GeminiInvalidOutputError."""
    mock_response = MagicMock()
    mock_response.text = '{"title": "Broken JSON", "guest_count": '

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    service = GeminiService(settings=Settings(gemini_api_key="mock_key"), client=mock_client)

    with pytest.raises(GeminiInvalidOutputError, match="could not be validated"):
        await service.generate_structured_content(
            prompt="Generate plan",
            response_schema=DummyEventPlan,
        )


@pytest.mark.asyncio
async def test_generate_structured_content_schema_mismatch_raises() -> None:
    """Verify that schema validation failure raises GeminiInvalidOutputError."""
    mock_response = MagicMock()
    # Missing required field 'guest_count'
    mock_response.text = '{"title": "No Guest Count"}'

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    service = GeminiService(settings=Settings(gemini_api_key="mock_key"), client=mock_client)

    with pytest.raises(GeminiInvalidOutputError, match="DummyEventPlan"):
        await service.generate_structured_content(
            prompt="Generate plan",
            response_schema=DummyEventPlan,
        )


# ==============================================================================
# Timeout and Retry Behavior Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_structured_content_timeout_handling() -> None:
    """Verify that request timeout triggers bounded retries and raises GeminiTimeoutError."""
    mock_client = MagicMock()

    async def hanging_call(**_kwargs: object) -> MagicMock:
        await asyncio.sleep(0.05)
        return MagicMock()

    mock_client.aio.models.generate_content = AsyncMock(side_effect=hanging_call)

    # Set very short timeout for fast unit testing
    settings = Settings(
        gemini_api_key="mock_key",
        gemini_timeout_seconds=0.01,
        gemini_max_retries=2,
    )
    service = GeminiService(
        settings=settings,
        client=mock_client,
        retry_backoff_base=0.001,
    )

    with pytest.raises(GeminiTimeoutError, match="timed out"):
        await service.generate_structured_content(
            prompt="Generate plan",
            response_schema=DummyEventPlan,
        )

    # Initial attempt + 2 retries = 3 attempts
    assert mock_client.aio.models.generate_content.await_count == 3


@pytest.mark.asyncio
async def test_generate_structured_content_transient_server_error_retry_success() -> None:
    """Verify that transient 503 error is retried and succeeds on subsequent attempt."""
    mock_client = MagicMock()

    error_503 = errors.APIError(code=503, response_json={"error": "Service Unavailable"})
    success_response = MagicMock()
    success_response.text = '{"title": "Recovered Plan", "guest_count": 120}'

    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=[error_503, success_response],
    )

    service = GeminiService(
        settings=Settings(gemini_api_key="mock_key", gemini_max_retries=2),
        client=mock_client,
        retry_backoff_base=0.001,
    )

    result = await service.generate_structured_content(
        prompt="Generate plan",
        response_schema=DummyEventPlan,
    )

    assert result.title == "Recovered Plan"
    assert result.guest_count == 120
    assert mock_client.aio.models.generate_content.await_count == 2


@pytest.mark.asyncio
async def test_generate_structured_content_rate_limit_retry_success() -> None:
    """Verify that 429 rate limit error is retried with backoff and succeeds."""
    mock_client = MagicMock()

    error_429 = errors.APIError(code=429, response_json={"error": "Rate Limit Exceeded"})
    success_response = MagicMock()
    success_response.text = '{"title": "Rate Limit Recovered", "guest_count": 95}'

    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=[error_429, success_response],
    )

    service = GeminiService(
        settings=Settings(gemini_api_key="mock_key", gemini_max_retries=2),
        client=mock_client,
        retry_backoff_base=0.001,
    )

    result = await service.generate_structured_content(
        prompt="Generate plan",
        response_schema=DummyEventPlan,
    )

    assert result.title == "Rate Limit Recovered"
    assert mock_client.aio.models.generate_content.await_count == 2


@pytest.mark.asyncio
async def test_generate_structured_content_rate_limit_exhausted_raises() -> None:
    """Verify that persistent 429 rate limit raises GeminiRateLimitError after retries."""
    mock_client = MagicMock()
    error_429 = errors.APIError(code=429, response_json={"error": "Rate Limit Exceeded"})

    mock_client.aio.models.generate_content = AsyncMock(side_effect=error_429)

    service = GeminiService(
        settings=Settings(gemini_api_key="mock_key", gemini_max_retries=2),
        client=mock_client,
        retry_backoff_base=0.001,
    )

    with pytest.raises(GeminiRateLimitError, match="rate limit exceeded"):
        await service.generate_structured_content(
            prompt="Generate plan",
            response_schema=DummyEventPlan,
        )

    # 1 initial + 2 retries = 3 attempts
    assert mock_client.aio.models.generate_content.await_count == 3


@pytest.mark.asyncio
async def test_generate_structured_content_permanent_error_no_retry() -> None:
    """Verify that 401 Unauthorized or 400 Bad Request fails immediately without retry."""
    mock_client = MagicMock()
    error_401 = errors.APIError(code=401, response_json={"error": "Invalid API Key"})

    mock_client.aio.models.generate_content = AsyncMock(side_effect=error_401)

    service = GeminiService(
        settings=Settings(gemini_api_key="mock_key", gemini_max_retries=3),
        client=mock_client,
        retry_backoff_base=0.001,
    )

    with pytest.raises(GeminiProviderError, match="status 401"):
        await service.generate_structured_content(
            prompt="Generate plan",
            response_schema=DummyEventPlan,
        )

    # Must NOT retry: call count must be exactly 1
    assert mock_client.aio.models.generate_content.await_count == 1


@pytest.mark.asyncio
async def test_generate_structured_content_network_error_exhausted_raises() -> None:
    """Verify that network transport error triggers retries and raises GeminiProviderError."""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused by upstream host"),
    )

    service = GeminiService(
        settings=Settings(gemini_api_key="mock_key", gemini_max_retries=1),
        client=mock_client,
        retry_backoff_base=0.001,
    )

    with pytest.raises(GeminiProviderError, match="network connection failure"):
        await service.generate_structured_content(
            prompt="Generate plan",
            response_schema=DummyEventPlan,
        )

    assert mock_client.aio.models.generate_content.await_count == 2


# ==============================================================================
# API End-to-End & Health Endpoint Tests
# ==============================================================================


def test_api_ai_status_endpoint_unconfigured() -> None:
    """Verify /api/v1/ai/status reports unconfigured status when gemini_api_key is None."""
    settings = Settings(gemini_api_key=None)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        res = client.get("/api/v1/ai/status")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["model"] == "gemini-2.5-flash"
        assert data["timeout_seconds"] == 30.0
        assert data["max_retries"] == 3
        # Key must not appear
        assert "gemini_api_key" not in data
        assert "api_key" not in data


def test_api_ai_status_endpoint_configured() -> None:
    """Verify /api/v1/ai/status reports configured=true without exposing the secret key."""
    secret_key = "super_secret_production_gemini_key"
    settings = Settings(gemini_api_key=secret_key)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        res = client.get("/api/v1/ai/status")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is True
        assert data["model"] == "gemini-2.5-flash"
        # Secret key must NEVER appear in the response text or headers
        assert secret_key not in res.text
        assert "super_secret" not in res.text


def test_api_ai_exception_handlers_standard_envelope() -> None:
    """Verify that Gemini exceptions map to the agreed standard error response format."""
    app = create_app()

    @app.get("/test-ai-unconfigured")
    async def route_unconfigured() -> None:
        raise GeminiNotConfiguredError("Gemini API key is not configured.")

    @app.get("/test-ai-timeout")
    async def route_timeout() -> None:
        raise GeminiTimeoutError("Gemini request timed out after 30.0 seconds.")

    @app.get("/test-ai-rate-limit")
    async def route_rate_limit() -> None:
        raise GeminiRateLimitError("Gemini rate limit exceeded.")

    @app.get("/test-ai-invalid-output")
    async def route_invalid_output() -> None:
        raise GeminiInvalidOutputError("Gemini output failed schema validation.")

    @app.get("/test-ai-provider-error")
    async def route_provider_error() -> None:
        raise GeminiProviderError("Upstream Gemini server error.")

    with TestClient(app) as client:
        # 1. Not configured -> 503
        res1 = client.get("/test-ai-unconfigured")
        assert res1.status_code == 503
        d1 = res1.json()
        assert d1["error"]["code"] == "AI_NOT_CONFIGURED"
        assert d1["error"]["message"] == "Gemini API key is not configured."
        assert d1["error"]["details"] is None

        # 2. Timeout -> 504
        res2 = client.get("/test-ai-timeout")
        assert res2.status_code == 504
        d2 = res2.json()
        assert d2["error"]["code"] == "AI_TIMEOUT"
        assert d2["error"]["details"] is None

        # 3. Rate Limit -> 429
        res3 = client.get("/test-ai-rate-limit")
        assert res3.status_code == 429
        d3 = res3.json()
        assert d3["error"]["code"] == "AI_RATE_LIMIT"
        assert d3["error"]["details"] is None

        # 4. Invalid Output -> 502
        res4 = client.get("/test-ai-invalid-output")
        assert res4.status_code == 502
        d4 = res4.json()
        assert d4["error"]["code"] == "AI_OUTPUT_VALIDATION_ERROR"
        assert d4["error"]["details"] is None

        # 5. Provider Error -> 502
        res5 = client.get("/test-ai-provider-error")
        assert res5.status_code == 502
        d5 = res5.json()
        assert d5["error"]["code"] == "AI_PROVIDER_ERROR"
        assert d5["error"]["details"] is None
