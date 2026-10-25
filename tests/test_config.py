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


def test_supabase_settings_default_to_none() -> None:
    """Verify that optional Supabase and database settings default to None."""
    settings = Settings()
    assert settings.supabase_url is None
    assert settings.supabase_anon_key is None
    assert settings.supabase_jwt_secret is None
    assert settings.database_url is None
    assert settings.is_supabase_configured is False
    assert settings.is_database_configured is False
    assert settings.get_supabase_anon_key_value() is None
    assert settings.get_supabase_jwt_secret_value() is None
    assert settings.get_database_url_value() is None


def test_supabase_settings_loaded_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that Supabase and PostgreSQL settings load properly from environment variables."""
    test_url = "https://my-test-proj.supabase.co"
    test_anon = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-anon-key"
    test_jwt_secret = "super-secret-jwt-signing-key-12345"
    test_db = "postgresql://postgres:dbpass@localhost:5432/testdb"

    monkeypatch.setenv("SUPABASE_URL", test_url)
    monkeypatch.setenv("SUPABASE_ANON_KEY", test_anon)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", test_jwt_secret)
    monkeypatch.setenv("DATABASE_URL", test_db)

    settings = Settings()
    assert settings.supabase_url == test_url
    assert settings.is_supabase_configured is True
    assert settings.is_database_configured is True
    assert settings.get_supabase_anon_key_value() == test_anon
    assert settings.get_supabase_jwt_secret_value() == test_jwt_secret
    assert settings.get_database_url_value() == test_db


def test_supabase_secret_masking_in_repr_and_str() -> None:
    """Verify that sensitive Supabase keys and database URLs are masked in repr and str."""
    anon_key = "sensitive-anon-key-123"
    jwt_secret = "sensitive-jwt-secret-456"
    db_pass = "top-secret-db-password"
    db_url = f"postgresql://postgres:{db_pass}@db.supabase.co:5432/postgres"

    settings = Settings(
        supabase_anon_key=SecretStr(anon_key),
        supabase_jwt_secret=SecretStr(jwt_secret),
        database_url=SecretStr(db_url),
    )

    settings_repr = repr(settings)
    settings_str = str(settings)

    # Sensitive values must never appear in repr or str
    assert anon_key not in settings_repr
    assert jwt_secret not in settings_repr
    assert db_pass not in settings_repr
    assert anon_key not in settings_str
    assert jwt_secret not in settings_str
    assert db_pass not in settings_str


def test_empty_supabase_strings_handled_as_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that blank or whitespace-only Supabase env vars are treated as None."""
    monkeypatch.setenv("SUPABASE_URL", "   ")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", " ")
    monkeypatch.setenv("DATABASE_URL", "")

    settings = Settings()
    assert settings.supabase_url is None
    assert settings.supabase_anon_key is None
    assert settings.supabase_jwt_secret is None
    assert settings.database_url is None
    assert settings.is_supabase_configured is False
    assert settings.is_database_configured is False


def test_invalid_supabase_url_rejected() -> None:
    """Verify that non-HTTP/HTTPS URLs for SUPABASE_URL raise validation errors."""
    with pytest.raises(ValidationError) as exc:
        Settings(supabase_url="not-a-valid-url")
    assert "Invalid SUPABASE_URL" in str(exc.value)

    with pytest.raises(ValidationError):
        Settings(supabase_url="ftp://supabase.co")


def test_app_starts_without_supabase_configured() -> None:
    """Verify that FastAPI application initializes and responds normally without Supabase."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(settings=Settings())
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


def test_jwt_auth_defaults_and_resolution() -> None:
    """Verify defaults for JWT audience, algorithms allowlist, and derived JWKS/issuer."""
    settings = Settings()
    assert settings.supabase_jwt_audience == "authenticated"
    assert settings.supabase_jwt_algorithms == ["HS256", "RS256", "ES256"]
    assert settings.supabase_jwt_public_key is None
    assert settings.supabase_jwks_url is None
    assert settings.supabase_jwt_issuer is None
    assert settings.allow_guest_mode is True
    assert settings.is_auth_configured is False
    assert settings.resolved_jwks_url is None
    assert settings.resolved_jwt_issuer is None


def test_jwt_auth_derived_from_supabase_url() -> None:
    """Verify JWKS URL and issuer are properly derived from supabase_url."""
    settings = Settings(supabase_url="https://xyzproject.supabase.co")
    assert settings.is_auth_configured is True
    assert settings.resolved_jwks_url == "https://xyzproject.supabase.co/auth/v1/.well-known/jwks.json"
    assert settings.resolved_jwt_issuer == "https://xyzproject.supabase.co/auth/v1"


def test_jwt_auth_explicit_overrides() -> None:
    """Verify explicit JWKS URL and issuer overrides take precedence."""
    settings = Settings(
        supabase_url="https://xyzproject.supabase.co",
        supabase_jwks_url="https://custom-jwks.example.com/keys.json",
        supabase_jwt_issuer="https://custom-auth.example.com",
    )
    assert settings.resolved_jwks_url == "https://custom-jwks.example.com/keys.json"
    assert settings.resolved_jwt_issuer == "https://custom-auth.example.com"


def test_jwt_algorithm_validation() -> None:
    """Verify JWT algorithm parsing, allowlist validation, and 'none' algorithm rejection."""
    # Comma-separated string parsing
    s = Settings(supabase_jwt_algorithms="HS256, RS256")
    assert s.supabase_jwt_algorithms == ["HS256", "RS256"]

    # Reject unsigned 'none' algorithm
    with pytest.raises(ValidationError) as exc:
        Settings(supabase_jwt_algorithms="none")
    assert "Unsigned JWT algorithm 'none' is strictly forbidden" in str(exc.value)

    # Reject unknown algorithm
    with pytest.raises(ValidationError) as exc:
        Settings(supabase_jwt_algorithms="UNSUPPORTED_ALG")
    assert "Unsupported JWT signing algorithm" in str(exc.value)


def test_jwt_public_key_masking() -> None:
    """Verify that public key PEM is masked in repr and str."""
    pem_data = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A\n-----END PUBLIC KEY-----"
    settings = Settings(supabase_jwt_public_key=SecretStr(pem_data))
    assert pem_data not in repr(settings)
    assert pem_data not in str(settings)
    assert settings.get_supabase_jwt_public_key_value() == pem_data
    assert settings.is_auth_configured is True


def test_render_yaml_configuration_matches_settings() -> None:
    """Verify render.yaml specifies APP_ENV=production and declares required secrets."""
    import yaml
    from pathlib import Path

    render_path = Path(__file__).parent.parent / "render.yaml"
    assert render_path.exists(), "render.yaml must exist"
    data = yaml.safe_load(render_path.read_text(encoding="utf-8"))

    services = data.get("services", [])
    assert len(services) >= 1
    web_service = services[0]

    env_vars = {item["key"]: item.get("value") for item in web_service.get("envVars", [])}
    assert "APP_ENV" in env_vars, "render.yaml must use APP_ENV rather than ambiguous ENVIRONMENT"
    assert env_vars["APP_ENV"] == "production"

    # Confirm GUEST_SESSION_SECRET is declared as a sync: false secret
    secret_keys = [item["key"] for item in web_service.get("envVars", []) if item.get("sync") is False]
    assert "GUEST_SESSION_SECRET" in secret_keys, "GUEST_SESSION_SECRET must be declared in render.yaml"


def test_environment_validation_alias_and_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that ENVIRONMENT acts as a validation alias for app_env and APP_ENV has precedence."""
    # 1. ENVIRONMENT alone maps to app_env
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("APP_ENV", raising=False)
    # Production with guest mode requires secret
    s1 = Settings(allow_guest_mode=False)
    assert s1.app_env == "production"

    # 2. When both are set, APP_ENV takes precedence over ENVIRONMENT
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ENVIRONMENT", "production")
    s2 = Settings(allow_guest_mode=False)
    assert s2.app_env == "staging"


def test_production_mode_enforces_security_rules() -> None:
    """Verify that production mode strictly enforces cookie and guest secret requirements."""
    # Production forbids insecure cookies
    with pytest.raises(ValidationError, match="Insecure cookies"):
        Settings(app_env="production", secure_cookies=False)

    # Production with guest mode requires explicit secret
    with pytest.raises(ValidationError, match="require an explicit, stable GUEST_SESSION_SECRET"):
        Settings(app_env="production", allow_guest_mode=True, guest_session_secret=None)

    # Production rejects secret shorter than 32 characters
    with pytest.raises(ValidationError, match="must be at least 32 characters"):
        Settings(app_env="production", allow_guest_mode=True, guest_session_secret="too-short")

    # Production succeeds with valid secret (>= 32 chars)
    valid_secret = "a" * 32
    s = Settings(app_env="production", allow_guest_mode=True, guest_session_secret=valid_secret)
    assert s.app_env == "production"


def test_trusted_proxies_validation() -> None:
    """Verify validation of trusted_proxies: IPs, CIDR ranges, hostnames, and wildcard rejection."""
    # Valid configurations
    s1 = Settings(trusted_proxies=["127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "localhost", "testclient"])
    assert "10.0.0.0/8" in s1.trusted_proxies
    assert "localhost" in s1.trusted_proxies

    # Comma-separated string parsing
    s2 = Settings(trusted_proxies="192.168.1.0/24, fe80::/10, proxy.internal")
    assert s2.trusted_proxies == ["192.168.1.0/24", "fe80::/10", "proxy.internal"]

    # Reject wildcard 0.0.0.0/0
    with pytest.raises(ValidationError, match="Wildcard proxy entry '0.0.0.0/0' is prohibited"):
        Settings(trusted_proxies=["0.0.0.0/0"])

    # Reject wildcard ::/0
    with pytest.raises(ValidationError, match="Wildcard proxy entry '::/0' is prohibited"):
        Settings(trusted_proxies=["::/0"])

    # Reject invalid IP
    with pytest.raises(ValidationError, match="Invalid IP address or CIDR range"):
        Settings(trusted_proxies=["999.999.999.999"])

    # Reject invalid CIDR
    with pytest.raises(ValidationError, match="Invalid IP address or CIDR range"):
        Settings(trusted_proxies=["10.0.0.0/99"])

    # Reject malformed hostname
    with pytest.raises(ValidationError, match="Invalid trusted proxy entry"):
        Settings(trusted_proxies=["invalid host name!"])


