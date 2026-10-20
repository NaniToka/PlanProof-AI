"""Security and configuration regression tests for PlanProof AI.

Verifies secret protection, path sanitization in error messages,
absence of information leaks, and security rules in configuration and .gitignore.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import ConfigurationError, Settings
from app.main import create_app


def test_app_starts_without_gemini_key() -> None:
    """Verify that the application starts cleanly without GEMINI_API_KEY for local offline use."""
    settings = Settings(gemini_api_key=None)
    app = create_app(settings=settings)
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


def test_secrets_never_exposed_in_api_responses(client: TestClient) -> None:
    """Verify that secret values are never included in health, status, or validation responses."""
    # Check /health
    res_health = client.get("/health")
    assert "api_key" not in res_health.text
    assert "secret" not in res_health.text.lower()

    # Check /api/v1/data-status
    res_status = client.get("/api/v1/data-status")
    assert "api_key" not in res_status.text
    assert "secret" not in res_status.text.lower()


def test_error_messages_do_not_expose_absolute_paths(client: TestClient) -> None:
    """Verify that validation and error responses do not leak absolute filesystem paths."""
    # 1. Validation error with path-like input
    payload = {
        "event_type": "wedding",
        "city_tier": "metro",
        "total_budget_inr": 100,  # Invalid budget
        "notes": "/Users/developer/secret_project/exploit.txt",
    }
    res = client.post("/api/v1/budget/calculate", json=payload)
    assert res.status_code == 422
    # Ensure neither macOS (/Users) nor Linux (/home) system paths are reflected
    assert "/Users/" not in res.text
    assert "/home/" not in res.text


def test_gitignore_excludes_secret_and_env_files() -> None:
    """Verify that .gitignore properly excludes .env, keys, and credentials."""
    repo_root = Path(__file__).parent.parent
    gitignore_path = repo_root / ".gitignore"
    assert gitignore_path.exists(), ".gitignore file must exist at project root"

    content = gitignore_path.read_text(encoding="utf-8")
    lines = [
        line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")
    ]

    # Assert critical secret patterns are explicitly listed
    assert ".env" in lines
    assert any(".key" in line for line in lines)
    assert any(".pem" in line for line in lines)
    assert any("__pycache__" in line for line in lines)


def test_configuration_error_handling_sanitizes_path() -> None:
    """Verify that ConfigurationError handler masks filesystem paths and returns 503."""
    app = create_app()

    @app.get("/test-config-error")
    async def trigger_config_error() -> None:
        raise ConfigurationError("Missing key at /Users/tokanani/secret/config.json")

    with TestClient(app) as test_client:
        res = test_client.get("/test-config-error")
        assert res.status_code == 503
        data = res.json()
        assert data["error"]["code"] == "CONFIGURATION_ERROR"
        # Path must be sanitized to remove directory structure
        assert "/Users/tokanani/secret" not in res.text
        assert "config.json" in res.text


def test_secret_str_masks_in_repr_and_logging() -> None:
    """Verify that SecretStr masks the raw key in str and repr."""
    secret_key = "AIzaSySecretTestingKey987654321"
    settings = Settings(gemini_api_key=SecretStr(secret_key))
    assert secret_key not in str(settings)
    assert secret_key not in repr(settings)
    assert "**********" in repr(settings.gemini_api_key)
