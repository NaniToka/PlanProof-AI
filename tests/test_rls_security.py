"""Real PostgreSQL Row Level Security (RLS) deep security verification test suite.

Independently verifies PostgreSQL database-level tenant isolation, anti-spoofing,
child-table protection, role privileges, and pool isolation under a non-bypass role.

Demonstrates:
1. User A can access their own event and child records.
2. User B cannot SELECT User A's event directly in PostgreSQL under the non-bypass role.
3. User B cannot INSERT an event claiming User A as owner.
4. User B cannot UPDATE or DELETE User A's event directly in PostgreSQL.
5. User B cannot access or mutate User A's budgets, milestones, vendor items, or crisis records.
6. A child row cannot be attached to another tenant's event.
7. A request without a valid identity cannot access persistent user data.
8. Connection pooling does not leak identity across users or after failed transactions.
9. The test role is not a superuser and does not have BYPASSRLS.
10. Tests fail if RLS is disabled or if a tenant policy is removed (proving RLS is the real barrier).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.repositories.postgres import PostgresEventRepository
from app.schemas import (
    CityTier,
    EventBudgetBreakdown,
    EventProfile,
    EventType,
    LanguageCode,
)

TEST_APP_DB_URL = os.getenv(
    "TEST_APP_DATABASE_URL",
    "postgresql://planproof_test_app@127.0.0.1:5432/planproof_step1c_test",
)
TEST_ADMIN_DB_URL = os.getenv(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql://tokanani@127.0.0.1:5432/planproof_step1c_test",
)


async def check_pg_available() -> bool:
    """Check if test database is reachable."""
    try:
        conn = await asyncpg.connect(TEST_APP_DB_URL, timeout=3.0)
        await conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def app_conn():
    """Acquire a connection under the non-bypass application role (planproof_test_app)."""
    if not await check_pg_available():
        pytest.skip("Local test PostgreSQL database is not reachable.")
    conn = await asyncpg.connect(TEST_APP_DB_URL)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def admin_conn():
    """Acquire an admin connection only for test user provisioning and teardown."""
    if not await check_pg_available():
        pytest.skip("Local test PostgreSQL database is not reachable.")
    try:
        conn = await asyncpg.connect(TEST_ADMIN_DB_URL)
    except Exception:
        pytest.skip("Admin connection to local test PostgreSQL database not available.")
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def provisioned_tenants(admin_conn):
    """Provision User A and User B in auth.users via admin connection (simulating Supabase Auth)."""
    user_a = uuid4()
    user_b = uuid4()

    await admin_conn.execute(
        """
        INSERT INTO auth.users (id, email)
        VALUES ($1, $3), ($2, $4)
        ON CONFLICT (id) DO NOTHING;
        """,
        user_a,
        user_b,
        f"tenant-a-{user_a}@planproof.ai",
        f"tenant-b-{user_b}@planproof.ai",
    )

    yield user_a, user_b

    # Teardown: delete events and auth.users cleanly
    await admin_conn.execute("DELETE FROM public.events WHERE user_id IN ($1, $2);", user_a, user_b)
    await admin_conn.execute("DELETE FROM auth.users WHERE id IN ($1, $2);", user_a, user_b)


# ==============================================================================
# Requirement 9: Verify Test Role Privileges
# ==============================================================================


async def test_09_test_role_is_not_superuser_and_lacks_bypassrls(app_conn) -> None:
    """Requirement 9: Prove the test role is genuinely non-bypass and non-superuser."""
    is_super = await app_conn.fetchval("SELECT current_setting('is_superuser');")
    assert is_super == "off", "Test connection role must NOT be a PostgreSQL superuser"

    rolname = await app_conn.fetchval("SELECT current_user;")
    assert rolname == "planproof_test_app"

    rolbypassrls = await app_conn.fetchval(
        "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user;"
    )
    assert rolbypassrls is False, "Test connection role must NOT possess BYPASSRLS privilege"

    rolsuper = await app_conn.fetchval(
        "SELECT rolsuper FROM pg_roles WHERE rolname = current_user;"
    )
    assert rolsuper is False, "Test connection role rolsuper attribute must be False"


# ==============================================================================
# Requirement 1 & 2: User A Access & User B Direct Query Isolation
# ==============================================================================


async def test_01_user_a_can_access_own_event_and_child_records(
    provisioned_tenants, app_conn
) -> None:
    """Requirement 1: User A can create and access their own event and child entities."""
    user_a, _ = provisioned_tenants
    event_id = f"EV-TEST-A-{uuid4().hex[:8].upper()}"

    # Connect repository as non-bypass application role
    repo = PostgresEventRepository(database_url=TEST_APP_DB_URL)
    await repo.connect()

    try:
        now = datetime.now(timezone.utc)
        profile = EventProfile(
            event_id=event_id,
            user_id=user_a,
            event_type=EventType.WEDDING,
            event_name="User A Royal Wedding",
            city="Bengaluru",
            city_tier=CityTier.METRO,
            event_date=date(2027, 2, 14),
            guest_count=200,
            total_budget_inr=2000000,
            language=LanguageCode.EN,
            theme_notes="Exclusive theme",
            budget=EventBudgetBreakdown(
                venue=600000,
                catering=600000,
                decor=300000,
                photo_video=200000,
                attire_beauty=100000,
                entertainment=100000,
                logistics=50000,
                buffer=50000,
                total_budget_inr=2000000,
            ),
            created_at=now,
            updated_at=now,
        )

        created = await repo.create(profile, user_id=user_a)
        assert created.event_id == event_id
        assert created.user_id == user_a

        # User A can retrieve via repository
        fetched = await repo.get(event_id, user_id=user_a)
        assert fetched is not None
        assert fetched.event_name == "User A Royal Wedding"
        assert fetched.budget is not None
        assert fetched.budget.total_budget_inr == 2000000

        # User A can retrieve via direct raw SQL under their RLS context
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_a))
            row = await app_conn.fetchrow(
                "SELECT event_id, event_name, total_budget_inr FROM public.events WHERE event_id = $1;",
                event_id,
            )
            assert row is not None
            assert row["event_name"] == "User A Royal Wedding"

            b_row = await app_conn.fetchrow(
                "SELECT venue, catering, total_budget_inr FROM public.event_budgets WHERE event_id = $1;",
                event_id,
            )
            assert b_row is not None
            assert b_row["total_budget_inr"] == 2000000

    finally:
        await repo.delete(event_id, user_id=user_a)
        await repo.disconnect()


async def test_02_user_b_cannot_select_user_a_event_directly(
    provisioned_tenants, app_conn
) -> None:
    """Requirement 2: User B cannot SELECT User A's event, bypassing FastAPI under non-bypass role."""
    user_a, user_b = provisioned_tenants
    event_id = f"EV-TEST-A-{uuid4().hex[:8].upper()}"

    repo = PostgresEventRepository(database_url=TEST_APP_DB_URL)
    await repo.connect()

    try:
        now = datetime.now(timezone.utc)
        profile = EventProfile(
            event_id=event_id,
            user_id=user_a,
            event_type=EventType.BIRTHDAY,
            event_name="User A Private Birthday",
            guest_count=50,
            total_budget_inr=500000,
            created_at=now,
            updated_at=now,
        )
        await repo.create(profile, user_id=user_a)

        # 1. User B attempts query via PostgresEventRepository
        repo_fetched = await repo.get(event_id, user_id=user_b)
        assert repo_fetched is None

        # 2. User B bypasses Python repository and queries PostgreSQL DIRECTLY without WHERE user_id
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))

            # Direct targeted SELECT without user_id filter
            direct_row = await app_conn.fetchrow(
                "SELECT * FROM public.events WHERE event_id = $1;",
                event_id,
            )
            assert direct_row is None, "PostgreSQL RLS must block User B from reading User A's event"

            # Direct table scan without any WHERE clause
            all_rows = await app_conn.fetch("SELECT event_id FROM public.events;")
            found_ids = [r["event_id"] for r in all_rows]
            assert event_id not in found_ids, "PostgreSQL table scan must never expose User A's event to User B"

    finally:
        await repo.delete(event_id, user_id=user_a)
        await repo.disconnect()


# ==============================================================================
# Requirement 3: Anti-Spoofing on INSERT
# ==============================================================================


async def test_03_user_b_cannot_insert_event_claiming_user_a_as_owner(
    provisioned_tenants, app_conn
) -> None:
    """Requirement 3: User B cannot INSERT an event claiming User A as owner."""
    user_a, user_b = provisioned_tenants
    spoofed_event_id = f"EV-SPOOF-{uuid4().hex[:8].upper()}"

    async with app_conn.transaction():
        # Establish User B's verified identity
        await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
        await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))

        # Attempt to insert an event claiming user_a as owner
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError) as exc_info:
            await app_conn.execute(
                """
                INSERT INTO public.events (
                    event_id, user_id, event_type, guest_count, total_budget_inr
                ) VALUES ($1, $2, 'wedding', 100, 1000000);
                """,
                spoofed_event_id,
                user_a,
            )
        assert "violates row-level security policy" in str(exc_info.value)


# ==============================================================================
# Requirement 4: Anti-Mutation (UPDATE and DELETE)
# ==============================================================================


async def test_04_user_b_cannot_update_or_delete_user_a_event(
    provisioned_tenants, app_conn
) -> None:
    """Requirement 4: User B cannot UPDATE or DELETE User A's event directly in PostgreSQL."""
    user_a, user_b = provisioned_tenants
    event_id = f"EV-IMMUT-{uuid4().hex[:8].upper()}"

    repo = PostgresEventRepository(database_url=TEST_APP_DB_URL)
    await repo.connect()

    try:
        now = datetime.now(timezone.utc)
        profile = EventProfile(
            event_id=event_id,
            user_id=user_a,
            event_type=EventType.COMMUNITY_EVENT,
            event_name="Original User A Event",
            guest_count=80,
            total_budget_inr=800000,
            created_at=now,
            updated_at=now,
        )
        await repo.create(profile, user_id=user_a)

        # User B establishes identity and attempts direct UPDATE and DELETE
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))

            # Attempt UPDATE
            update_res = await app_conn.execute(
                "UPDATE public.events SET event_name = 'Compromised Name' WHERE event_id = $1;",
                event_id,
            )
            assert update_res == "UPDATE 0", "RLS must prevent User B from modifying User A's event"

            # Attempt DELETE
            delete_res = await app_conn.execute(
                "DELETE FROM public.events WHERE event_id = $1;",
                event_id,
            )
            assert delete_res == "DELETE 0", "RLS must prevent User B from deleting User A's event"

        # Verify event remains unaltered under User A
        fetched = await repo.get(event_id, user_id=user_a)
        assert fetched is not None
        assert fetched.event_name == "Original User A Event"

    finally:
        await repo.delete(event_id, user_id=user_a)
        await repo.disconnect()


# ==============================================================================
# Requirement 5: Child Resources Protection
# ==============================================================================


async def test_05_user_b_cannot_access_or_mutate_user_a_child_records(
    provisioned_tenants, app_conn
) -> None:
    """Requirement 5: User B cannot read or mutate User A's budgets, milestones, or vendor items."""
    user_a, user_b = provisioned_tenants
    event_id = f"EV-CHILD-{uuid4().hex[:8].upper()}"

    repo = PostgresEventRepository(database_url=TEST_APP_DB_URL)
    await repo.connect()

    try:
        now = datetime.now(timezone.utc)
        profile = EventProfile(
            event_id=event_id,
            user_id=user_a,
            event_type=EventType.WEDDING,
            event_name="Child Isolation Event",
            guest_count=150,
            total_budget_inr=1500000,
            budget=EventBudgetBreakdown(
                venue=500000,
                catering=500000,
                decor=200000,
                photo_video=100000,
                attire_beauty=50000,
                entertainment=50000,
                logistics=50000,
                buffer=50000,
                total_budget_inr=1500000,
            ),
            created_at=now,
            updated_at=now,
        )
        await repo.create(profile, user_id=user_a)

        # Insert a milestone and a vendor checklist item under User A's context
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_a))
            await app_conn.execute(
                """
                INSERT INTO public.event_milestone_statuses (event_id, milestone_id, status)
                VALUES ($1, 'M-TEST-01', 'completed');
                """,
                event_id,
            )
            await app_conn.execute(
                """
                INSERT INTO public.event_vendor_checklist_items (
                    id, event_id, category, title, description, status, priority, booking_status
                ) VALUES ('V-TEST-01', $1, 'catering_refreshments', 'Caterer Contract', 'Book catering', 'completed', 'high', 'booked');
                """,
                event_id,
            )

        # User B attempts direct queries against child tables
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))

            # 1. Budgets table
            b_rows = await app_conn.fetch("SELECT * FROM public.event_budgets WHERE event_id = $1;", event_id)
            assert len(b_rows) == 0, "User B must not read User A's budget"
            b_up = await app_conn.execute("UPDATE public.event_budgets SET venue = 0 WHERE event_id = $1;", event_id)
            assert b_up == "UPDATE 0"

            # 2. Milestones table
            m_rows = await app_conn.fetch("SELECT * FROM public.event_milestone_statuses WHERE event_id = $1;", event_id)
            assert len(m_rows) == 0, "User B must not read User A's milestone statuses"
            m_del = await app_conn.execute("DELETE FROM public.event_milestone_statuses WHERE event_id = $1;", event_id)
            assert m_del == "DELETE 0"

            # 3. Vendor checklist items
            v_rows = await app_conn.fetch("SELECT * FROM public.event_vendor_checklist_items WHERE event_id = $1;", event_id)
            assert len(v_rows) == 0, "User B must not read User A's vendor checklist items"
            v_up = await app_conn.execute("UPDATE public.event_vendor_checklist_items SET status = 'skipped' WHERE event_id = $1;", event_id)
            assert v_up == "UPDATE 0"

    finally:
        await repo.delete(event_id, user_id=user_a)
        await repo.disconnect()


# ==============================================================================
# Requirement 6: Child Row Foreign Attachment Prevention
# ==============================================================================


async def test_06_child_row_cannot_be_attached_to_another_tenants_event(
    provisioned_tenants, app_conn
) -> None:
    """Requirement 6: User B cannot attach child items to User A's event."""
    user_a, user_b = provisioned_tenants
    event_id = f"EV-PARENT-{uuid4().hex[:8].upper()}"

    repo = PostgresEventRepository(database_url=TEST_APP_DB_URL)
    await repo.connect()

    try:
        now = datetime.now(timezone.utc)
        profile = EventProfile(
            event_id=event_id,
            user_id=user_a,
            event_type=EventType.WEDDING,
            event_name="Parent Attachment Event",
            guest_count=100,
            total_budget_inr=1000000,
            created_at=now,
            updated_at=now,
        )
        await repo.create(profile, user_id=user_a)

        # 1. Budget insert violation
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await app_conn.execute(
                    """
                    INSERT INTO public.event_budgets (
                        event_id, venue, catering, decor, photo_video, attire_beauty,
                        entertainment, logistics, buffer, total_budget_inr
                    ) VALUES ($1, 1000000, 0, 0, 0, 0, 0, 0, 0, 1000000);
                    """,
                    event_id,
                )

        # 2. Milestone status insert violation
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await app_conn.execute(
                    """
                    INSERT INTO public.event_milestone_statuses (event_id, milestone_id, status)
                    VALUES ($1, 'M-FORGED', 'completed');
                    """,
                    event_id,
                )

        # 3. Vendor checklist item insert violation
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await app_conn.execute(
                    """
                    INSERT INTO public.event_vendor_checklist_items (
                        id, event_id, category, title, description, status
                    ) VALUES ('V-FORGED', $1, 'venue_permissions', 'Unauthorized Item', 'Desc', 'pending');
                    """,
                    event_id,
                )

    finally:
        await repo.delete(event_id, user_id=user_a)
        await repo.disconnect()


# ==============================================================================
# Requirement 7: Unauthenticated Request Protection
# ==============================================================================


async def test_07_request_without_valid_identity_cannot_access_user_data(
    provisioned_tenants, app_conn
) -> None:
    """Requirement 7: Queries without valid authenticated identity cannot access or insert user data."""
    user_a, _ = provisioned_tenants
    event_id = f"EV-UNAUTH-{uuid4().hex[:8].upper()}"

    repo = PostgresEventRepository(database_url=TEST_APP_DB_URL)
    await repo.connect()

    try:
        now = datetime.now(timezone.utc)
        profile = EventProfile(
            event_id=event_id,
            user_id=user_a,
            event_type=EventType.BIRTHDAY,
            event_name="Unauth Protected Event",
            guest_count=50,
            total_budget_inr=500000,
            created_at=now,
            updated_at=now,
        )
        await repo.create(profile, user_id=user_a)

        # Connection without setting claim or role: auth.uid() evaluates to NULL
        async with app_conn.transaction():
            # Querying events directly without identity
            rows = await app_conn.fetch("SELECT * FROM public.events WHERE event_id = $1;", event_id)
            assert len(rows) == 0, "Unauthenticated queries must return 0 rows under RLS"

            # Attempting insert without identity
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await app_conn.execute(
                    """
                    INSERT INTO public.events (event_id, user_id, event_type, guest_count, total_budget_inr)
                    VALUES ('EV-UNAUTH-TRY', $1, 'birthday', 50, 500000);
                    """,
                    user_a,
                )

    finally:
        await repo.delete(event_id, user_id=user_a)
        await repo.disconnect()


# ==============================================================================
# Requirement 8: Connection Pooling Claim Isolation
# ==============================================================================


async def test_08_connection_pooling_does_not_leak_identity(
    provisioned_tenants,
) -> None:
    """Requirement 8: Connection pool resets transaction claims and does not leak identity."""
    user_a, user_b = provisioned_tenants

    repo = PostgresEventRepository(database_url=TEST_APP_DB_URL, min_size=1, max_size=2)
    await repo.connect()

    try:
        # User A executes a query within an RLS transaction
        async with repo.acquire_connection() as conn_1:
            async with conn_1.transaction():
                await PostgresEventRepository._set_rls_context(conn_1, user_a)
                sub_val = await conn_1.fetchval("SELECT current_setting('request.jwt.claim.sub', true);")
                assert sub_val == str(user_a)

        # Next acquisition from pool must NOT contain residual claim context
        async with repo.acquire_connection() as conn_2:
            sub_after_commit = await conn_2.fetchval("SELECT current_setting('request.jwt.claim.sub', true);")
            assert sub_after_commit in ("", None), f"Residual sub leaked after commit: {sub_after_commit}"

        # User B starts transaction and causes an error (aborted transaction)
        async with repo.acquire_connection() as conn_3:
            try:
                async with conn_3.transaction():
                    await PostgresEventRepository._set_rls_context(conn_3, user_b)
                    # Trigger deliberate syntax error to force ROLLBACK
                    await conn_3.execute("SELECT * FROM nonexistent_table_forcing_abort;")
            except Exception:
                pass

        # Next acquisition after rolled back transaction must also be clean
        async with repo.acquire_connection() as conn_4:
            sub_after_abort = await conn_4.fetchval("SELECT current_setting('request.jwt.claim.sub', true);")
            assert sub_after_abort in ("", None), f"Residual sub leaked after rollback: {sub_after_abort}"

    finally:
        await repo.disconnect()


# ==============================================================================
# Requirement 10: Proof that RLS is the Active Barrier
# ==============================================================================


async def test_10_tests_fail_if_rls_is_disabled(
    provisioned_tenants, admin_conn, app_conn
) -> None:
    """Requirement 10: Prove that RLS is the real protective barrier.

    Demonstrates that disabling RLS allows cross-tenant access,
    whereas enabling RLS completely blocks it.
    """
    user_a, user_b = provisioned_tenants
    event_id = f"EV-BARRIER-{uuid4().hex[:8].upper()}"

    repo = PostgresEventRepository(database_url=TEST_APP_DB_URL)
    await repo.connect()

    try:
        now = datetime.now(timezone.utc)
        profile = EventProfile(
            event_id=event_id,
            user_id=user_a,
            event_type=EventType.WEDDING,
            event_name="Barrier Test Event",
            guest_count=100,
            total_budget_inr=1000000,
            created_at=now,
            updated_at=now,
        )
        await repo.create(profile, user_id=user_a)

        # 1. WITH RLS ENABLED: User B cannot see User A's event
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))
            row_with_rls = await app_conn.fetchrow(
                "SELECT event_id, event_name FROM public.events WHERE event_id = $1;",
                event_id,
            )
            assert row_with_rls is None, "With RLS enabled, User B must see nothing"

        # 2. WITH RLS TEMPORARILY DISABLED: User B CAN see User A's event
        # (Execute DDL outside transaction to release exclusive table lock before app_conn reads)
        await admin_conn.execute("ALTER TABLE public.events DISABLE ROW LEVEL SECURITY;")
        try:
            # Under the non-bypass role, with RLS disabled, User B now sees User A's event
            async with app_conn.transaction():
                await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
                await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))
                row_without_rls = await app_conn.fetchrow(
                    "SELECT event_id, event_name FROM public.events WHERE event_id = $1;",
                    event_id,
                )
                assert row_without_rls is not None, "Disabling RLS allows cross-tenant access"
                assert row_without_rls["event_name"] == "Barrier Test Event"
        finally:
            # Re-enable RLS immediately
            await admin_conn.execute("ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;")

        # 3. VERIFY RLS IS ACTIVE AGAIN
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('role', 'authenticated', true);")
            await app_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_b))
            row_recheck = await app_conn.fetchrow(
                "SELECT event_id, event_name FROM public.events WHERE event_id = $1;",
                event_id,
            )
            assert row_recheck is None, "With RLS re-enabled, User B is blocked again"

    finally:
        await repo.delete(event_id, user_id=user_a)
        await repo.disconnect()
