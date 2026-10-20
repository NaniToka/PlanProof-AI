"""Automated unit tests for PlanProof AI application configuration."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings


def test_default_settings_are_valid() -> None:
    """Verify that default settings instantiate with expected values."""
    settings = Settings()
    assert settings.app_name == "PlanProof AI"
    assert settings.app_env == "development"
    assert settings.environment == "development"
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.gemini_timeout_seconds == 30.0
    assert settings.gemini_max_retries == 3
    assert settings.max_guest_count == 2000
    assert settings.min_event_budget_inr == 10000
    assert settings.max_event_budget_inr == 50000000
    assert settings.allowed_cors_origins == ["*"]
    assert settings.crisis_dataset_path == Path("data/crisis_scenarios.csv")
    assert settings.budget_splits_path == Path("data/budget_splits.json")
    assert settings.vendor_checklists_path == Path("data/vendor_checklists.json")


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that environment variables properly override default settings."""
    monkeypatch.setenv("APP_NAME", "Custom Planner")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("MAX_GUEST_COUNT", "1500")
    monkeypatch.setenv("MIN_EVENT_BUDGET_INR", "25000")
    monkeypatch.setenv("MAX_EVENT_BUDGET_INR", "10000000")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "5")
    monkeypatch.setenv("ALLOWED_CORS_ORIGINS", "http://localhost:3000, https://planner.example.com")

    settings = Settings()
    assert settings.app_name == "Custom Planner"
    assert settings.app_env == "staging"
    assert settings.environment == "staging"
    assert settings.max_guest_count == 1500
    assert settings.min_event_budget_inr == 25000
    assert settings.max_event_budget_inr == 10000000
    assert settings.gemini_max_retries == 5
    assert settings.allowed_cors_origins == ["http://localhost:3000", "https://planner.example.com"]


def test_invalid_budget_range_rejected() -> None:
    """Verify error when min_event_budget_inr >= max_event_budget_inr."""
    with pytest.raises(ValidationError) as exc:
        Settings(min_event_budget_inr=50000, max_event_budget_inr=10000)
    assert "must be strictly less than" in str(exc.value)


def test_invalid_retries_rejected() -> None:
    """Verify retry count bounds (0 to 10)."""
    with pytest.raises(ValidationError):
        Settings(gemini_max_retries=-1)
    with pytest.raises(ValidationError):
        Settings(gemini_max_retries=15)


def test_invalid_timeout_rejected() -> None:
    """Verify timeout must be strictly positive."""
    with pytest.raises(ValidationError):
        Settings(gemini_timeout_seconds=0.0)
    with pytest.raises(ValidationError):
        Settings(gemini_timeout_seconds=-5.0)


def test_missing_gemini_key_allowed_for_local() -> None:
    """Verify that settings load normally when GEMINI_API_KEY is not provided."""
    settings = Settings(gemini_api_key=None)
    assert settings.gemini_api_key is None
    assert settings.get_gemini_api_key_value() is None


def test_secret_protection_in_repr_and_str() -> None:
    """Verify that SecretStr masks the raw API key in string/repr outputs."""
    raw_key = "AIzaSySecretTestKey123456"
    settings = Settings(gemini_api_key=SecretStr(raw_key))

    # Masked in repr and str
    assert raw_key not in str(settings)
    assert raw_key not in repr(settings)
    assert raw_key not in repr(settings.gemini_api_key)
    # Only exposed via explicit safe getter
    assert settings.get_gemini_api_key_value() == raw_key


def test_invalid_cors_origin_syntax_rejected() -> None:
    """Verify that malformed CORS origins raise clear validation errors."""
    with pytest.raises(ValidationError) as exc:
        Settings(allowed_cors_origins="not-a-valid-url")
    assert "Invalid CORS origin" in str(exc.value)

    with pytest.raises(ValidationError):
        Settings(allowed_cors_origins="ftp://example.com")


def test_cors_json_string_parsing() -> None:
    """Verify that JSON array string in CORS configuration is parsed correctly."""
    settings = Settings(
        allowed_cors_origins='["https://app.planproof.in", "https://admin.planproof.in"]'
    )
    assert settings.allowed_cors_origins == [
        "https://app.planproof.in",
        "https://admin.planproof.in",
    ]
