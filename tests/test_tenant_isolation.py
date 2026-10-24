"""Tenant isolation and multi-tenant security test suite for PlanProof AI.

Covers:
- Server-enforced owner assignment from verified JWT `sub`
- Rejection of client-supplied owner manipulation
- Event listing strictly scoped to the authenticated owner
- Cross-tenant event retrieval, updates, and deletion returning non-leaking HTTP 404
- Child-resource protection across budget, timeline, vendors, AI, crisis recovery, and readiness
- Ephemeral guest session isolation
- PostgreSQL RLS context transaction scoping and connection-pool isolation (unit + integration)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg
import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_guest_session_token
from app.config import Settings
from app.main import create_app
from app.repositories import PostgresEventRepository
from app.schemas import CityTier, EventProfile, EventType


TEST_JWT_SECRET = "super-secret-test-key-32-chars-long-minimum!"
USER_A_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_B_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_token_for(user_id: UUID) -> str:
    """Generate a valid signed HS256 Supabase-compatible JWT for testing."""
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "iss": "https://test.supabase.co/auth/v1",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
        "role": "authenticated",
        "email": f"user-{str(user_id)[:8]}@example.com",
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def auth_settings() -> Settings:
    """Settings configured with test JWT authentication parameters."""
    return Settings(
        app_name="PlanProof AI Tenant Test",
        storage_backend="memory",
        supabase_jwt_secret=TEST_JWT_SECRET,
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://test.supabase.co/auth/v1",
        allow_guest_mode=True,
    )


@pytest.fixture
async def client(auth_settings: Settings) -> AsyncClient:
    """Async test client with JWT configuration."""
    app = create_app(auth_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_event_creation_assigns_authenticated_user_id(client: AsyncClient) -> None:
    """Server-enforced event creation sets user_id from verified sub claim."""
    token = create_token_for(USER_A_ID)
    payload = {
        "event_type": "wedding",
        "event_name": "User A Royal Wedding",
        "city": "Bengaluru",
        "city_tier": "metro",
        "event_date": "2027-02-14",
        "guest_count": 250,
        "total_budget_inr": 2000000,
        "language": "en",
        "theme_notes": "Private notes",
    }
    resp = await client.post(
        "/api/v1/events",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["event_name"] == "User A Royal Wedding"
    assert data["user_id"] == str(USER_A_ID)


@pytest.mark.asyncio
async def test_client_cannot_choose_or_overwrite_owner(client: AsyncClient) -> None:
    """Extra or spoofed user_id in payload is rejected by schema."""
    token = create_token_for(USER_A_ID)
    payload_with_spoofed_user = {
        "event_type": "wedding",
        "event_name": "Spoofed Event",
        "city": "Bengaluru",
        "city_tier": "metro",
        "event_date": "2027-02-14",
        "guest_count": 200,
        "total_budget_inr": 1500000,
        "user_id": str(USER_B_ID),
    }
    resp = await client.post(
        "/api/v1/events",
        json=payload_with_spoofed_user,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_event_listing_restricted_to_owner(client: AsyncClient) -> None:
    """Listing events returns only events owned by the authenticated caller."""
    token_a = create_token_for(USER_A_ID)
    token_b = create_token_for(USER_B_ID)

    # User A creates an event
    resp_a = await client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "event_name": "User A Birthday",
            "city": "Mumbai",
            "city_tier": "metro",
            "event_date": "2027-03-01",
            "guest_count": 50,
            "total_budget_inr": 300000,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a.status_code == 201
    event_a_id = resp_a.json()["event_id"]

    # User B creates an event
    resp_b = await client.post(
        "/api/v1/events",
        json={
            "event_type": "community_event",
            "event_name": "User B Gathering",
            "city": "Delhi",
            "city_tier": "metro",
            "event_date": "2027-04-01",
            "guest_count": 75,
            "total_budget_inr": 500000,
        },
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 201
    event_b_id = resp_b.json()["event_id"]

    # User A lists events -> sees only Event A
    list_a = await client.get("/api/v1/events", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    ids_a = [e["event_id"] for e in list_a.json()["events"]]
    assert event_a_id in ids_a
    assert event_b_id not in ids_a

    # User B lists events -> sees only Event B
    list_b = await client.get("/api/v1/events", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    ids_b = [e["event_id"] for e in list_b.json()["events"]]
    assert event_b_id in ids_b
    assert event_a_id not in ids_b


@pytest.mark.asyncio
async def test_cross_tenant_event_retrieval_update_and_deletion(client: AsyncClient) -> None:
    """User B cannot retrieve, update, or delete User A's event (consistent 404)."""
    token_a = create_token_for(USER_A_ID)
    token_b = create_token_for(USER_B_ID)

    # User A creates an event
    created = await client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "event_name": "Confidential A Summit",
            "city": "Hyderabad",
            "city_tier": "metro",
            "event_date": "2027-05-10",
            "guest_count": 100,
            "total_budget_inr": 1000000,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert created.status_code == 201
    event_id = created.json()["event_id"]

    # User B attempts GET -> 404
    resp_get = await client.get(
        f"/api/v1/events/{event_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_get.status_code == 404

    # User B attempts PATCH -> 404
    resp_patch = await client.patch(
        f"/api/v1/events/{event_id}",
        json={"event_name": "Hacked Name"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_patch.status_code == 404

    # User B attempts DELETE -> 404
    resp_delete = await client.delete(
        f"/api/v1/events/{event_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_delete.status_code == 404

    # User A CAN retrieve it
    resp_a_get = await client.get(
        f"/api/v1/events/{event_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a_get.status_code == 200
    assert resp_a_get.json()["event_name"] == "Confidential A Summit"

    # User A CAN delete it
    resp_a_del = await client.delete(
        f"/api/v1/events/{event_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a_del.status_code == 200


@pytest.mark.asyncio
async def test_child_resources_protected_by_event_ownership(client: AsyncClient) -> None:
    """All child resources return 404 when requested by an unauthorized user."""
    token_a = create_token_for(USER_A_ID)
    token_b = create_token_for(USER_B_ID)

    # User A creates an event
    created = await client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "event_name": "Protected Event A",
            "city": "Bengaluru",
            "city_tier": "metro",
            "event_date": "2027-06-20",
            "guest_count": 200,
            "total_budget_inr": 2000000,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert created.status_code == 201
    event_id = created.json()["event_id"]

    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. Budget
    assert (await client.get(f"/api/v1/events/{event_id}/budget", headers=headers_b)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/events/{event_id}/budget/rebalance",
            json={"new_total_budget_inr": 1800000, "strict_protect": False},
            headers=headers_b,
        )
    ).status_code == 404

    # 2. Timeline & Milestones
    assert (await client.get(f"/api/v1/events/{event_id}/timeline", headers=headers_b)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/events/{event_id}/timeline/milestones/M-01",
            json={"status": "completed"},
            headers=headers_b,
        )
    ).status_code == 404

    # 3. Vendors
    assert (await client.get(f"/api/v1/events/{event_id}/vendors/checklist", headers=headers_b)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/events/{event_id}/vendors/checklist/V-01",
            json={"status": "completed"},
            headers=headers_b,
        )
    ).status_code == 404

    # 4. Recommendations, Risks, Family Council
    assert (await client.get(f"/api/v1/events/{event_id}/ideas", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/events/{event_id}/risks", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/events/{event_id}/family-council", headers=headers_b)).status_code == 404

    # 5. Crisis Recovery
    assert (
        await client.post(
            f"/api/v1/events/{event_id}/crisis/evaluate",
            json={"crisis_type": "vendor_cancellation", "severity": 2, "description": "Caterer canceled"},
            headers=headers_b,
        )
    ).status_code == 404
    assert (await client.get(f"/api/v1/events/{event_id}/crisis/recoveries", headers=headers_b)).status_code == 404

    # 6. Readiness
    assert (await client.get(f"/api/v1/events/{event_id}/readiness", headers=headers_b)).status_code == 404


@pytest.mark.asyncio
async def test_guest_session_isolation(client: AsyncClient) -> None:
    """Guest sessions with different server-issued session headers cannot access each other's events."""
    session_1, _, _ = create_guest_session_token(secret=TEST_JWT_SECRET)
    session_2, _, _ = create_guest_session_token(secret=TEST_JWT_SECRET)

    # Guest 1 creates an event
    resp_g1 = await client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "event_name": "Guest 1 Shower",
            "city": "Chennai",
            "city_tier": "metro",
            "event_date": "2027-07-01",
            "guest_count": 40,
            "total_budget_inr": 200000,
        },
        headers={"X-Guest-Session-ID": session_1},
    )
    assert resp_g1.status_code == 201
    event_g1_id = resp_g1.json()["event_id"]

    # Guest 2 attempts to retrieve Guest 1's event -> 404
    resp_g2_get = await client.get(
        f"/api/v1/events/{event_g1_id}",
        headers={"X-Guest-Session-ID": session_2},
    )
    assert resp_g2_get.status_code == 404

    # Authenticated user cannot access Guest 1's event
    token_a = create_token_for(USER_A_ID)
    resp_auth_get = await client.get(
        f"/api/v1/events/{event_g1_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_auth_get.status_code == 404

    # Guest 1 CAN retrieve their event
    resp_g1_ok = await client.get(
        f"/api/v1/events/{event_g1_id}",
        headers={"X-Guest-Session-ID": session_1},
    )
    assert resp_g1_ok.status_code == 200


@pytest.mark.asyncio
async def test_forged_or_guessed_guest_session_rejected(client: AsyncClient) -> None:
    """A forged, guessed, or raw UUID guest session identifier cannot access or create data."""
    # 1. Raw guessed UUID
    raw_uuid = str(uuid4())
    resp_raw = await client.get("/api/v1/events", headers={"X-Guest-Session-ID": raw_uuid})
    assert resp_raw.status_code == 401
    assert resp_raw.json()["error"]["code"] == "INVALID_GUEST_SESSION"

    # 2. Forged signature
    valid_token, _, _ = create_guest_session_token(secret=TEST_JWT_SECRET)
    tampered_token = valid_token[:-4] + "xxxx"
    resp_tampered = await client.get("/api/v1/events", headers={"X-Guest-Session-ID": tampered_token})
    assert resp_tampered.status_code == 401
    assert resp_tampered.json()["error"]["code"] == "INVALID_GUEST_SESSION"

    # 3. Expired guest token
    expired_token, _, _ = create_guest_session_token(ttl_seconds=-10, secret=TEST_JWT_SECRET)
    resp_expired = await client.get("/api/v1/events", headers={"X-Guest-Session-ID": expired_token})
    assert resp_expired.status_code == 401
    assert resp_expired.json()["error"]["code"] == "INVALID_GUEST_SESSION"

    # 4. Token signed with wrong secret
    wrong_token, _, _ = create_guest_session_token(secret="completely-different-secret-key-32!")
    resp_wrong = await client.get("/api/v1/events", headers={"X-Guest-Session-ID": wrong_token})
    assert resp_wrong.status_code == 401
    assert resp_wrong.json()["error"]["code"] == "INVALID_GUEST_SESSION"


@pytest.mark.asyncio
async def test_guest_cannot_access_postgres_storage(auth_settings: Settings) -> None:
    """Guest sessions are strictly rejected when storage backend is PostgreSQL."""
    pg_settings = auth_settings.model_copy(
        update={
            "storage_backend": "postgres",
            "database_url": "postgresql://test_user:test_pass@127.0.0.1:5432/test_db",
        }
    )
    app = create_app(settings=pg_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as pg_client:
        valid_guest_token, _, _ = create_guest_session_token(secret=TEST_JWT_SECRET)
        resp = await pg_client.get(
            "/api/v1/events", headers={"X-Guest-Session-ID": valid_guest_token}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert "PostgreSQL" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_guest_session_issuance_endpoint(client: AsyncClient) -> None:
    """Server issues cryptographically valid guest tokens via endpoint."""
    resp = await client.post("/api/v1/auth/guest-session")
    assert resp.status_code == 200
    data = resp.json()
    assert "guest_session_token" in data
    assert data["guest_session_token"].startswith("gst.")
    assert "session_id" in data
    assert "expires_at" in data
    # Response also sets header and cookie
    assert "X-Guest-Session-ID" in resp.headers
    assert "planproof_guest_session" in resp.cookies



@pytest.mark.asyncio
async def test_postgres_rls_transaction_scoping_and_zero_leakage() -> None:
    """Live PostgreSQL RLS context test: verifying transaction-scoped identity and pool safety under non-bypass role.

    If local test DB is available, tests real RLS enforcement under transaction settings.
    """
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL", "postgresql://tokanani@127.0.0.1:5432/planproof_step1c_test")
    app_url = os.getenv("TEST_APP_DATABASE_URL", "postgresql://planproof_test_app@127.0.0.1:5432/planproof_step1c_test")

    try:
        admin_conn = await asyncpg.connect(admin_url)
    except Exception:
        pytest.skip("Local test PostgreSQL database not available for live RLS pool test.")

    try:
        user_1 = uuid4()
        user_2 = uuid4()

        # Ensure profiles exist via auth.users using admin provisioning
        await admin_conn.execute(
            """
            INSERT INTO auth.users (id, email)
            VALUES ($1, $3),
                   ($2, $4)
            ON CONFLICT (id) DO NOTHING;
            """,
            user_1,
            user_2,
            f"tenant-{user_1}@example.com",
            f"tenant-{user_2}@example.com",
        )

        # Repository MUST connect as non-bypass application role (NOT superuser, NOT bypassrls)
        repo = PostgresEventRepository(database_url=app_url)
        await repo.connect()

        async with repo.acquire_connection() as conn_check:
            is_super = await conn_check.fetchval("SELECT current_setting('is_superuser');")
            assert is_super == "off", "Repository connection must not be superuser"
            bypass = await conn_check.fetchval("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user;")
            assert bypass is False, "Repository connection must not have BYPASSRLS"

        now = datetime.now(timezone.utc)
        # User 1 creates an event
        profile_1 = EventProfile(
            event_id=f"EV-RLS-{uuid4().hex[:8].upper()}",
            user_id=user_1,
            event_type=EventType.WEDDING,
            event_name="Tenant 1 Gala",
            city="Bengaluru",
            city_tier=CityTier.METRO,
            guest_count=100,
            total_budget_inr=1500000,
            created_at=now,
            updated_at=now,
        )
        created = await repo.create(profile_1, user_id=user_1)
        assert created.event_id == profile_1.event_id

        # 1. User 1 can retrieve their event
        fetched_1 = await repo.get(profile_1.event_id, user_id=user_1)
        assert fetched_1 is not None
        assert fetched_1.event_name == "Tenant 1 Gala"

        # 2. User 2 cannot retrieve User 1's event
        fetched_2 = await repo.get(profile_1.event_id, user_id=user_2)
        assert fetched_2 is None

        # 3. User 2 listing events does not see User 1's event
        list_u2, count_u2 = await repo.list(user_id=user_2)
        assert count_u2 == 0
        assert not any(e.event_id == profile_1.event_id for e in list_u2)

        # 4. Connection pool isolation:
        # After executing queries with RLS context, verify that the connection has no residual claim context
        async with repo._pool.acquire() as pool_conn:
            sub_setting = await pool_conn.fetchval("SELECT current_setting('request.jwt.claim.sub', true);")
            role_setting = await pool_conn.fetchval("SELECT current_setting('role', true);")
            assert sub_setting in ("", None), f"Residual sub leaked: {sub_setting}"
            assert role_setting != "authenticated" or sub_setting in ("", None)

        # Cleanup
        await repo.delete(profile_1.event_id, user_id=user_1)
        await repo.disconnect()

    finally:
        await admin_conn.execute("DELETE FROM auth.users WHERE id IN ($1, $2);", user_1, user_2)
        await admin_conn.close()
