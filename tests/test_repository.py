"""
Unit and Integration Tests for PlanProof AI Repository Layer (Step 1C).

Tests:
1. Base repository interface and InMemoryEventRepository implementation
2. Backward compatibility of EventStore
3. Repository factory and dependency injection selection
4. Missing database configuration and invalid storage backends
5. Startup and shutdown lifecycle behavior
6. Mocked PostgreSQL operations (connection failure, transaction rollback, parameterized SQL)
7. Live PostgreSQL integration tests against local database (when available)
8. Predictable error responses without silent fallback
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import asyncpg
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
import pytest

from app.config import ConfigurationError, Settings
from app.main import create_app
from app.repositories import (
    BaseEventRepository,
    DatabaseConnectionError,
    EventNotFoundError,
    InMemoryEventRepository,
    PostgresEventRepository,
    RepositoryError,
    RepositoryIntegrityError,
    create_event_repository,
)
from app.schemas import (
    CityTier,
    CrisisRecoveryRecord,
    EventBudgetBreakdown,
    EventCrisisRecoveryResponse,
    EventProfile,
    EventType,
    EventVendorChecklistItem,
    LanguageCode,
    MatchedCrisisScenario,
    MilestoneStatus,
    RecoveryActionStatus,
    RecoveryProgressSummary,
    RecoveryStatus,
    TrackedRecoveryAction,
    VendorBookingStatus,
    VendorChecklistCategory,
    VendorChecklistPriority,
    VendorChecklistStatus,
)
from app.services.event_service import EventService, EventStore

# Local test connection string used for live integration tests
LOCAL_PG_URL = "postgresql://postgres@127.0.0.1:5432/planproof_step1c_test"


def check_live_postgres_available() -> bool:
    """Synchronously test whether the local PostgreSQL instance and database are available."""
    try:
        import socket

        s = socket.socket()
        s.settimeout(0.3)
        s.connect(("127.0.0.1", 5432))
        s.close()

        async def _test_conn() -> bool:
            try:
                conn = await asyncpg.connect(LOCAL_PG_URL, timeout=2.0)
                await conn.close()
                return True
            except Exception:
                return False

        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(_test_conn())
        loop.close()
        return res
    except Exception:
        return False


IS_LIVE_PG_AVAILABLE = check_live_postgres_available()


def make_test_event_profile(
    event_id: str | None = None,
    name: str = "Priya & Rohan Sangeet",
    budget: int = 1500000,
    guest_count: int = 250,
) -> EventProfile:
    """Helper to generate a valid, realistic EventProfile model."""
    now = datetime.now(timezone.utc)
    return EventProfile(
        event_id=event_id or f"evt_{uuid4().hex[:12]}",
        event_name=name,
        event_type=EventType.WEDDING,
        event_date=date(2026, 12, 15),
        city="Mumbai",
        city_tier=CityTier.METRO,
        total_budget_inr=budget,
        guest_count=guest_count,
        language=LanguageCode.EN,
        theme_notes="Royal Maratha aesthetic with floral accents",
        is_in_progress=False,
        created_at=now,
        updated_at=now,
    )


# ==============================================================================
# 1. In-Memory Repository & EventStore Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_in_memory_repository_crud() -> None:
    """Test full CRUD operations on InMemoryEventRepository."""
    repo = InMemoryEventRepository()
    assert await repo.count() == 0

    event = make_test_event_profile()
    created = await repo.create(event)
    assert created.event_id == event.event_id
    assert await repo.count() == 1

    fetched = await repo.get(event.event_id)
    assert fetched is not None
    assert fetched.event_name == event.event_name

    # Update
    updated_profile = fetched.model_copy(update={"total_budget_inr": 2000000})
    res_update = await repo.update(event.event_id, updated_profile)
    assert res_update is not None
    assert res_update.total_budget_inr == 2000000

    # List & pagination (returns (items, total))
    events, total = await repo.list(skip=0, limit=10)
    assert total == 1
    assert len(events) == 1
    assert events[0].event_id == event.event_id

    # Delete
    deleted = await repo.delete(event.event_id)
    assert deleted is True
    assert await repo.count() == 0
    assert await repo.get(event.event_id) is None


@pytest.mark.asyncio
async def test_in_memory_repository_capacity_eviction() -> None:
    """Test that InMemoryEventRepository strictly respects capacity and evicts oldest."""
    repo = InMemoryEventRepository(max_capacity=3)
    e1 = make_test_event_profile(event_id="evt_001")
    e2 = make_test_event_profile(event_id="evt_002")
    e3 = make_test_event_profile(event_id="evt_003")
    e4 = make_test_event_profile(event_id="evt_004")

    await repo.create(e1)
    await repo.create(e2)
    await repo.create(e3)
    assert await repo.count() == 3

    # Adding 4th should evict e1
    await repo.create(e4)
    assert await repo.count() == 3
    assert await repo.get("evt_001") is None
    assert await repo.get("evt_002") is not None
    assert await repo.get("evt_004") is not None


@pytest.mark.asyncio
async def test_in_memory_repository_granular_methods() -> None:
    """Test budget, milestone, vendor, and recovery methods on InMemoryEventRepository."""
    repo = InMemoryEventRepository()
    event = make_test_event_profile(event_id="evt_granular")
    await repo.create(event)

    # Budget
    assert await repo.get_budget("evt_granular") is None
    budget = EventBudgetBreakdown(
        venue=400000,
        catering=600000,
        decor=200000,
        photo_video=150000,
        entertainment=100000,
        attire_beauty=30000,
        logistics=10000,
        buffer=10000,
        total_budget_inr=1500000,
    )
    saved_budget = await repo.save_budget("evt_granular", budget)
    assert saved_budget == budget
    assert await repo.get_budget("evt_granular") == budget

    # Milestone statuses
    milestones = await repo.get_milestone_statuses("evt_granular")
    assert milestones == {}
    await repo.save_milestone_status("evt_granular", "M1", MilestoneStatus.COMPLETED)
    milestones = await repo.get_milestone_statuses("evt_granular")
    assert milestones.get("M1") == MilestoneStatus.COMPLETED

    # Vendor checklist
    checklist = await repo.get_vendor_checklist("evt_granular")
    assert checklist == []
    now = datetime.now(timezone.utc)
    vendor_item = EventVendorChecklistItem(
        id="V1",
        category=VendorChecklistCategory.VENUE_PERMISSIONS,
        title="Book banquet hall",
        description="Finalize contract with banquet",
        status=VendorChecklistStatus.IN_PROGRESS,
        due_date=date(2026, 11, 1),
        days_before_event=44,
        priority=VendorChecklistPriority.HIGH,
        notes="Checked acoustic rating",
        vendor_name="Taj Banquet",
        booking_status=VendorBookingStatus.CONTACTED,
        created_at=now,
        updated_at=now,
    )
    await repo.save_vendor_checklist_item("evt_granular", vendor_item)
    checklist = await repo.get_vendor_checklist("evt_granular")
    assert len(checklist) == 1
    assert checklist[0].id == "V1"

    # Recovery record
    matched_scenario = MatchedCrisisScenario(
        scenario_id="CR-01",
        is_dataset_match=True,
        crisis_type="rain",
        severity=2,
        event_type=EventType.WEDDING,
        phase="event_day",  # type: ignore[arg-type]
        description="Lawn flooded",
        recommended_fix="Shift indoors",
        cost_impact_pct_of_budget=5.0,
        message_target="guests",  # type: ignore[arg-type]
        synthetic=True,
    )
    plan = EventCrisisRecoveryResponse(
        event_id="evt_granular",
        event_type=EventType.WEDDING,
        event_name="Priya & Rohan Sangeet",
        event_phase="event_day",  # type: ignore[arg-type]
        matched_scenario=matched_scenario,
        crisis_summary="Outdoor lawn flooded during heavy rains",
        severity=2,
        affected_area="venue",
        immediate_actions=[
            {
                "priority": 1,
                "category": "immediate_safety",
                "title": "Triage electrical lines",
                "action": "Cut lawn power lines",
                "responsible_party": "Electrician",
                "timeframe": "Immediate (0-15 mins)",
            }
        ],
        budget_impact={
            "cost_impact_pct": 5.0,
            "estimated_rupee_impact": 75000,
            "affected_categories": ["venue"],
            "existing_buffer_inr": 10000,
            "buffer_sufficient": False,
            "advice": "Buffer insufficient; reallocate decor savings",
        },
        escalation_guidance="Contact on-site venue supervisor and local electrician.",
    )
    action = TrackedRecoveryAction(
        action_id="ACT-1",
        recovery_id="REC-01",
        title="Cut power",
        description="Ensure lawn wiring is isolated",
        priority=1,
        status=RecoveryActionStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    rec = CrisisRecoveryRecord(
        recovery_id="REC-01",
        event_id="evt_granular",
        crisis_type="rain",
        severity=2,
        description="Rain contingency",
        recovery_plan=plan,
        source="rules",
        status=RecoveryStatus.OPEN,
        actions=[action],
        progress=RecoveryProgressSummary(total_actions=1, completed_actions=0),
        total_actions=1,
        completed_actions=0,
        created_at=now,
        updated_at=now,
    )
    saved_rec = await repo.create_recovery_record("evt_granular", rec)
    assert saved_rec.recovery_id == "REC-01"

    rec_list = await repo.list_recovery_records("evt_granular")
    assert len(rec_list) == 1

    # Update action
    updated_act = await repo.update_recovery_action(
        "evt_granular", "REC-01", "ACT-1", status=RecoveryActionStatus.COMPLETED, notes="Power cut safe"
    )
    assert updated_act is not None
    assert updated_act.status == RecoveryActionStatus.COMPLETED
    assert updated_act.notes == "Power cut safe"


@pytest.mark.asyncio
async def test_event_store_backward_compatibility() -> None:
    """Verify that EventStore is a compatible subclass of InMemoryEventRepository."""
    store = EventStore()
    assert isinstance(store, BaseEventRepository)
    assert isinstance(store, InMemoryEventRepository)

    event = make_test_event_profile(event_id="evt_compat")
    await store.create(event)
    fetched = await store.get("evt_compat")
    assert fetched is not None
    assert fetched.event_id == "evt_compat"

    events, total = await store.list()
    assert len(events) == 1
    assert total == 1
    assert await store.count() == 1
    await store.clear()
    assert await store.count() == 0


# ==============================================================================
# 2. Repository Factory and Configuration Selection Tests
# ==============================================================================


def test_factory_defaults_to_in_memory() -> None:
    """Verify factory returns InMemoryEventRepository by default."""
    settings = Settings(storage_backend="memory")
    repo = create_event_repository(settings)
    assert isinstance(repo, InMemoryEventRepository)
    assert not isinstance(repo, PostgresEventRepository)


def test_factory_explicit_memory() -> None:
    """Verify explicit storage_backend='memory' creates InMemoryEventRepository."""
    settings = Settings(storage_backend="memory", max_in_memory_events=100)
    repo = create_event_repository(settings)
    assert isinstance(repo, InMemoryEventRepository)


def test_factory_postgres_missing_database_url_fails_fast() -> None:
    """Verify factory raises ConfigurationError if storage_backend='postgres' without database_url."""
    settings = Settings(storage_backend="postgres", database_url=None)
    with pytest.raises(ConfigurationError) as exc_info:
        create_event_repository(settings)
    assert "DATABASE_URL" in str(exc_info.value)


def test_factory_invalid_backend_raises() -> None:
    """Verify factory raises ConfigurationError for unsupported storage backends."""
    # We bypass pydantic validation here to test factory resilience
    settings = Settings(storage_backend="memory")
    object.__setattr__(settings, "storage_backend", "mongodb")
    with pytest.raises(ConfigurationError) as exc_info:
        create_event_repository(settings)
    assert "mongodb" in str(exc_info.value)


def test_factory_postgres_with_valid_url() -> None:
    """Verify factory instantiates PostgresEventRepository when configured properly."""
    settings = Settings(
        storage_backend="postgres",
        database_url=LOCAL_PG_URL,
        database_pool_min_size=2,
        database_pool_max_size=5,
    )
    repo = create_event_repository(settings)
    assert isinstance(repo, PostgresEventRepository)
    assert repo.settings == settings


# ==============================================================================
# 3. Application Lifecycle & Dependency Injection Tests
# ==============================================================================


def test_app_lifespan_initializes_and_closes_repository() -> None:
    """Test that FastAPI lifespan initializes event_repository and cleans up on exit."""
    settings = Settings(storage_backend="memory")
    app = create_app(settings=settings)

    with TestClient(app) as client:
        # App state should have repository initialized
        assert hasattr(app.state, "event_repository")
        assert hasattr(app.state, "event_store")
        assert isinstance(app.state.event_repository, InMemoryEventRepository)

        # Health endpoint should succeed
        resp = client.get("/health")
        assert resp.status_code == status.HTTP_200_OK


def test_database_connection_failure_returns_503_without_silent_fallback() -> None:
    """Verify that when PostgreSQL repository fails, route returns 503 instead of falling back to memory."""
    # Mock PostgresEventRepository that raises DatabaseConnectionError on get
    mock_repo = AsyncMock(spec=BaseEventRepository)
    mock_repo.get = AsyncMock(
        side_effect=DatabaseConnectionError("Could not connect to PostgreSQL server: connection refused")
    )
    mock_repo.connect = AsyncMock()
    mock_repo.disconnect = AsyncMock()

    settings = Settings(storage_backend="memory")
    app = create_app(settings=settings)
    app.state.event_repository = mock_repo
    app.state.event_store = mock_repo
    app.state.event_service = EventService(store=mock_repo, settings=settings)

    with TestClient(app) as client:
        resp = client.get("/api/v1/events/evt_mock_fail")
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = resp.json()
        assert data["error"]["code"] == "DATABASE_UNAVAILABLE"
        # Must not leak connection strings or passwords
        assert "password" not in json.dumps(data).lower()


# ==============================================================================
# 4. PostgreSQL Mock Unit Tests (Parameterized SQL, Rollback, Error Mapping)
# ==============================================================================


@pytest.mark.asyncio
async def test_postgres_parameterized_queries_inspect() -> None:
    """Verify that PostgresEventRepository uses parameterized queries ($1, $2) and no raw string interpolations."""
    settings = Settings(storage_backend="postgres", database_url=LOCAL_PG_URL)
    repo = PostgresEventRepository(settings)

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    repo._pool = mock_pool

    mock_conn.fetchrow.return_value = None

    # Call get
    await repo.get("evt_test_param")

    # Inspect the query issued
    assert mock_conn.fetchrow.called
    call_args = mock_conn.fetchrow.call_args[0]
    query_str = call_args[0]
    param_val = call_args[1]

    assert "$1" in query_str
    assert "evt_test_param" == param_val
    # Query must not contain raw formatted id
    assert "evt_test_param" not in query_str


@pytest.mark.asyncio
async def test_postgres_transaction_rollback_on_failure() -> None:
    """Verify that transactional multi-table updates trigger rollback on error."""
    settings = Settings(storage_backend="postgres", database_url=LOCAL_PG_URL)
    repo = PostgresEventRepository(settings)

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx)

    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    repo._pool = mock_pool

    # Let the profile checks succeed, then fail on the events table insert
    mock_conn.fetchval.return_value = "auth.users"
    mock_conn.execute.side_effect = [
        "INSERT 0 1",  # auth.users
        "INSERT 0 1",  # public.profiles
        asyncpg.ForeignKeyViolationError("violates foreign key"),
    ]

    event = make_test_event_profile()
    with pytest.raises(RepositoryIntegrityError):
        await repo.create(event)

    # Verify transaction context manager was entered and rolled back
    assert mock_conn.transaction.called


@pytest.mark.asyncio
async def test_postgres_connection_failure_mapping() -> None:
    """Verify asyncpg connection errors are wrapped in DatabaseConnectionError."""
    settings = Settings(storage_backend="postgres", database_url="postgresql://user:secret@127.0.0.1:9999/nodb")
    repo = PostgresEventRepository(settings)

    with patch("asyncpg.create_pool", side_effect=OSError("Connection refused")):
        with pytest.raises(DatabaseConnectionError) as exc_info:
            await repo.connect()
        # Ensure password is not leaked in the exception string
        assert "secret" not in str(exc_info.value)


# ==============================================================================
# 5. Live PostgreSQL Integration Tests (Real Database)
# ==============================================================================


@pytest.mark.skipif(not IS_LIVE_PG_AVAILABLE, reason="Local PostgreSQL instance not running")
@pytest.mark.asyncio
async def test_live_postgres_full_lifecycle_and_foreign_keys() -> None:
    """
    Live integration test against local PostgreSQL database (planproof_step1c_test).
    Validates:
    - Real asyncpg connection pool
    - Real schema tables (profiles, events, event_budgets, event_milestone_statuses,
      event_vendor_checklist_items, crisis_recovery_records, crisis_recovery_actions)
    - Cascade deletes
    - Row-to-model data mapping
    """
    settings = Settings(
        storage_backend="postgres",
        database_url=LOCAL_PG_URL,
        database_pool_min_size=1,
        database_pool_max_size=3,
    )
    repo = PostgresEventRepository(settings)
    await repo.connect()

    try:
        # 1. Clean slate
        await repo.clear()
        assert await repo.count() == 0

        # 2. Create EventProfile
        event_id = f"evt_live_{uuid4().hex[:8]}"
        event = make_test_event_profile(event_id=event_id, budget=1800000)
        created = await repo.create(event)
        assert created.event_id == event_id
        assert await repo.count() == 1

        # 3. Retrieve EventProfile
        fetched = await repo.get(event_id)
        assert fetched is not None
        assert fetched.event_id == event_id
        assert fetched.total_budget_inr == 1800000
        assert fetched.city == "Mumbai"

        # 4. Save and Retrieve Event Budget
        budget = EventBudgetBreakdown(
            venue=500000,
            catering=700000,
            decor=250000,
            photo_video=150000,
            entertainment=100000,
            attire_beauty=50000,
            logistics=20000,
            buffer=30000,
            total_budget_inr=1800000,
        )
        saved_budget = await repo.save_budget(event_id, budget)
        assert saved_budget == budget

        fetched_budget = await repo.get_budget(event_id)
        assert fetched_budget is not None
        assert fetched_budget.catering == 700000
        assert fetched_budget.total_budget_inr == 1800000

        # 5. Save and Retrieve Milestone Statuses
        await repo.save_milestone_status(event_id, "MS-01", MilestoneStatus.COMPLETED)
        await repo.save_milestone_status(event_id, "MS-02", MilestoneStatus.PENDING)

        milestones = await repo.get_milestone_statuses(event_id)
        assert milestones.get("MS-01") == MilestoneStatus.COMPLETED
        assert milestones.get("MS-02") == MilestoneStatus.PENDING

        # 6. Save and Retrieve Vendor Checklist Item
        now = datetime.now(timezone.utc)
        v_item = EventVendorChecklistItem(
            id="VND-001",
            category=VendorChecklistCategory.CATERING_REFRESHMENTS,
            title="Book Halwai & Caterer",
            description="Tasting menu and contract confirmation",
            status=VendorChecklistStatus.IN_PROGRESS,
            due_date=date(2026, 11, 10),
            days_before_event=35,
            priority=VendorChecklistPriority.HIGH,
            notes="Vegetarian menu with Jain options",
            vendor_name="Shree Ganesh Caterers",
            booking_status=VendorBookingStatus.CONTACTED,
            created_at=now,
            updated_at=now,
        )
        await repo.save_vendor_checklist_item(event_id, v_item)

        items = await repo.get_vendor_checklist(event_id)
        assert len(items) == 1
        assert items[0].id == "VND-001"
        assert items[0].vendor_name == "Shree Ganesh Caterers"
        assert items[0].booking_status == VendorBookingStatus.CONTACTED

        # 7. Create Crisis Recovery Record & Tracked Actions
        matched = MatchedCrisisScenario(
            scenario_id="CR-LIVE-01",
            is_dataset_match=True,
            crisis_type="vendor_cancellation",
            severity=3,
            event_type=EventType.WEDDING,
            phase="planning",  # type: ignore[arg-type]
            description="Caterer cancelled 30 days prior",
            recommended_fix="Engage pre-vetted backup caterer",
            cost_impact_pct_of_budget=6.0,
            message_target="vendor",  # type: ignore[arg-type]
            synthetic=False,
        )
        recovery_plan = EventCrisisRecoveryResponse(
            event_id=event_id,
            event_type=EventType.WEDDING,
            event_name="Priya & Rohan Sangeet",
            event_phase="planning",  # type: ignore[arg-type]
            matched_scenario=matched,
            crisis_summary="Primary caterer cancelled unexpectedly",
            severity=3,
            affected_area="catering",
            immediate_actions=[
                {
                    "priority": 1,
                    "category": "immediate_safety",
                    "title": "Contact backup caterer",
                    "action": "Call shortlisted backup caterers",
                    "responsible_party": "Lead planner",
                    "timeframe": "Immediate (0-15 mins)",
                }
            ],
            budget_impact={
                "cost_impact_pct": 6.0,
                "estimated_rupee_impact": 108000,
                "affected_categories": ["catering"],
                "existing_buffer_inr": 30000,
                "buffer_sufficient": False,
                "advice": "Emergency reallocation required from decor budget",
            },
            escalation_guidance="Contact alternate vendor roster and lead coordinator.",
        )
        act1 = TrackedRecoveryAction(
            action_id="ACT-LIVE-1",
            recovery_id="REC-LIVE-1",
            title="Call backup caterer list",
            description="Contact top 3 alternate caterers for availability",
            priority=1,
            status=RecoveryActionStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        act2 = TrackedRecoveryAction(
            action_id="ACT-LIVE-2",
            recovery_id="REC-LIVE-1",
            title="Audit advance payment refund",
            description="Send legal notice for prompt advance refund",
            priority=2,
            status=RecoveryActionStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        recovery_record = CrisisRecoveryRecord(
            recovery_id="REC-LIVE-1",
            event_id=event_id,
            crisis_type="vendor_cancellation",
            severity=3,
            description="Caterer cancellation crisis record",
            recovery_plan=recovery_plan,
            source="rules",
            status=RecoveryStatus.OPEN,
            actions=[act1, act2],
            progress=RecoveryProgressSummary(total_actions=2, completed_actions=0),
            total_actions=2,
            completed_actions=0,
            created_at=now,
            updated_at=now,
        )

        saved_rec = await repo.create_recovery_record(event_id, recovery_record)
        assert saved_rec.recovery_id == "REC-LIVE-1"

        records = await repo.list_recovery_records(event_id)
        assert len(records) == 1
        assert len(records[0].actions) == 2

        # 8. Update Recovery Action and verify progress
        upd_action = await repo.update_recovery_action(
            event_id=event_id,
            recovery_id="REC-LIVE-1",
            action_id="ACT-LIVE-1",
            status=RecoveryActionStatus.COMPLETED,
            notes="Contacted backup caterer Mr. Verma; confirmed availability",
        )
        assert upd_action is not None
        assert upd_action.status == RecoveryActionStatus.COMPLETED
        assert upd_action.notes == "Contacted backup caterer Mr. Verma; confirmed availability"

        # 9. Verify full EventProfile retrieval reflects all nested entities
        full_profile = await repo.get(event_id)
        assert full_profile is not None
        assert full_profile.budget is not None
        assert full_profile.budget.total_budget_inr == 1800000
        assert full_profile.milestone_statuses.get("MS-01") == MilestoneStatus.COMPLETED
        assert len(full_profile.vendor_checklist) == 1
        assert len(full_profile.recovery_records) == 1

        # 10. Delete Event and verify ON DELETE CASCADE
        deleted = await repo.delete(event_id)
        assert deleted is True
        assert await repo.get(event_id) is None
        assert await repo.count() == 0

        # Ensure related records in sub-tables were cleaned up
        async with repo.acquire_connection() as conn:
            budget_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.event_budgets WHERE event_id = $1;", event_id
            )
            assert budget_count == 0
            milestone_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.event_milestone_statuses WHERE event_id = $1;", event_id
            )
            assert milestone_count == 0
            vendor_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.event_vendor_checklist_items WHERE event_id = $1;", event_id
            )
            assert vendor_count == 0
            rec_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.crisis_recovery_records WHERE event_id = $1;", event_id
            )
            assert rec_count == 0
            act_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.crisis_recovery_actions WHERE recovery_id = 'REC-LIVE-1';"
            )
            assert act_count == 0

    finally:
        await repo.disconnect()
