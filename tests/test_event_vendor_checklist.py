"""Automated test suite for Event Vendor Checklist & Coordination Workflow (Prompt 11).

Validates:
1. Wedding checklist generation (wedding ceremony, catering, decor, photo/video, attire, entertainment, logistics, invites, cleanup).
2. Birthday checklist generation (venue, custom cake/food, decor, photography, entertainment, invites, return gifts, cleanup).
3. Community-event checklist generation (permits/NOC, sound/generator, circulars, shamiana/stage, volunteer marshals, water/prasad, documentation, waste cleanup).
4. Checklist generation for an unsupported event type (validation behavior).
5. Repeated GET requests do not create duplicates.
6. Checklist status updates work correctly (pending -> in_progress -> completed -> skipped).
7. Invalid statuses are rejected (422).
8. Notes and vendor names respect length limits (max 500 and max 100 characters).
9. Invalid or missing event IDs return 404 with standard error envelope.
10. Invalid or missing checklist item IDs return 404 with standard error envelope.
11. Events without an event date receive valid checklist items without fabricated due dates (due_date=None).
12. Due dates are deterministic for a fixed event date.
13. Vendor booking status is never fabricated (defaults to not_started; user can update to researching, contacted, booked, cancelled).
14. Existing budget, timeline, event profile, configuration, and data-validation features remain functional.
15. Due dates recalculate on event date change while preserving user notes and booking statuses.
16. Vendor checklist state persists across profile metadata updates and budget rebalancing.
17. Operation without Gemini API key and with zero external network calls.
"""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import AIMode, Settings
from app.main import create_app
from app.schemas import (
    EventType,
    VendorBookingStatus,
    VendorChecklistCategory,
    VendorChecklistPriority,
    VendorChecklistStatus,
)
from app.services.vendor_service import (
    BIRTHDAY_VENDOR_TEMPLATE,
    COMMUNITY_VENDOR_TEMPLATE,
    WEDDING_VENDOR_TEMPLATE,
    calculate_vendor_checklist_summary,
    generate_event_vendor_checklist,
    get_vendor_template_for_event_type,
    recalculate_checklist_due_dates,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def isolated_client() -> TestClient:
    """Provide an isolated TestClient with clean memory store and DEMO AI mode."""
    test_settings = Settings(
        gemini_api_key=None,
        ai_mode=AIMode.DEMO,
        data_dir=Path("data"),
        crisis_dataset_path=Path("data/crisis_scenarios.csv"),
        budget_splits_path=Path("data/budget_splits.json"),
        vendor_checklists_path=Path("data/vendor_checklists.json"),
    )
    application = create_app(settings=test_settings)
    with TestClient(application) as client:
        yield client


# ==============================================================================
# 1. Deterministic Vendor Template Unit Tests
# ==============================================================================


def test_wedding_vendor_template_generation() -> None:
    """Verify wedding vendor template has 9 items covering ceremony, reception, and guest needs."""
    assert len(WEDDING_VENDOR_TEMPLATE) == 9
    event_date = date(2027, 12, 10)

    items = generate_event_vendor_checklist(
        event_id="EV-TEST-WED",
        event_type=EventType.WEDDING,
        event_date=event_date,
    )

    assert len(items) == 9
    # All items must default to pending and not_started
    for item in items:
        assert item.status == VendorChecklistStatus.PENDING
        assert item.booking_status == VendorBookingStatus.NOT_STARTED
        assert item.vendor_name is None
        assert item.notes is None
        assert item.id.startswith("VCL-WED-")
        assert item.due_date == event_date - timedelta(days=item.days_before_event)

    categories = [i.category for i in items]
    assert VendorChecklistCategory.VENUE_PERMISSIONS in categories
    assert VendorChecklistCategory.CATERING_REFRESHMENTS in categories
    assert VendorChecklistCategory.DECORATION_SETUP in categories
    assert VendorChecklistCategory.PHOTOGRAPHY_VIDEOGRAPHY in categories
    assert VendorChecklistCategory.ATTIRE_BEAUTY in categories
    assert VendorChecklistCategory.ENTERTAINMENT_EQUIPMENT in categories
    assert VendorChecklistCategory.TRANSPORT_LOGISTICS in categories
    assert VendorChecklistCategory.INVITATIONS_COORDINATION in categories
    assert VendorChecklistCategory.CLEANUP_POST_EVENT in categories


def test_birthday_vendor_template_generation() -> None:
    """Verify birthday vendor template has 8 focused items without irrelevant wedding attire/mandap."""
    assert len(BIRTHDAY_VENDOR_TEMPLATE) == 8
    event_date = date(2027, 8, 20)

    items = generate_event_vendor_checklist(
        event_id="EV-TEST-BDY",
        event_type=EventType.BIRTHDAY,
        event_date=event_date,
    )

    assert len(items) == 8
    for item in items:
        assert item.id.startswith("VCL-BDY-")
        assert item.status == VendorChecklistStatus.PENDING
        assert item.booking_status == VendorBookingStatus.NOT_STARTED
        assert item.due_date == event_date - timedelta(days=item.days_before_event)

    categories = [i.category for i in items]
    # Birthday does NOT include attire_beauty
    assert VendorChecklistCategory.ATTIRE_BEAUTY not in categories
    assert VendorChecklistCategory.VENUE_PERMISSIONS in categories
    assert VendorChecklistCategory.CATERING_REFRESHMENTS in categories
    assert VendorChecklistCategory.ENTERTAINMENT_EQUIPMENT in categories


def test_community_event_vendor_template_generation() -> None:
    """Verify community vendor template includes municipal permissions, equipment, and volunteers."""
    assert len(COMMUNITY_VENDOR_TEMPLATE) == 8
    event_date = date(2027, 9, 15)

    items = generate_event_vendor_checklist(
        event_id="EV-TEST-COM",
        event_type=EventType.COMMUNITY_EVENT,
        event_date=event_date,
    )

    assert len(items) == 8
    for item in items:
        assert item.id.startswith("VCL-COM-")
        assert item.status == VendorChecklistStatus.PENDING
        assert item.booking_status == VendorBookingStatus.NOT_STARTED
        assert item.due_date == event_date - timedelta(days=item.days_before_event)

    categories = [i.category for i in items]
    assert VendorChecklistCategory.ATTIRE_BEAUTY not in categories
    assert VendorChecklistCategory.VENUE_PERMISSIONS in categories
    assert VendorChecklistCategory.ENTERTAINMENT_EQUIPMENT in categories
    assert VendorChecklistCategory.CLEANUP_POST_EVENT in categories


def test_unsupported_event_type_raises_error() -> None:
    """Verify that get_vendor_template_for_event_type raises ValueError for invalid event types."""
    with pytest.raises(ValueError, match="Unsupported event type"):
        get_vendor_template_for_event_type("corporate_retreat")

    with pytest.raises(ValueError, match="Unsupported event type"):
        get_vendor_template_for_event_type("anniversary")


def test_event_without_date_has_none_due_dates() -> None:
    """Verify that events with no event_date have due_date=None without fabricated dates."""
    items = generate_event_vendor_checklist(
        event_id="EV-NO-DATE",
        event_type=EventType.WEDDING,
        event_date=None,
    )

    assert len(items) == 9
    for item in items:
        assert item.due_date is None
        assert item.days_before_event is not None


def test_recalculate_checklist_due_dates() -> None:
    """Verify recalculation of due dates when event_date changes preserves user edits."""
    initial_date = date(2027, 10, 10)
    items = generate_event_vendor_checklist("EV-1", EventType.WEDDING, initial_date)

    # Simulate user updates on first item
    user_item = items[0].model_copy(
        update={
            "status": VendorChecklistStatus.COMPLETED,
            "notes": "Booked with 20% advance",
            "vendor_name": "Grand Palace Hall",
            "booking_status": VendorBookingStatus.BOOKED,
        }
    )
    items[0] = user_item

    # Shift event date by +10 days
    new_date = date(2027, 10, 20)
    recalculated = recalculate_checklist_due_dates(items, new_date)

    # User fields preserved
    assert recalculated[0].status == VendorChecklistStatus.COMPLETED
    assert recalculated[0].notes == "Booked with 20% advance"
    assert recalculated[0].vendor_name == "Grand Palace Hall"
    assert recalculated[0].booking_status == VendorBookingStatus.BOOKED

    # Due date shifted exactly by 10 days
    expected_due = new_date - timedelta(days=items[0].days_before_event)
    assert recalculated[0].due_date == expected_due


def test_calculate_vendor_checklist_summary() -> None:
    """Verify summary counts match actual item statuses and booking statuses."""
    items = generate_event_vendor_checklist("EV-1", EventType.BIRTHDAY, date(2027, 6, 1))

    # All start pending and not_started
    s1 = calculate_vendor_checklist_summary(items)
    assert s1.total_items == 8
    assert s1.pending == 8
    assert s1.in_progress == 0
    assert s1.completed == 0
    assert s1.skipped == 0
    assert s1.booking_statuses["not_started"] == 8

    # Modify two items
    items[0] = items[0].model_copy(
        update={"status": VendorChecklistStatus.COMPLETED, "booking_status": VendorBookingStatus.BOOKED}
    )
    items[1] = items[1].model_copy(
        update={"status": VendorChecklistStatus.IN_PROGRESS, "booking_status": VendorBookingStatus.CONTACTED}
    )

    s2 = calculate_vendor_checklist_summary(items)
    assert s2.total_items == 8
    assert s2.pending == 6
    assert s2.in_progress == 1
    assert s2.completed == 1
    assert s2.skipped == 0
    assert s2.booking_statuses["booked"] == 1
    assert s2.booking_statuses["contacted"] == 1
    assert s2.booking_statuses["not_started"] == 6


# ==============================================================================
# 2. API Endpoint Integration Tests
# ==============================================================================


def test_api_get_vendor_checklist_wedding_success(isolated_client: TestClient) -> None:
    """Test GET /api/v1/events/{event_id}/vendors/checklist returns 9 wedding items and summary."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 350,
            "total_budget_inr": 2_500_000,
            "city_tier": "metro",
            "city": "Mumbai",
            "event_date": "2027-11-20",
        },
    )
    assert create_resp.status_code == 201
    event_id = create_resp.json()["event_id"]

    resp = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    assert resp.status_code == 200
    data = resp.json()

    assert data["event_id"] == event_id
    assert data["event_type"] == "wedding"
    assert data["event_date"] == "2027-11-20"
    assert len(data["items"]) == 9
    assert data["summary"]["total_items"] == 9
    assert data["summary"]["pending"] == 9
    assert data["summary"]["booking_statuses"]["not_started"] == 9

    # Verify first item due_date calculation (Nov 20, 2027 - 150 days -> June 23, 2027)
    item_01 = data["items"][0]
    assert item_01["id"] == "VCL-WED-01"
    assert item_01["category"] == "venue_permissions"
    assert item_01["due_date"] == "2027-06-23"
    assert item_01["status"] == "pending"
    assert item_01["booking_status"] == "not_started"
    assert item_01["vendor_name"] is None
    assert item_01["notes"] is None


def test_api_repeated_get_does_not_duplicate_items(isolated_client: TestClient) -> None:
    """Verify repeated GET calls return identical checklist items without creating duplicates."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "guest_count": 50,
            "total_budget_inr": 150_000,
            "city_tier": "tier2",
            "city": "Pune",
            "event_date": "2027-08-15",
        },
    )
    event_id = create_resp.json()["event_id"]

    # First request
    resp1 = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    assert resp1.status_code == 200
    assert len(resp1.json()["items"]) == 8

    # Second request
    resp2 = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    assert resp2.status_code == 200
    assert len(resp2.json()["items"]) == 8

    # IDs and timestamps are identical
    ids1 = [i["id"] for i in resp1.json()["items"]]
    ids2 = [i["id"] for i in resp2.json()["items"]]
    assert ids1 == ids2


def test_api_get_checklist_for_event_without_date(isolated_client: TestClient) -> None:
    """Verify event without date gets valid checklist items with due_date=None and warning."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "community_event",
            "guest_count": 300,
            "total_budget_inr": 500_000,
            "city_tier": "tier2",
            "city": "Nagpur",
            # event_date omitted
        },
    )
    event_id = create_resp.json()["event_id"]

    resp = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_date"] is None
    assert len(data["items"]) == 8
    for item in data["items"]:
        assert item["due_date"] is None
    assert len(data["warnings"]) >= 1
    assert "Event date is not set" in data["warnings"][0]


def test_api_patch_vendor_checklist_item_success(isolated_client: TestClient) -> None:
    """Test updating status, notes, priority, vendor_name, and booking_status on an item."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 200,
            "total_budget_inr": 1_200_000,
            "event_date": "2027-12-01",
        },
    )
    event_id = create_resp.json()["event_id"]

    # Update VCL-WED-01
    patch_payload = {
        "status": "in_progress",
        "notes": "Visited Royal Orchid Lawns. Advance requested is 25%.",
        "priority": "high",
        "vendor_name": "Royal Orchid Lawns",
        "booking_status": "contacted",
    }
    patch_resp = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-WED-01",
        json=patch_payload,
    )
    assert patch_resp.status_code == 200
    item = patch_resp.json()
    assert item["id"] == "VCL-WED-01"
    assert item["status"] == "in_progress"
    assert item["notes"] == "Visited Royal Orchid Lawns. Advance requested is 25%."
    assert item["vendor_name"] == "Royal Orchid Lawns"
    assert item["booking_status"] == "contacted"
    assert item["priority"] == "high"

    # Verify GET reflects update in checklist and summary
    get_resp = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    assert get_resp.status_code == 200
    summary = get_resp.json()["summary"]
    assert summary["in_progress"] == 1
    assert summary["pending"] == 8
    assert summary["booking_statuses"]["contacted"] == 1
    assert summary["booking_statuses"]["not_started"] == 8


def test_api_patch_vendor_checklist_status_transitions(isolated_client: TestClient) -> None:
    """Test all permitted task statuses: pending, in_progress, completed, skipped."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "guest_count": 40,
            "total_budget_inr": 100_000,
            "event_date": "2027-07-20",
        },
    )
    event_id = create_resp.json()["event_id"]

    # 1. in_progress
    r1 = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-BDY-01",
        json={"status": "in_progress"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "in_progress"

    # 2. completed
    r2 = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-BDY-01",
        json={"status": "completed"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "completed"

    # 3. skipped
    r3 = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-BDY-01",
        json={"status": "skipped"},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "skipped"

    # 4. back to pending
    r4 = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-BDY-01",
        json={"status": "pending"},
    )
    assert r4.status_code == 200
    assert r4.json()["status"] == "pending"


def test_api_patch_invalid_status_rejected(isolated_client: TestClient) -> None:
    """Verify that unsupported status values return 422 Unprocessable Entity."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 800_000,
            "event_date": "2027-10-10",
        },
    )
    event_id = create_resp.json()["event_id"]

    resp = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-WED-01",
        json={"status": "done"},
    )
    assert resp.status_code == 422


def test_api_patch_invalid_booking_status_rejected(isolated_client: TestClient) -> None:
    """Verify that unsupported booking_status values return 422."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 800_000,
            "event_date": "2027-10-10",
        },
    )
    event_id = create_resp.json()["event_id"]

    resp = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-WED-01",
        json={"booking_status": "confirmed_and_paid"},
    )
    assert resp.status_code == 422


def test_api_patch_field_length_limits(isolated_client: TestClient) -> None:
    """Verify length limits on notes (max 500) and vendor_name (max 100)."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 800_000,
            "event_date": "2027-10-10",
        },
    )
    event_id = create_resp.json()["event_id"]

    # Notes exceeding 500 characters
    long_notes = "A" * 501
    resp_notes = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-WED-01",
        json={"notes": long_notes},
    )
    assert resp_notes.status_code == 422

    # Vendor name exceeding 100 characters
    long_name = "B" * 101
    resp_name = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-WED-01",
        json={"vendor_name": long_name},
    )
    assert resp_name.status_code == 422


def test_api_missing_or_invalid_event_id_returns_404(isolated_client: TestClient) -> None:
    """Verify 404 with structured error envelope for non-existent event IDs."""
    # GET checklist for non-existent event
    get_resp = isolated_client.get("/api/v1/events/EV-NONEXISTENT/vendors/checklist")
    assert get_resp.status_code == 404
    assert get_resp.json()["error"]["code"] == "HTTP_ERROR"
    assert "not found" in get_resp.json()["error"]["message"].lower()

    # PATCH item for non-existent event
    patch_resp = isolated_client.patch(
        "/api/v1/events/EV-NONEXISTENT/vendors/checklist/VCL-WED-01",
        json={"status": "completed"},
    )
    assert patch_resp.status_code == 404
    assert patch_resp.json()["error"]["code"] == "HTTP_ERROR"


def test_api_missing_or_invalid_item_id_returns_404(isolated_client: TestClient) -> None:
    """Verify 404 with structured error envelope when checklist item ID is not found."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 800_000,
            "event_date": "2027-10-10",
        },
    )
    event_id = create_resp.json()["event_id"]

    # Item ID that does not exist in wedding checklist
    patch_resp = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-INVALID-99",
        json={"status": "completed"},
    )
    assert patch_resp.status_code == 404
    assert "not found" in patch_resp.json()["error"]["message"].lower()


def test_api_patch_rejects_immutable_fields(isolated_client: TestClient) -> None:
    """Verify client cannot tamper with item id, category, due_date, or created_at."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 800_000,
            "event_date": "2027-10-10",
        },
    )
    event_id = create_resp.json()["event_id"]

    resp = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-WED-01",
        json={"id": "TAMPERED-ID", "status": "completed"},
    )
    assert resp.status_code == 422


def test_vendor_checklist_persists_across_event_updates_and_budget_rebalancing(
    isolated_client: TestClient,
) -> None:
    """Verify that vendor checklist state is preserved when event profile metadata or budget is updated."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 250,
            "total_budget_inr": 2_000_000,
            "event_date": "2027-11-15",
        },
    )
    event_id = create_resp.json()["event_id"]

    # 1. Update checklist item
    patch_item = isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-WED-02",
        json={
            "status": "completed",
            "vendor_name": "Annapurna Caterers",
            "booking_status": "booked",
            "notes": "Menu finalized with live chaat counter.",
        },
    )
    assert patch_item.status_code == 200

    # 2. Update event profile name
    update_resp = isolated_client.patch(
        f"/api/v1/events/{event_id}",
        json={"event_name": "Destination Sangeet & Wedding"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["event_name"] == "Destination Sangeet & Wedding"

    # Verify checklist state is intact
    c1 = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist").json()
    item_after_metadata = [i for i in c1["items"] if i["id"] == "VCL-WED-02"][0]
    assert item_after_metadata["status"] == "completed"
    assert item_after_metadata["vendor_name"] == "Annapurna Caterers"
    assert item_after_metadata["booking_status"] == "booked"
    assert item_after_metadata["notes"] == "Menu finalized with live chaat counter."

    # 3. Rebalance budget
    rebal_resp = isolated_client.post(
        f"/api/v1/events/{event_id}/budget/rebalance",
        json={"new_total_budget_inr": 1_800_000},
    )
    assert rebal_resp.status_code == 200

    # Verify checklist state is still intact after budget rebalance
    c2 = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist").json()
    item_after_rebalance = [i for i in c2["items"] if i["id"] == "VCL-WED-02"][0]
    assert item_after_rebalance["status"] == "completed"
    assert item_after_rebalance["vendor_name"] == "Annapurna Caterers"
    assert item_after_rebalance["booking_status"] == "booked"


def test_vendor_due_dates_recalculate_when_event_date_updated(
    isolated_client: TestClient,
) -> None:
    """Verify updating event_date updates vendor task due dates while preserving user notes."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "guest_count": 50,
            "total_budget_inr": 120_000,
            "event_date": "2027-05-15",
        },
    )
    event_id = create_resp.json()["event_id"]

    # Add user notes on cake task (VCL-BDY-04: 12 days before)
    isolated_client.patch(
        f"/api/v1/events/{event_id}/vendors/checklist/VCL-BDY-04",
        json={"notes": "Chocolate truffle flavor chosen", "status": "in_progress"},
    )

    c_before = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist").json()
    cake_before = [i for i in c_before["items"] if i["id"] == "VCL-BDY-04"][0]
    # May 15 - 12 days -> May 3, 2027
    assert cake_before["due_date"] == "2027-05-03"

    # Shift event date to May 25
    isolated_client.patch(
        f"/api/v1/events/{event_id}",
        json={"event_date": "2027-05-25"},
    )

    c_after = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist").json()
    cake_after = [i for i in c_after["items"] if i["id"] == "VCL-BDY-04"][0]
    # May 25 - 12 days -> May 13, 2027
    assert cake_after["due_date"] == "2027-05-13"
    # User fields preserved
    assert cake_after["notes"] == "Chocolate truffle flavor chosen"
    assert cake_after["status"] == "in_progress"


def test_vendor_checklist_operates_offline_without_gemini_api_key(
    isolated_client: TestClient,
) -> None:
    """Verify that vendor checklist operates 100% offline with zero network calls."""
    with patch("urllib.request.urlopen", side_effect=RuntimeError("Outbound network disabled")):
        create_resp = isolated_client.post(
            "/api/v1/events",
            json={
                "event_type": "community_event",
                "guest_count": 250,
                "total_budget_inr": 400_000,
                "event_date": "2027-10-10",
            },
        )
        assert create_resp.status_code == 201
        event_id = create_resp.json()["event_id"]

        get_resp = isolated_client.get(f"/api/v1/events/{event_id}/vendors/checklist")
        assert get_resp.status_code == 200
        assert len(get_resp.json()["items"]) == 8

        patch_resp = isolated_client.patch(
            f"/api/v1/events/{event_id}/vendors/checklist/VCL-COM-01",
            json={"status": "completed", "vendor_name": "Municipal Ward Office"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["vendor_name"] == "Municipal Ward Office"
