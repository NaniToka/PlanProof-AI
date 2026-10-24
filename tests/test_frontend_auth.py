"""Integration and contract tests for Step 3: Supabase Auth Frontend Integration.

Verifies:
- Safe frontend config endpoint (/api/v1/auth/config) exposes only public anon keys and URL.
- Zero secret leakage (SUPABASE_JWT_SECRET, db passwords, connection URIs never exposed).
- Unconfigured Supabase gracefully handles requests and reports configured: False.
- Frontend static HTML includes pinned official Supabase client and Auth UI elements.
- Frontend static CSS includes styling for auth pills, modal tabs, and alerts.
- Frontend static JS implements AuthManager, Bearer token attachment, 401 retry, and cleanup.
- Protected API endpoints verify Bearer tokens and enforce tenant isolation.
- Account switching and logout prevent cross-account event visibility.
- Guest/demo mode remains safely isolated on in-memory storage.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app

TEST_SECRET = "test-jwt-secret-for-step3-frontend-auth-32bytes!"


def create_token(
    user_id: str,
    email: str = "testuser@example.com",
    role: str = "authenticated",
    secret: str = TEST_SECRET,
    expired: bool = False,
) -> str:
    """Helper to generate mock Supabase access tokens."""
    exp = (
        datetime.now(UTC) - timedelta(hours=1)
        if expired
        else datetime.now(UTC) + timedelta(hours=1)
    )
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "aud": "authenticated",
        "exp": int(exp.timestamp()),
        "iat": int((datetime.now(UTC) - timedelta(minutes=5)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ==============================================================================
# 1. Configuration & Secret Safety Tests
# ==============================================================================


def test_auth_config_endpoint_when_configured() -> None:
    """Verify that /api/v1/auth/config safely exposes public parameters and never server secrets."""
    settings = Settings(
        supabase_url="https://mockproject.supabase.co",
        supabase_anon_key=SecretStr("mock-anon-public-key-xyz123"),
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        database_url=SecretStr("postgresql://user:supersecretpass@db.example.com:5432/postgres"),
        allow_guest_mode=True,
        storage_backend="memory",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        res = client.get("/api/v1/auth/config")
        assert res.status_code == 200
        data = res.json()

        # Public fields exposed
        assert data["configured"] is True
        assert data["supabase_url"] == "https://mockproject.supabase.co"
        assert data["supabase_anon_key"] == "mock-anon-public-key-xyz123"
        assert data["allow_guest_mode"] is True
        assert data["storage_backend"] == "memory"

        # Critical: Verify secrets are NEVER in response
        raw_text = res.text.lower()
        assert TEST_SECRET.lower() not in raw_text
        assert "supersecretpass" not in raw_text
        assert "jwt_secret" not in raw_text
        assert "database_url" not in raw_text


def test_auth_config_endpoint_when_unconfigured() -> None:
    """Verify that /api/v1/auth/config reports configured: False when keys are missing."""
    settings = Settings(
        supabase_url=None,
        supabase_anon_key=None,
        supabase_jwt_secret=None,
        allow_guest_mode=True,
        storage_backend="memory",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        res = client.get("/api/v1/auth/config")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["supabase_url"] is None
        assert data["supabase_anon_key"] is None


# ==============================================================================
# 2. Frontend Asset & HTML/CSS/JS Integration Tests
# ==============================================================================


def test_index_html_includes_pinned_supabase_client_and_auth_ui() -> None:
    """Verify that index.html loads pinned Supabase JS and includes complete auth UI components."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        html = res.text

        # Official Supabase client pinned CDN script
        assert "cdn.jsdelivr.net/npm/@supabase/supabase-js@2.48.1" in html

        # Header account indicator & button
        assert 'id="auth-status-container"' in html
        assert 'id="auth-status-badge"' in html
        assert 'id="auth-user-email"' in html
        assert 'id="btn-auth-action"' in html

        # Setup notice banner
        assert 'id="auth-unconfigured-banner"' in html

        # Authentication modal & forms
        assert 'id="modal-auth"' in html
        assert 'id="tab-auth-login"' in html
        assert 'id="tab-auth-signup"' in html
        assert 'id="form-auth"' in html
        assert 'id="auth-email"' in html
        assert 'id="auth-password"' in html
        assert 'id="auth-alert"' in html
        assert 'id="btn-auth-submit"' in html
        assert 'id="btn-switch-auth-mode"' in html
        assert 'id="btn-close-auth-modal"' in html


def test_style_css_includes_auth_design_system() -> None:
    """Verify that style.css defines styles for auth pills, indicators, modals, and alerts."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/static/style.css")
        assert res.status_code == 200
        css = res.text

        assert ".auth-status-container" in css
        assert ".auth-status-pill" in css
        assert ".auth-status-pill.authenticated" in css
        assert ".auth-status-pill.guest" in css
        assert ".auth-status-dot.online" in css
        assert ".auth-modal-header-tabs" in css
        assert ".auth-tab-btn.active" in css
        assert ".auth-alert" in css
        assert ".auth-alert.error" in css
        assert ".auth-alert.success" in css
        assert ".auth-unconfigured-banner" in css


def test_app_js_includes_auth_manager_and_token_handling() -> None:
    """Verify app.js implements official client integration, token injection, and 401 retry."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/static/app.js")
        assert res.status_code == 200
        js = res.text

        # AuthManager existence and methods
        assert "const AuthManager = {" in js
        assert "getGuestSessionId()" in js
        assert "isAuthenticated()" in js
        assert "signIn(" in js
        assert "signUp(" in js
        assert "signOut(" in js
        assert "handleSessionExpired()" in js
        assert "clearUserState()" in js
        assert "handleAuthStateChange(" in js

        # Token attachment and 401 refresh
        assert "Authorization" in js
        assert "Bearer" in js
        assert "refreshSession()" in js
        assert "isRetry" in js  # Guard preventing retry loops

        # State clearing logic
        assert "sessionStorage.removeItem('planproof_active_event_id')" in js

        # Config endpoint call
        assert "/api/v1/auth/config" in js


# ==============================================================================
# 3. Token Attachment, Backend Verification, and Isolation Tests
# ==============================================================================


def test_bearer_token_attachment_and_user_event_creation() -> None:
    """Verify that attaching a valid Bearer token associates created events with the token sub."""
    user_id = str(uuid4())
    token = create_token(user_id=user_id, email="alice@example.com")

    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        allow_guest_mode=True,
        storage_backend="memory",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "event_type": "wedding",
            "city_tier": "metro",
            "total_budget_inr": 2000000,
            "guest_count": 300,
            "event_name": "Alice Wedding Celebration",
        }
        res = client.post("/api/v1/events", json=payload, headers=headers)
        assert res.status_code == 201
        event_data = res.json()
        assert event_data["user_id"] == user_id
        assert event_data["event_name"] == "Alice Wedding Celebration"


def test_expired_token_returns_401_without_retry_loop() -> None:
    """Verify that an expired Bearer token is rejected with HTTP 401 and TOKEN_EXPIRED."""
    user_id = str(uuid4())
    token = create_token(user_id=user_id, expired=True)

    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        allow_guest_mode=True,
        storage_backend="memory",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        res = client.get("/api/v1/events", headers=headers)
        assert res.status_code == 401
        data = res.json()
        assert data["error"]["code"] == "TOKEN_EXPIRED"


def test_account_switching_isolation_between_two_users() -> None:
    """Verify that events created by User A are never returned to User B after account switch."""
    user_a = str(uuid4())
    user_b = str(uuid4())

    token_a = create_token(user_id=user_a, email="user_a@example.com")
    token_b = create_token(user_id=user_b, email="user_b@example.com")

    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        allow_guest_mode=True,
        storage_backend="memory",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        # 1. User A creates an event
        payload = {
            "event_type": "birthday",
            "city_tier": "tier2",
            "total_budget_inr": 150000,
            "guest_count": 50,
            "event_name": "User A Birthday",
        }
        res_a = client.post(
            "/api/v1/events", json=payload, headers={"Authorization": f"Bearer {token_a}"}
        )
        assert res_a.status_code == 201
        event_a_id = res_a.json()["event_id"]

        # 2. User A lists events -> sees Event A
        list_a = client.get("/api/v1/events", headers={"Authorization": f"Bearer {token_a}"})
        assert list_a.status_code == 200
        assert any(e["event_id"] == event_a_id for e in list_a.json()["events"])

        # 3. User B lists events -> sees 0 events (never sees User A's data)
        list_b = client.get("/api/v1/events", headers={"Authorization": f"Bearer {token_b}"})
        assert list_b.status_code == 200
        assert not any(e["event_id"] == event_a_id for e in list_b.json()["events"])

        # 4. User B attempts direct GET for User A's event -> 404 Not Found
        get_b = client.get(
            f"/api/v1/events/{event_a_id}", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert get_b.status_code == 404


def test_guest_mode_remains_isolated_from_authenticated_data() -> None:
    """Verify that an unauthenticated guest cannot access authenticated user events."""
    user_id = str(uuid4())
    token = create_token(user_id=user_id, email="auth_user@example.com")

    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        allow_guest_mode=True,
        storage_backend="memory",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        # Authenticated user creates an event
        payload = {
            "event_type": "community_event",
            "city_tier": "tier3",
            "total_budget_inr": 500000,
            "guest_count": 200,
            "event_name": "Festival Gathering",
        }
        res = client.post(
            "/api/v1/events", json=payload, headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 201
        event_id = res.json()["event_id"]

        # Guest without Authorization header lists events -> cannot see authenticated event
        guest_list = client.get("/api/v1/events")
        assert guest_list.status_code == 200
        assert not any(e["event_id"] == event_id for e in guest_list.json()["events"])

        # Guest direct GET -> 404
        guest_get = client.get(f"/api/v1/events/{event_id}")
        assert guest_get.status_code == 404


def test_child_resources_require_owner_token() -> None:
    """Verify that all child resource endpoints enforce ownership and reject other tenants."""
    user_a = str(uuid4())
    user_b = str(uuid4())

    token_a = create_token(user_id=user_a, email="user_a@example.com")
    token_b = create_token(user_id=user_b, email="user_b@example.com")

    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        allow_guest_mode=True,
        storage_backend="memory",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        # Create event as User A
        payload = {
            "event_type": "wedding",
            "city_tier": "metro",
            "total_budget_inr": 2500000,
            "guest_count": 250,
            "event_name": "User A Child Resource Event",
        }
        res = client.post(
            "/api/v1/events", json=payload, headers={"Authorization": f"Bearer {token_a}"}
        )
        assert res.status_code == 201
        event_id = res.json()["event_id"]

        child_endpoints = [
            f"/api/v1/events/{event_id}/budget",
            f"/api/v1/events/{event_id}/timeline",
            f"/api/v1/events/{event_id}/vendors/checklist",
            f"/api/v1/events/{event_id}/risks",
            f"/api/v1/events/{event_id}/ideas",
            f"/api/v1/events/{event_id}/family-council",
            f"/api/v1/events/{event_id}/readiness",
            f"/api/v1/events/{event_id}/crisis/recoveries",
        ]

        # User A has access to all child resources
        for ep in child_endpoints:
            res_a = client.get(ep, headers={"Authorization": f"Bearer {token_a}"})
            assert res_a.status_code == 200, f"User A should access {ep}"

        # User B is blocked with 404 on all User A child resources
        for ep in child_endpoints:
            res_b = client.get(ep, headers={"Authorization": f"Bearer {token_b}"})
            assert res_b.status_code == 404, f"User B must receive 404 on {ep}"


def test_missing_token_when_postgres_storage_active_returns_401() -> None:
    """Verify that unauthenticated access is strictly blocked when storage_backend is postgres."""
    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        allow_guest_mode=True,
        storage_backend="postgres",
        database_url=SecretStr("postgresql://user:pass@localhost:5432/testdb"),
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        res = client.get("/api/v1/events")
        assert res.status_code == 401
        data = res.json()
        assert data["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_malformed_authorization_headers_rejected() -> None:
    """Verify that non-Bearer or malformed Authorization headers return 401."""
    settings = Settings(
        supabase_jwt_secret=SecretStr(TEST_SECRET),
        allow_guest_mode=True,
        storage_backend="memory",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        # 1. Basic auth scheme
        res1 = client.get("/api/v1/events", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert res1.status_code == 401
        assert res1.json()["error"]["code"] == "INVALID_TOKEN"

        # 2. Empty Bearer
        res2 = client.get("/api/v1/events", headers={"Authorization": "Bearer "})
        assert res2.status_code == 401

        # 3. Malformed garbage token
        res3 = client.get("/api/v1/events", headers={"Authorization": "Bearer not-a-jwt"})
        assert res3.status_code == 401
