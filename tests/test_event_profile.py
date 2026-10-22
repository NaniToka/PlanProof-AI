"""Automated tests for Event Profile model, safe date handling, in-memory store, and API operations."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas import (
    CityTier,
    EventCreateRequest,
    EventListResponse,
    EventProfile,
    EventPlanRequest,
    EventType,
    EventUpdateRequest,
    LanguageCode,
    get_current_ist_date,
    validate_event_date,
)
from app.services.event_service import EventService, EventStore


# ==============================================================================
# 1. Pydantic v2 Schema & Model Validation Tests
# ==============================================================================


def test_event_create_request_minimal_valid() -> None:
    """Verify EventCreateRequest with only required fields uses correct defaults."""
    req = EventCreateRequest(
        event_type=EventType.WEDDING,
        guest_count=150,
        total_budget_inr=1_500_000,
    )
    assert req.event_type == EventType.WEDDING
    assert req.guest_count == 150
    assert req.total_budget_inr == 1_500_000
    assert req.city_tier == CityTier.METRO
    assert req.language == LanguageCode.EN
    assert req.theme_notes == ""
    assert req.city is None
    assert req.event_name is None
    assert req.event_date is None
    assert req.is_in_progress is False


def test_event_create_request_full_valid() -> None:
    """Verify EventCreateRequest with all fields populated."""
    tomorrow = get_current_ist_date() + timedelta(days=1)
    req = EventCreateRequest(
        event_type=EventType.BIRTHDAY,
        guest_count=50,
        total_budget_inr=150_000,
        city_tier=CityTier.TIER2,
        city="Pune",
        event_name="Aarav's 5th Birthday",
        event_date=tomorrow,
        language=LanguageCode.HI,
        theme_notes="Jungle safari theme with kids activities",
        is_in_progress=False,
    )
    assert req.city == "Pune"
    assert req.event_name == "Aarav's 5th Birthday"
    assert req.event_date == tomorrow
    assert req.language == LanguageCode.HI


def test_event_create_request_whitespace_stripping() -> None:
    """Verify that string fields are trimmed and blank optional strings become None."""
    req = EventCreateRequest(
        event_type=EventType.COMMUNITY_EVENT,
        guest_count=300,
        total_budget_inr=500_000,
        city="   Hyderabad   ",
        event_name="   Diwali Mela   ",
    )
    assert req.city == "Hyderabad"
    assert req.event_name == "Diwali Mela"

    # Whitespace-only becomes None
    req2 = EventCreateRequest(
        event_type=EventType.COMMUNITY_EVENT,
        guest_count=300,
        total_budget_inr=500_000,
        city="   ",
        event_name="   ",
    )
    assert req2.city is None
    assert req2.event_name is None


def test_event_create_request_guest_count_boundaries() -> None:
    """Verify guest count boundaries (1 to 2000)."""
    # Valid boundaries
    req_min = EventCreateRequest(event_type=EventType.WEDDING, guest_count=1, total_budget_inr=100_000)
    assert req_min.guest_count == 1
    req_max = EventCreateRequest(event_type=EventType.WEDDING, guest_count=2000, total_budget_inr=100_000)
    assert req_max.guest_count == 2000

    # Below 1 rejected
    with pytest.raises(ValidationError) as exc:
        EventCreateRequest(event_type=EventType.WEDDING, guest_count=0, total_budget_inr=100_000)
    assert "guest_count must be between 1 and 2,000" in str(exc.value)

    # Above 2000 rejected
    with pytest.raises(ValidationError) as exc:
        EventCreateRequest(event_type=EventType.WEDDING, guest_count=2001, total_budget_inr=100_000)
    assert "guest_count must be between 1 and 2,000" in str(exc.value)

    # Negative rejected
    with pytest.raises(ValidationError):
        EventCreateRequest(event_type=EventType.WEDDING, guest_count=-10, total_budget_inr=100_000)


def test_event_create_request_budget_boundaries() -> None:
    """Verify budget boundaries (₹10,000 to ₹50,000,000)."""
    # Valid boundaries
    req_min = EventCreateRequest(event_type=EventType.WEDDING, guest_count=100, total_budget_inr=10_000)
    assert req_min.total_budget_inr == 10_000
    req_max = EventCreateRequest(event_type=EventType.WEDDING, guest_count=100, total_budget_inr=50_000_000)
    assert req_max.total_budget_inr == 50_000_000

    # Below minimum rejected
    with pytest.raises(ValidationError) as exc:
        EventCreateRequest(event_type=EventType.WEDDING, guest_count=100, total_budget_inr=9_999)
    assert "total_budget_inr must be between" in str(exc.value)

    # Above maximum rejected
    with pytest.raises(ValidationError) as exc:
        EventCreateRequest(event_type=EventType.WEDDING, guest_count=100, total_budget_inr=50_000_001)
    assert "total_budget_inr must be between" in str(exc.value)


def test_event_create_request_strict_types() -> None:
    """Verify strict type enforcement: booleans and floats are rejected."""
    # Booleans rejected for integers
    with pytest.raises(ValidationError) as exc:
        EventCreateRequest(event_type=EventType.WEDDING, guest_count=True, total_budget_inr=100_000)  # type: ignore[arg-type]
    assert "guest_count must be an integer, not a boolean" in str(exc.value)

    # Floats rejected for guest_count
    with pytest.raises(ValidationError) as exc:
        EventCreateRequest(event_type=EventType.WEDDING, guest_count=150.5, total_budget_inr=100_000)  # type: ignore[arg-type]
    assert "guest_count must be an integer, not a decimal" in str(exc.value)

    # Floats rejected for budget
    with pytest.raises(ValidationError) as exc:
        EventCreateRequest(event_type=EventType.WEDDING, guest_count=150, total_budget_inr=100000.50)  # type: ignore[arg-type]
    assert "total_budget_inr must be an integer amount in INR, not a decimal" in str(exc.value)


def test_event_create_request_excessive_lengths() -> None:
    """Verify string length constraints are enforced."""
    with pytest.raises(ValidationError):
        EventCreateRequest(
            event_type=EventType.WEDDING,
            guest_count=100,
            total_budget_inr=100_000,
            event_name="A" * 151,
        )

    with pytest.raises(ValidationError):
        EventCreateRequest(
            event_type=EventType.WEDDING,
            guest_count=100,
            total_budget_inr=100_000,
            city="B" * 101,
        )

    with pytest.raises(ValidationError):
        EventCreateRequest(
            event_type=EventType.WEDDING,
            guest_count=100,
            total_budget_inr=100_000,
            theme_notes="C" * 1001,
        )


def test_event_create_request_forbids_extra_fields() -> None:
    """Verify that client cannot pass unexpected or server-generated fields."""
    with pytest.raises(ValidationError) as exc:
        EventCreateRequest.model_validate(
            {
                "event_type": "wedding",
                "guest_count": 100,
                "total_budget_inr": 100_000,
                "event_id": "EV-CLIENT-HACK",
            }
        )
    assert "extra_forbidden" in str(exc.value)

    with pytest.raises(ValidationError):
        EventCreateRequest.model_validate(
            {
                "event_type": "wedding",
                "guest_count": 100,
                "total_budget_inr": 100_000,
                "created_at": "2026-10-22T00:00:00Z",
            }
        )


def test_event_update_request_forbids_extra_fields() -> None:
    """Verify that update requests forbid server-generated or arbitrary fields."""
    with pytest.raises(ValidationError) as exc:
        EventUpdateRequest.model_validate({"event_id": "EV-CLIENT-HACK"})
    assert "extra_forbidden" in str(exc.value)

    with pytest.raises(ValidationError):
        EventUpdateRequest.model_validate({"created_at": "2026-10-22T00:00:00Z"})


def test_event_profile_to_plan_request() -> None:
    """Verify that EventProfile can be converted cleanly into an EventPlanRequest for AI orchestration."""
    now = datetime.now(timezone.utc)
    profile = EventProfile(
        event_id="EV-1234567890AB",
        event_type=EventType.WEDDING,
        event_name="Sharma Wedding",
        city="Jaipur",
        city_tier=CityTier.TIER2,
        event_date=date(2026, 12, 15),
        guest_count=350,
        total_budget_inr=3_500_000,
        language=LanguageCode.EN,
        theme_notes="Royal Rajasthani heritage theme",
        is_in_progress=False,
        created_at=now,
        updated_at=now,
    )
    plan_req = profile.to_plan_request()
    assert isinstance(plan_req, EventPlanRequest)
    assert plan_req.event_type == EventType.WEDDING
    assert plan_req.city == "Jaipur"
    assert plan_req.city_tier == CityTier.TIER2
    assert plan_req.guest_count == 350
    assert plan_req.total_budget_inr == 3_500_000
    assert plan_req.event_name == "Sharma Wedding"
    assert plan_req.event_date == date(2026, 12, 15)


# ==============================================================================
# 2. Date Handling & Validation Tests
# ==============================================================================


def test_validate_event_date_future_accepted() -> None:
    """Verify future date is accepted."""
    ref = date(2026, 10, 22)
    future = date(2026, 11, 1)
    res = validate_event_date(future, allow_past=False, reference_date=ref)
    assert res == future


def test_validate_event_date_today_accepted() -> None:
    """Verify same-day date is accepted."""
    ref = date(2026, 10, 22)
    res = validate_event_date(ref, allow_past=False, reference_date=ref)
    assert res == ref


def test_validate_event_date_past_rejected_for_upcoming() -> None:
    """Verify past date raises ValueError for new upcoming event."""
    ref = date(2026, 10, 22)
    past = date(2026, 10, 21)
    with pytest.raises(ValueError) as exc:
        validate_event_date(past, allow_past=False, reference_date=ref)
    assert "cannot be in the past for an upcoming event" in str(exc.value)
    assert "2026-10-21" in str(exc.value)


def test_validate_event_date_past_accepted_for_in_progress() -> None:
    """Verify past date is allowed when is_in_progress is True (crisis recovery)."""
    ref = date(2026, 10, 22)
    past = date(2026, 10, 15)
    res = validate_event_date(past, allow_past=True, reference_date=ref)
    assert res == past


def test_validate_event_date_none_returns_none() -> None:
    """Verify None input returns None."""
    assert validate_event_date(None) is None


def test_get_current_ist_date() -> None:
    """Verify get_current_ist_date returns an instance of date."""
    d = get_current_ist_date()
    assert isinstance(d, date)


# ==============================================================================
# 3. Ephemeral In-Memory Store (EventStore) Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_event_store_lifecycle() -> None:
    """Verify basic CRUD lifecycle in EventStore."""
    store = EventStore()
    now = datetime.now(timezone.utc)
    profile = EventProfile(
        event_id="EV-TEST001",
        event_type=EventType.WEDDING,
        guest_count=100,
        total_budget_inr=1_000_000,
        created_at=now,
        updated_at=now,
    )

    # 1. Create
    await store.create(profile)
    assert await store.count() == 1

    # 2. Get
    fetched = await store.get("EV-TEST001")
    assert fetched is not None
    assert fetched.event_id == "EV-TEST001"

    # 3. Get non-existent
    assert await store.get("EV-UNKNOWN") is None

    # 4. Update
    updated_profile = profile.model_copy(update={"guest_count": 120})
    res = await store.update("EV-TEST001", updated_profile)
    assert res is not None
    assert res.guest_count == 120

    # 5. Delete
    assert await store.delete("EV-TEST001") is True
    assert await store.delete("EV-TEST001") is False
    assert await store.count() == 0

    # 6. Clear
    await store.create(profile)
    await store.clear()
    assert await store.count() == 0


@pytest.mark.asyncio
async def test_event_store_capacity_eviction() -> None:
    """Verify bounded memory management: FIFO eviction occurs at max capacity."""
    store = EventStore(max_capacity=3)
    now = datetime.now(timezone.utc)

    for i in range(1, 5):
        profile = EventProfile(
            event_id=f"EV-00{i}",
            event_type=EventType.BIRTHDAY,
            guest_count=50,
            total_budget_inr=200_000,
            created_at=now,
            updated_at=now,
        )
        await store.create(profile)

    # Store capacity was 3, so EV-001 must have been evicted
    assert await store.count() == 3
    assert await store.get("EV-001") is None
    assert await store.get("EV-002") is not None
    assert await store.get("EV-003") is not None
    assert await store.get("EV-004") is not None


@pytest.mark.asyncio
async def test_event_store_pagination() -> None:
    """Verify pagination and ordering in EventStore."""
    store = EventStore()
    base_time = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone.utc)

    # Insert 5 events with ascending updated_at
    for i in range(5):
        t = base_time + timedelta(minutes=i)
        p = EventProfile(
            event_id=f"EV-PAGE-{i}",
            event_type=EventType.WEDDING,
            guest_count=100 + i,
            total_budget_inr=500_000,
            created_at=t,
            updated_at=t,
        )
        await store.create(p)

    # Page 1: limit 2 -> returns most recently updated first (EV-PAGE-4, EV-PAGE-3)
    page1, total = await store.list(skip=0, limit=2)
    assert total == 5
    assert len(page1) == 2
    assert page1[0].event_id == "EV-PAGE-4"
    assert page1[1].event_id == "EV-PAGE-3"

    # Page 2: skip 2, limit 2
    page2, total = await store.list(skip=2, limit=2)
    assert total == 5
    assert len(page2) == 2
    assert page2[0].event_id == "EV-PAGE-2"
    assert page2[1].event_id == "EV-PAGE-1"

    # Page 3: skip 4, limit 2
    page3, total = await store.list(skip=4, limit=2)
    assert total == 5
    assert len(page3) == 1
    assert page3[0].event_id == "EV-PAGE-0"


# ==============================================================================
# 4. Domain Service (EventService) Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_event_service_create_event_and_budget() -> None:
    """Verify that EventService generates server fields and attaches deterministic budget allocations."""
    service = EventService()
    tomorrow = get_current_ist_date() + timedelta(days=1)
    req = EventCreateRequest(
        event_type=EventType.WEDDING,
        guest_count=200,
        total_budget_inr=2_000_000,
        city_tier=CityTier.METRO,
        city="Delhi",
        event_name="Kapoor Wedding",
        event_date=tomorrow,
    )
    profile = await service.create_event(req)

    # Server-generated ID
    assert profile.event_id.startswith("EV-")
    assert len(profile.event_id) == 15  # EV- + 12 hex chars

    # Server-generated timestamps
    assert profile.created_at.tzinfo == timezone.utc
    assert profile.updated_at.tzinfo == timezone.utc

    # Deterministic budget calculation attached
    assert profile.budget is not None
    assert profile.budget.total_budget_inr == 2_000_000
    cat_sum = (
        profile.budget.venue
        + profile.budget.catering
        + profile.budget.decor
        + profile.budget.photo_video
        + profile.budget.attire_beauty
        + profile.budget.entertainment
        + profile.budget.logistics
        + profile.budget.buffer
    )
    assert cat_sum == 2_000_000


@pytest.mark.asyncio
async def test_event_service_update_event_recomputes_budget_on_budget_change() -> None:
    """Verify that modifying total_budget_inr recalculates the budget allocations."""
    service = EventService()
    req = EventCreateRequest(
        event_type=EventType.WEDDING,
        guest_count=100,
        total_budget_inr=1_000_000,
    )
    profile = await service.create_event(req)
    assert profile.budget is not None
    assert profile.budget.total_budget_inr == 1_000_000
    initial_updated_at = profile.updated_at

    # Update budget to ₹2,500,000
    update_req = EventUpdateRequest(total_budget_inr=2_500_000)
    updated = await service.update_event(profile.event_id, update_req)
    assert updated is not None
    assert updated.event_id == profile.event_id  # Immutable ID
    assert updated.created_at == profile.created_at  # Immutable creation timestamp
    assert updated.updated_at >= initial_updated_at  # Updated timestamp
    assert updated.total_budget_inr == 2_500_000
    assert updated.budget is not None
    assert updated.budget.total_budget_inr == 2_500_000
    cat_sum = (
        updated.budget.venue
        + updated.budget.catering
        + updated.budget.decor
        + updated.budget.photo_video
        + updated.budget.attire_beauty
        + updated.budget.entertainment
        + updated.budget.logistics
        + updated.budget.buffer
    )
    assert cat_sum == 2_500_000


@pytest.mark.asyncio
async def test_event_service_update_event_keeps_budget_when_metadata_updated() -> None:
    """Verify updating non-budget fields preserves the existing budget breakdown."""
    service = EventService()
    req = EventCreateRequest(
        event_type=EventType.WEDDING,
        guest_count=100,
        total_budget_inr=1_000_000,
    )
    profile = await service.create_event(req)
    original_budget = profile.budget

    update_req = EventUpdateRequest(event_name="Renamed Gala Event")
    updated = await service.update_event(profile.event_id, update_req)
    assert updated is not None
    assert updated.event_name == "Renamed Gala Event"
    assert updated.budget == original_budget


@pytest.mark.asyncio
async def test_event_service_privacy_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Verify logging does not expose customer theme notes or PII."""
    service = EventService()
    req = EventCreateRequest(
        event_type=EventType.WEDDING,
        guest_count=150,
        total_budget_inr=1_000_000,
        theme_notes="Confidential: Groom's uncle dislikes loud music; family secret recipes only.",
    )
    with caplog.at_level(logging.INFO):
        profile = await service.create_event(req)

    # Check logs
    all_log_text = " ".join(record.message for record in caplog.records)
    assert profile.event_id in all_log_text
    assert "wedding" in all_log_text
    # Sensitive customer text MUST NOT be in logs
    assert "Confidential" not in all_log_text
    assert "Groom's uncle" not in all_log_text
    assert "family secret" not in all_log_text


# ==============================================================================
# 5. REST API Integration Tests
# ==============================================================================


def test_api_create_event_201_success(client: TestClient) -> None:
    """Verify POST /api/v1/events creates profile with 201 status and deterministic budget."""
    tomorrow = (get_current_ist_date() + timedelta(days=2)).isoformat()
    payload = {
        "event_type": "wedding",
        "guest_count": 250,
        "total_budget_inr": 2_500_000,
        "city_tier": "metro",
        "city": "Bengaluru",
        "event_name": "Rohan & Priya Wedding",
        "event_date": tomorrow,
        "language": "en",
        "theme_notes": "Pastel florals and eco-friendly mandap",
    }
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["event_id"].startswith("EV-")
    assert data["event_name"] == "Rohan & Priya Wedding"
    assert data["city"] == "Bengaluru"
    assert data["guest_count"] == 250
    assert data["total_budget_inr"] == 2_500_000
    assert "created_at" in data
    assert "updated_at" in data
    assert data["budget"] is not None
    assert data["budget"]["total_budget_inr"] == 2_500_000


def test_api_create_event_validation_errors(client: TestClient) -> None:
    """Verify POST /api/v1/events rejects invalid inputs with 422 standard error."""
    # Out of bounds guest count
    res1 = client.post(
        "/api/v1/events",
        json={"event_type": "wedding", "guest_count": 5000, "total_budget_inr": 1_000_000},
    )
    assert res1.status_code == 422
    err1 = res1.json()["error"]
    assert err1["code"] == "VALIDATION_ERROR"

    # Out of bounds budget
    res2 = client.post(
        "/api/v1/events",
        json={"event_type": "wedding", "guest_count": 100, "total_budget_inr": 5_000},
    )
    assert res2.status_code == 422
    err2 = res2.json()["error"]
    assert err2["code"] == "VALIDATION_ERROR"

    # Invalid event type
    res3 = client.post(
        "/api/v1/events",
        json={"event_type": "carnival", "guest_count": 100, "total_budget_inr": 100_000},
    )
    assert res3.status_code == 422


def test_api_create_event_rejects_client_event_id(client: TestClient) -> None:
    """Verify POST /api/v1/events forbids client-provided event_id or timestamps."""
    res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 100_000,
            "event_id": "EV-MALICIOUS-INJECTION",
        },
    )
    assert res.status_code == 422
    assert "extra_forbidden" in str(res.json())


def test_api_create_event_date_handling(client: TestClient) -> None:
    """Verify date handling in API: past date rejected unless is_in_progress=True."""
    past = (get_current_ist_date() - timedelta(days=5)).isoformat()

    # Past date with is_in_progress=False -> 422
    res_past = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 500_000,
            "event_date": past,
            "is_in_progress": False,
        },
    )
    assert res_past.status_code == 422

    # Past date with is_in_progress=True -> 201 Created (crisis recovery support)
    res_crisis = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 500_000,
            "event_date": past,
            "is_in_progress": True,
        },
    )
    assert res_crisis.status_code == 201
    assert res_crisis.json()["is_in_progress"] is True
    assert res_crisis.json()["event_date"] == past


def test_api_get_event_endpoints(client: TestClient) -> None:
    """Verify GET /api/v1/events/{event_id} success and 404 behavior."""
    # 1. Create an event
    create_res = client.post(
        "/api/v1/events",
        json={"event_type": "birthday", "guest_count": 40, "total_budget_inr": 80_000},
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    # 2. Get the event -> 200
    get_res = client.get(f"/api/v1/events/{event_id}")
    assert get_res.status_code == 200
    assert get_res.json()["event_id"] == event_id
    assert get_res.json()["event_type"] == "birthday"

    # 3. Get non-existent event -> 404 standard envelope
    missing_res = client.get("/api/v1/events/EV-NONEXISTENT")
    assert missing_res.status_code == 404
    err = missing_res.json()["error"]
    assert err["code"] == "HTTP_ERROR"
    assert "not found" in err["message"].lower()


def test_api_patch_event_endpoints(client: TestClient) -> None:
    """Verify PATCH /api/v1/events/{event_id} partial updates and budget recalculation."""
    # 1. Create an event
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 1_000_000,
            "event_name": "Original Name",
        },
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    # 2. Update name only -> 200
    patch_res = client.patch(
        f"/api/v1/events/{event_id}",
        json={"event_name": "Updated Name"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["event_name"] == "Updated Name"
    assert patch_res.json()["total_budget_inr"] == 1_000_000

    # 3. Update budget -> triggers automatic rebalance/recalculation
    patch_budget_res = client.patch(
        f"/api/v1/events/{event_id}",
        json={"total_budget_inr": 3_000_000},
    )
    assert patch_budget_res.status_code == 200
    data = patch_budget_res.json()
    assert data["total_budget_inr"] == 3_000_000
    assert data["budget"]["total_budget_inr"] == 3_000_000

    # 4. Patch non-existent -> 404
    missing_patch = client.patch(
        "/api/v1/events/EV-UNKNOWN",
        json={"event_name": "Ghost Event"},
    )
    assert missing_patch.status_code == 404

    # 5. Patch with immutable field -> 422
    tamper_res = client.patch(
        f"/api/v1/events/{event_id}",
        json={"event_id": "EV-MODIFIED"},
    )
    assert tamper_res.status_code == 422


def test_api_list_events_pagination(client: TestClient) -> None:
    """Verify GET /api/v1/events returns paginated results."""
    # Create 3 events
    for i in range(3):
        client.post(
            "/api/v1/events",
            json={
                "event_type": "wedding",
                "guest_count": 100 + i * 10,
                "total_budget_inr": 1_000_000,
                "event_name": f"Event Batch {i}",
            },
        )

    # Fetch page of 2
    res = client.get("/api/v1/events?skip=0&limit=2")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 3
    assert data["skip"] == 0
    assert data["limit"] == 2
    assert len(data["events"]) == 2

    # Fetch offset
    res2 = client.get("/api/v1/events?skip=2&limit=2")
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["events"]) >= 1

    # Invalid pagination query params -> 422
    bad_limit = client.get("/api/v1/events?limit=150")
    assert bad_limit.status_code == 422

    bad_skip = client.get("/api/v1/events?skip=-5")
    assert bad_skip.status_code == 422


def test_api_patch_event_validation_errors(client: TestClient) -> None:
    """Verify PATCH /api/v1/events/{event_id} rejects invalid updates with 422."""
    create_res = client.post(
        "/api/v1/events",
        json={"event_type": "wedding", "guest_count": 100, "total_budget_inr": 1_000_000},
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    # Reject out-of-bounds guest count
    res_bad_guests = client.patch(f"/api/v1/events/{event_id}", json={"guest_count": 3000})
    assert res_bad_guests.status_code == 422

    # Reject out-of-bounds budget
    res_bad_budget = client.patch(f"/api/v1/events/{event_id}", json={"total_budget_inr": 500})
    assert res_bad_budget.status_code == 422

    # Reject past date for upcoming event
    past = (get_current_ist_date() - timedelta(days=10)).isoformat()
    res_bad_date = client.patch(f"/api/v1/events/{event_id}", json={"event_date": past})
    assert res_bad_date.status_code == 422

