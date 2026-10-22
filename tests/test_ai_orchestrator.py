"""Comprehensive tests for AI operation modes, deterministic fallbacks, and output validation.

Verifies:
1. AI_MODE settings parsing, defaults, allowed modes (auto, demo, gemini), and startup validation.
2. AIResultEnvelope schema integrity, status/source validation, extra field rejection, and path sanitization.
3. Pure deterministic Demo Mode (never invokes live Gemini client, returns illustrative fixtures).
4. Strict Gemini Mode (requires Gemini; no silent fallback on failure or missing key).
5. Auto Mode (Gemini when available; permitted deterministic fallback when offline or unconfigured).
6. Feature-specific fallback interfaces (0-arg sync, 1-arg sync, async, protocol classes, exception handling).
7. Minimal demo fixtures data integrity (wedding timeline, birthday timeline, risks, crisis, family council).
8. API endpoints integration (/api/v1/ai/status, /api/v1/plan/timeline, /api/v1/plan/risks).
9. Security: secrets and filesystem paths never leak in envelope message or warnings.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.config import AIMode, ConfigurationError, Settings
from app.main import create_app
from app.schemas import (
    AIResultEnvelope,
    AIResultSource,
    AIResultStatus,
    AITask,
    CrisisRecoveryPlan,
    EventPlanRequest,
    EventTimelineResponse,
    EventType,
    FamilyCouncilResponse,
    PreMortemRisk,
)
from app.services.ai_orchestrator import AIOrchestrator, FallbackProvider
from app.services.demo_fixtures import (
    get_demo_birthday_timeline,
    get_demo_crisis_recovery,
    get_demo_event_risks,
    get_demo_family_council,
    get_demo_timeline,
    get_demo_wedding_timeline,
)
from app.services.fallback_service import (
    generate_deterministic_crisis_recovery,
    generate_deterministic_family_council,
    generate_deterministic_risks,
    generate_deterministic_timeline,
)
from app.services.gemini_service import (
    GeminiInvalidOutputError,
    GeminiNotConfiguredError,
    GeminiRateLimitError,
    GeminiService,
    GeminiTimeoutError,
)


class DummyOutputSchema(BaseModel):
    """Simple schema for orchestration testing."""

    summary: str = Field(..., min_length=1)
    score: int = Field(..., ge=0)


# ==============================================================================
# 1. AI_MODE Configuration & Startup Validation Tests
# ==============================================================================


def test_ai_mode_default_is_auto() -> None:
    """Verify that the default AI_MODE is 'auto'."""
    settings = Settings()
    assert settings.ai_mode == AIMode.AUTO
    assert settings.ai_mode.value == "auto"


def test_ai_mode_parsing_valid_values() -> None:
    """Verify that Settings parses case-insensitive valid AI_MODE values."""
    assert Settings(ai_mode="auto").ai_mode == AIMode.AUTO
    assert Settings(ai_mode="AUTO").ai_mode == AIMode.AUTO
    assert Settings(ai_mode="demo").ai_mode == AIMode.DEMO
    assert Settings(ai_mode="DEMO").ai_mode == AIMode.DEMO
    assert Settings(ai_mode="gemini").ai_mode == AIMode.GEMINI
    assert Settings(ai_mode="GEMINI").ai_mode == AIMode.GEMINI


def test_ai_mode_invalid_value_rejected() -> None:
    """Verify that invalid AI_MODE values raise ValueError."""
    with pytest.raises(ValueError, match="Invalid AI_MODE 'unsupported_mode'"):
        Settings(ai_mode="unsupported_mode")


def test_app_startup_validates_ai_mode() -> None:
    """Verify application startup verifies configured AI_MODE."""
    # Valid modes start cleanly
    for mode in (AIMode.AUTO, AIMode.DEMO, AIMode.GEMINI):
        settings = Settings(ai_mode=mode)
        app = create_app(settings=settings)
        with TestClient(app) as client:
            res = client.get("/health")
            assert res.status_code == 200

    # If an unsupported mode somehow bypassed Settings, lifespan rejects it
    bad_settings = Settings()
    object.__setattr__(bad_settings, "ai_mode", "corrupted_mode")
    bad_app = create_app(settings=bad_settings)
    with pytest.raises(ConfigurationError, match="Unsupported AI_MODE"):
        with TestClient(bad_app):
            pass


# ==============================================================================
# 2. AIResultEnvelope Schema Integrity Tests
# ==============================================================================


def test_ai_result_envelope_success_validation() -> None:
    """Verify valid envelope creation for success status."""
    dummy = DummyOutputSchema(summary="All good", score=10)
    envelope = AIResultEnvelope[DummyOutputSchema](
        status=AIResultStatus.SUCCESS,
        source=AIResultSource.GEMINI,
        data=dummy,
        message="Generated successfully",
        warnings=[],
    )
    assert envelope.status == AIResultStatus.SUCCESS
    assert envelope.source == AIResultSource.GEMINI
    assert envelope.data.summary == "All good"
    assert envelope.data.score == 10
    assert envelope.warnings == []


def test_ai_result_envelope_fallback_validation() -> None:
    """Verify valid envelope creation for fallback status."""
    dummy = DummyOutputSchema(summary="Fallback rule", score=5)
    envelope = AIResultEnvelope[DummyOutputSchema](
        status=AIResultStatus.FALLBACK,
        source=AIResultSource.DETERMINISTIC,
        data=dummy,
        message="Served from fallback",
        warnings=["Gemini unavailable"],
    )
    assert envelope.status == AIResultStatus.FALLBACK
    assert envelope.source == AIResultSource.DETERMINISTIC
    assert envelope.data == dummy


def test_ai_result_envelope_unavailable_validation() -> None:
    """Verify valid envelope creation for unavailable status with null data."""
    envelope = AIResultEnvelope[DummyOutputSchema](
        status=AIResultStatus.UNAVAILABLE,
        source=AIResultSource.GEMINI,
        data=None,
        message="API unavailable",
        warnings=["No key configured"],
    )
    assert envelope.status == AIResultStatus.UNAVAILABLE
    assert envelope.data is None


def test_ai_result_envelope_rejects_missing_data_for_success_and_fallback() -> None:
    """Verify that status=success or fallback requires data to not be None."""
    with pytest.raises(ValueError, match="data cannot be None when status is 'success'"):
        AIResultEnvelope[DummyOutputSchema](
            status=AIResultStatus.SUCCESS,
            source=AIResultSource.GEMINI,
            data=None,
        )

    with pytest.raises(ValueError, match="data cannot be None when status is 'fallback'"):
        AIResultEnvelope[DummyOutputSchema](
            status=AIResultStatus.FALLBACK,
            source=AIResultSource.DETERMINISTIC,
            data=None,
        )


def test_ai_result_envelope_rejects_data_for_unavailable() -> None:
    """Verify that status=unavailable forbids non-None data."""
    dummy = DummyOutputSchema(summary="Stale data", score=0)
    with pytest.raises(ValueError, match="data must be None when status is 'unavailable'"):
        AIResultEnvelope[DummyOutputSchema](
            status=AIResultStatus.UNAVAILABLE,
            source=AIResultSource.GEMINI,
            data=dummy,
        )


def test_ai_result_envelope_forbids_extra_fields() -> None:
    """Verify strict schema forbids unexpected extra fields."""
    dummy = DummyOutputSchema(summary="Check", score=1)
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        AIResultEnvelope[DummyOutputSchema](
            status=AIResultStatus.SUCCESS,
            source=AIResultSource.GEMINI,
            data=dummy,
            extra_field="malicious_payload",  # type: ignore[call-arg]
        )


def test_ai_result_envelope_sanitizes_paths() -> None:
    """Verify envelope automatically sanitizes filesystem paths in message and warnings."""
    dummy = DummyOutputSchema(summary="Clean", score=10)
    envelope = AIResultEnvelope[DummyOutputSchema](
        status=AIResultStatus.SUCCESS,
        source=AIResultSource.DEMO,
        data=dummy,
        message="Failed opening /Users/tokanani/secrets/config.json",
        warnings=[
            "Checked path C:\\Windows\\System32\\driver.sys",
            "Checked /var/log/app/secrets.log",
        ],
    )
    assert "/Users/tokanani" not in envelope.message
    assert "config.json" in envelope.message
    assert "C:\\Windows\\System32" not in envelope.warnings[0]
    assert "driver.sys" in envelope.warnings[0]
    assert "/var/log/app" not in envelope.warnings[1]
    assert "secrets.log" in envelope.warnings[1]


# ==============================================================================
# 3. Demo Mode Behavior Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_demo_mode_never_calls_gemini() -> None:
    """Verify that in demo mode, Gemini client is NEVER invoked."""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock()

    settings = Settings(ai_mode=AIMode.DEMO, gemini_api_key="dummy_key")
    gemini_svc = GeminiService(settings=settings, client=mock_client)
    orchestrator = AIOrchestrator(settings=settings, gemini_service=gemini_svc)

    result = await orchestrator.orchestrate(
        task=AITask.EVENT_TIMELINE,
        response_schema=EventTimelineResponse,
        prompt="Plan a wedding timeline",
    )

    # Gemini client must NOT have been called
    mock_client.aio.models.generate_content.assert_not_called()
    assert result.status == AIResultStatus.SUCCESS
    assert result.source == AIResultSource.DEMO
    assert isinstance(result.data, EventTimelineResponse)
    assert len(result.data.planning_milestones) > 0
    assert any("Illustrative Demo" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_demo_mode_with_custom_provider() -> None:
    """Verify custom demo provider is used in demo mode."""
    settings = Settings(ai_mode=AIMode.DEMO)
    orchestrator = AIOrchestrator(settings=settings)

    custom_demo = DummyOutputSchema(summary="Custom Demo Story", score=99)
    result = await orchestrator.orchestrate(
        task="custom_task",
        response_schema=DummyOutputSchema,
        demo_provider=lambda: custom_demo,
    )

    assert result.status == AIResultStatus.SUCCESS
    assert result.source == AIResultSource.DEMO
    assert result.data == custom_demo


@pytest.mark.asyncio
async def test_demo_mode_unregistered_task_returns_unavailable() -> None:
    """Verify unregistered task in demo mode without fallback returns unavailable."""
    settings = Settings(ai_mode=AIMode.DEMO)
    orchestrator = AIOrchestrator(settings=settings)

    result = await orchestrator.orchestrate(
        task="unknown_unregistered_task",
        response_schema=DummyOutputSchema,
    )

    assert result.status == AIResultStatus.UNAVAILABLE
    assert result.source == AIResultSource.DEMO
    assert result.data is None
    assert "No demonstration fixture or fallback" in (result.message or "")


# ==============================================================================
# 4. Strict Gemini Mode Behavior Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_gemini_mode_unconfigured_returns_unavailable_without_fallback() -> None:
    """Verify gemini mode returns unavailable and does NOT silently fall back when unconfigured."""
    settings = Settings(ai_mode=AIMode.GEMINI, gemini_api_key=None)
    orchestrator = AIOrchestrator(settings=settings)

    fallback_called = False

    def sample_fallback() -> DummyOutputSchema:
        nonlocal fallback_called
        fallback_called = True
        return DummyOutputSchema(summary="Fallback", score=1)

    result = await orchestrator.orchestrate(
        task="sample_task",
        response_schema=DummyOutputSchema,
        prompt="Tell me something",
        fallback=sample_fallback,
    )

    assert fallback_called is False
    assert result.status == AIResultStatus.UNAVAILABLE
    assert result.source == AIResultSource.GEMINI
    assert result.data is None
    assert "GEMINI_API_KEY is not configured" in (result.message or "")


@pytest.mark.asyncio
async def test_gemini_mode_success() -> None:
    """Verify gemini mode returns success when Gemini responds with valid structured JSON."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"summary": "Gemini generated wedding plan", "score": 95}'
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    settings = Settings(ai_mode=AIMode.GEMINI, gemini_api_key="valid_key")
    gemini_svc = GeminiService(settings=settings, client=mock_client)
    orchestrator = AIOrchestrator(settings=settings, gemini_service=gemini_svc)

    result = await orchestrator.orchestrate(
        task="plan_summary",
        response_schema=DummyOutputSchema,
        prompt="Generate plan summary",
    )

    assert result.status == AIResultStatus.SUCCESS
    assert result.source == AIResultSource.GEMINI
    assert result.data.summary == "Gemini generated wedding plan"
    assert result.data.score == 95
    assert result.warnings == []


@pytest.mark.asyncio
async def test_gemini_mode_failure_does_not_fall_back() -> None:
    """Verify gemini mode does not fall back when Gemini encounters a provider error."""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=TimeoutError("Request timed out")
    )

    settings = Settings(
        ai_mode=AIMode.GEMINI,
        gemini_api_key="valid_key",
        gemini_timeout_seconds=0.1,
        gemini_max_retries=0,
    )
    gemini_svc = GeminiService(settings=settings, client=mock_client)
    orchestrator = AIOrchestrator(settings=settings, gemini_service=gemini_svc)

    fallback_called = False

    def sample_fallback() -> DummyOutputSchema:
        nonlocal fallback_called
        fallback_called = True
        return DummyOutputSchema(summary="Fallback", score=1)

    result = await orchestrator.orchestrate(
        task="plan_summary",
        response_schema=DummyOutputSchema,
        prompt="Generate plan summary",
        fallback=sample_fallback,
    )

    # In gemini mode, fallback MUST NOT be called!
    assert fallback_called is False
    assert result.status == AIResultStatus.UNAVAILABLE
    assert result.source == AIResultSource.GEMINI
    assert result.data is None
    assert "timed out" in (result.message or "").lower()


# ==============================================================================
# 5. Auto Mode Behavior Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_auto_mode_uses_gemini_when_available() -> None:
    """Verify auto mode uses Gemini when configured and available."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"summary": "Auto Gemini output", "score": 88}'
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    settings = Settings(ai_mode=AIMode.AUTO, gemini_api_key="valid_key")
    gemini_svc = GeminiService(settings=settings, client=mock_client)
    orchestrator = AIOrchestrator(settings=settings, gemini_service=gemini_svc)

    fallback_called = False

    def dummy_fallback() -> DummyOutputSchema:
        nonlocal fallback_called
        fallback_called = True
        return DummyOutputSchema(summary="Fallback", score=0)

    result = await orchestrator.orchestrate(
        task="auto_task",
        response_schema=DummyOutputSchema,
        prompt="Tell me a story",
        fallback=dummy_fallback,
    )

    assert fallback_called is False
    assert result.status == AIResultStatus.SUCCESS
    assert result.source == AIResultSource.GEMINI
    assert result.data.summary == "Auto Gemini output"


@pytest.mark.asyncio
async def test_auto_mode_falls_back_when_gemini_unconfigured() -> None:
    """Verify auto mode uses fallback when gemini key is not configured."""
    settings = Settings(ai_mode=AIMode.AUTO, gemini_api_key=None)
    orchestrator = AIOrchestrator(settings=settings)

    def dummy_fallback() -> DummyOutputSchema:
        return DummyOutputSchema(summary="Unconfigured fallback", score=42)

    result = await orchestrator.orchestrate(
        task="auto_task",
        response_schema=DummyOutputSchema,
        prompt="Prompt",
        fallback=dummy_fallback,
    )

    assert result.status == AIResultStatus.FALLBACK
    assert result.source == AIResultSource.DETERMINISTIC
    assert result.data.summary == "Unconfigured fallback"
    assert any("not configured" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_auto_mode_falls_back_when_gemini_fails() -> None:
    """Verify auto mode uses fallback when live Gemini call fails with timeout or rate limit."""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=TimeoutError("Connection timed out")
    )

    settings = Settings(
        ai_mode=AIMode.AUTO,
        gemini_api_key="valid_key",
        gemini_timeout_seconds=0.1,
        gemini_max_retries=0,
    )
    gemini_svc = GeminiService(settings=settings, client=mock_client)
    orchestrator = AIOrchestrator(settings=settings, gemini_service=gemini_svc)

    def dummy_fallback() -> DummyOutputSchema:
        return DummyOutputSchema(summary="Fallback on failure", score=77)

    result = await orchestrator.orchestrate(
        task="auto_task",
        response_schema=DummyOutputSchema,
        prompt="Prompt",
        fallback=dummy_fallback,
    )

    assert result.status == AIResultStatus.FALLBACK
    assert result.source == AIResultSource.DETERMINISTIC
    assert result.data.summary == "Fallback on failure"
    assert any("unavailable" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_auto_mode_without_fallback_returns_unavailable() -> None:
    """Verify auto mode returns unavailable if Gemini fails and NO fallback is registered."""
    settings = Settings(ai_mode=AIMode.AUTO, gemini_api_key=None)
    orchestrator = AIOrchestrator(settings=settings)

    # Task with no fallback registered
    result = await orchestrator.orchestrate(
        task="unsupported_task_without_fallback",
        response_schema=DummyOutputSchema,
        prompt="Prompt",
        fallback=None,
    )

    assert result.status == AIResultStatus.UNAVAILABLE
    assert result.source == AIResultSource.GEMINI
    assert result.data is None
    assert "no deterministic fallback is registered" in (result.message or "")


# ==============================================================================
# 6. Feature-Specific Fallback Interface Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_fallback_zero_arg_callable() -> None:
    """Verify zero-argument synchronous fallback callable works."""
    settings = Settings(ai_mode=AIMode.AUTO, gemini_api_key=None)
    orchestrator = AIOrchestrator(settings=settings)

    def zero_arg() -> DummyOutputSchema:
        return DummyOutputSchema(summary="Zero Arg", score=10)

    res = await orchestrator.orchestrate(
        task="test",
        response_schema=DummyOutputSchema,
        fallback=zero_arg,
    )
    assert res.status == AIResultStatus.FALLBACK
    assert res.data.summary == "Zero Arg"


@pytest.mark.asyncio
async def test_fallback_one_arg_callable_with_request_data() -> None:
    """Verify one-argument fallback receives request_data."""
    settings = Settings(ai_mode=AIMode.AUTO, gemini_api_key=None)
    orchestrator = AIOrchestrator(settings=settings)

    def one_arg(req: dict) -> DummyOutputSchema:
        return DummyOutputSchema(summary=f"Processed {req['city']}", score=req["count"])

    res = await orchestrator.orchestrate(
        task="test",
        response_schema=DummyOutputSchema,
        request_data={"city": "Jaipur", "count": 250},
        fallback=one_arg,
    )
    assert res.status == AIResultStatus.FALLBACK
    assert res.data.summary == "Processed Jaipur"
    assert res.data.score == 250


@pytest.mark.asyncio
async def test_fallback_async_callable() -> None:
    """Verify async fallback callable is properly awaited."""
    settings = Settings(ai_mode=AIMode.AUTO, gemini_api_key=None)
    orchestrator = AIOrchestrator(settings=settings)

    async def async_fallback(req: Any) -> DummyOutputSchema:
        return DummyOutputSchema(summary="Async Result", score=50)

    res = await orchestrator.orchestrate(
        task="test",
        response_schema=DummyOutputSchema,
        fallback=async_fallback,
    )
    assert res.status == AIResultStatus.FALLBACK
    assert res.data.summary == "Async Result"


@pytest.mark.asyncio
async def test_fallback_provider_class() -> None:
    """Verify class implementing FallbackProvider protocol works."""

    class CustomClassFallback:
        def __init__(self, prefix: str) -> None:
            self.prefix = prefix

        def __call__(self, req: Any = None) -> DummyOutputSchema:
            return DummyOutputSchema(summary=f"{self.prefix}: Done", score=100)

    settings = Settings(ai_mode=AIMode.AUTO, gemini_api_key=None)
    orchestrator = AIOrchestrator(settings=settings)

    handler = CustomClassFallback(prefix="ClassProvider")
    res = await orchestrator.orchestrate(
        task="test",
        response_schema=DummyOutputSchema,
        fallback=handler,
    )
    assert res.status == AIResultStatus.FALLBACK
    assert res.data.summary == "ClassProvider: Done"


@pytest.mark.asyncio
async def test_fallback_exception_handling_safe_envelope() -> None:
    """Verify fallback exceptions return unavailable envelope without leaking paths or crashing."""
    settings = Settings(ai_mode=AIMode.AUTO, gemini_api_key=None)
    orchestrator = AIOrchestrator(settings=settings)

    def crashing_fallback(_req: Any) -> DummyOutputSchema:
        raise RuntimeError("Disk failure at /Users/tokanani/secret/data.db")

    res = await orchestrator.orchestrate(
        task="test",
        response_schema=DummyOutputSchema,
        fallback=crashing_fallback,
    )
    assert res.status == AIResultStatus.UNAVAILABLE
    assert res.source == AIResultSource.DETERMINISTIC
    assert res.data is None
    assert "/Users/tokanani" not in (res.message or "")
    assert "data.db" in (res.message or "")


# ==============================================================================
# 7. Demo Fixtures & Deterministic Fallbacks Domain Integrity Tests
# ==============================================================================


def test_demo_timeline_fixtures_integrity() -> None:
    """Verify built-in demo timelines pass schema validation."""
    wedding_tl = get_demo_wedding_timeline()
    assert isinstance(wedding_tl, EventTimelineResponse)
    assert len(wedding_tl.planning_milestones) >= 4
    assert len(wedding_tl.run_sheet) >= 4
    assert all("[Illustrative Demo]" in m.description for m in wedding_tl.planning_milestones)

    birthday_tl = get_demo_birthday_timeline()
    assert isinstance(birthday_tl, EventTimelineResponse)
    assert len(birthday_tl.planning_milestones) >= 3

    assert get_demo_timeline(EventType.WEDDING) is not None
    assert get_demo_timeline(EventType.BIRTHDAY) is not None


def test_demo_event_risks_integrity() -> None:
    """Verify built-in demo event risks pass schema validation."""
    risks = get_demo_event_risks(EventType.WEDDING)
    assert isinstance(risks, list)
    assert len(risks) >= 3
    for r in risks:
        assert isinstance(r, PreMortemRisk)
        assert 0.0 <= r.probability <= 1.0
        assert "[Illustrative Demo]" in r.risk_description


def test_demo_crisis_recovery_integrity() -> None:
    """Verify built-in demo crisis recovery plan passes schema validation."""
    crisis = get_demo_crisis_recovery()
    assert isinstance(crisis, CrisisRecoveryPlan)
    assert crisis.severity in (1, 2, 3)
    assert len(crisis.whatsapp_message_drafts) >= 2
    assert all("[Illustrative Demo]" in m.message_text for m in crisis.whatsapp_message_drafts)


def test_demo_family_council_integrity() -> None:
    """Verify built-in demo family council review passes schema validation."""
    fc = get_demo_family_council()
    assert isinstance(fc, FamilyCouncilResponse)
    assert fc.budget_holder.persona_name
    assert fc.elder_relative.persona_name
    assert fc.picky_friend.persona_name
    assert fc.parent_with_kids.persona_name
    assert "[Illustrative Demo]" in fc.compromise.agreed_plan


def test_deterministic_fallbacks_domain_generation() -> None:
    """Verify deterministic fallback generators produce compliant schemas."""
    plan_req = EventPlanRequest(
        event_type=EventType.WEDDING,
        guest_count=500,
        total_budget_inr=3500000,
        city_tier="metro",
        city="Mumbai",
    )

    tl = generate_deterministic_timeline(plan_req)
    assert isinstance(tl, EventTimelineResponse)
    assert len(tl.planning_milestones) >= 4
    assert len(tl.run_sheet) >= 4

    risks = generate_deterministic_risks(plan_req)
    assert len(risks) >= 4
    assert any("traffic" in r.risk_description.lower() for r in risks)

    crisis = generate_deterministic_crisis_recovery("rain", severity=3)
    assert isinstance(crisis, CrisisRecoveryPlan)
    assert len(crisis.whatsapp_message_drafts) >= 2

    fc = generate_deterministic_family_council(plan_req)
    assert isinstance(fc, FamilyCouncilResponse)
    assert "Mumbai" in fc.compromise.agreed_plan


# ==============================================================================
# 8. API Endpoint Integration Tests
# ==============================================================================


def test_api_ai_status_reflects_ai_mode() -> None:
    """Verify /api/v1/ai/status returns current ai_mode."""
    for mode in ("auto", "demo", "gemini"):
        app = create_app(settings=Settings(ai_mode=mode))
        with TestClient(app) as client:
            res = client.get("/api/v1/ai/status")
            assert res.status_code == 200
            data = res.json()
            assert data["mode"] == mode


def test_api_plan_timeline_demo_mode() -> None:
    """Verify POST /api/v1/plan/timeline in demo mode returns demo envelope."""
    app = create_app(settings=Settings(ai_mode=AIMode.DEMO))
    payload = {
        "event_type": "wedding",
        "guest_count": 350,
        "total_budget_inr": 2500000,
        "city_tier": "metro",
        "city": "Hyderabad",
    }

    with TestClient(app) as client:
        res = client.post("/api/v1/plan/timeline", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["source"] == "demo"
        assert data["data"] is not None
        assert len(data["data"]["planning_milestones"]) > 0
        assert any("Illustrative Demo" in w for w in data["warnings"])


def test_api_plan_timeline_auto_mode_offline_fallback() -> None:
    """Verify POST /api/v1/plan/timeline in auto mode without API key uses deterministic fallback."""
    app = create_app(settings=Settings(ai_mode=AIMode.AUTO, gemini_api_key=None))
    payload = {
        "event_type": "birthday",
        "guest_count": 60,
        "total_budget_inr": 75000,
        "city_tier": "tier2",
        "city": "Mysore",
    }

    with TestClient(app) as client:
        res = client.post("/api/v1/plan/timeline", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "fallback"
        assert data["source"] == "deterministic"
        assert data["data"] is not None
        assert len(data["data"]["planning_milestones"]) > 0
        assert any("deterministic fallback" in w for w in data["warnings"])


def test_api_plan_timeline_gemini_mode_unconfigured() -> None:
    """Verify POST /api/v1/plan/timeline in gemini mode without key returns unavailable."""
    app = create_app(settings=Settings(ai_mode=AIMode.GEMINI, gemini_api_key=None))
    payload = {
        "event_type": "wedding",
        "guest_count": 200,
        "total_budget_inr": 1500000,
        "city_tier": "tier3",
        "city": "Udaipur",
    }

    with TestClient(app) as client:
        res = client.post("/api/v1/plan/timeline", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "unavailable"
        assert data["source"] == "gemini"
        assert data["data"] is None
        assert "GEMINI_API_KEY is not configured" in data["message"]


def test_api_plan_risks_demo_mode() -> None:
    """Verify POST /api/v1/plan/risks in demo mode returns illustrative risks."""
    app = create_app(settings=Settings(ai_mode=AIMode.DEMO))
    payload = {
        "event_type": "wedding",
        "guest_count": 400,
        "total_budget_inr": 3000000,
        "city_tier": "metro",
        "city": "Delhi",
    }

    with TestClient(app) as client:
        res = client.post("/api/v1/plan/risks", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["source"] == "demo"
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 3
