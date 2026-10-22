"""Automated test suite for Event Timeline and Milestone Scheduling (Prompt 10).

Validates:
1. Wedding timeline generation.
2. Birthday timeline generation.
3. Community-event timeline generation.
4. Unknown event returns 404.
5. Missing event date is handled clearly.
6. Correct deadline calculations (event_date - timedelta(days=days_before_event)).
7. Chronological sorting (earliest due date first).
8. Correct days_before_event values and non-negative lead times.
9. Leap-year dates (e.g., February 29 calculations).
10. Month and year boundaries (transitions across year-end).
11. Events scheduled soon, with some deadlines already passed (is_overdue and warnings).
12. Stable milestone identifiers (M-WED-xx, M-BDY-xx, M-COM-xx).
13. Duplicate milestone prevention in schema validators.
14. Invalid milestone status rejection (422).
15. Unknown milestone ID handling (404).
16. Completed milestones retain their due dates and are not overdue.
17. Operation without a Gemini API key.
18. Demo mode makes zero external API calls.
19. Existing event profile and budget features remain functional.
20. Milestone completion status persists across profile updates and budget rebalancing.
"""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import AIMode, Settings
from app.main import create_app
from app.schemas import (
    CityTier,
    EventMilestone,
    EventTimelineScheduleResponse,
    EventType,
    MilestoneCategory,
    MilestonePriority,
    MilestoneStatus,
)
from app.services.timeline import (
    BIRTHDAY_TIMELINE_TEMPLATE,
    COMMUNITY_EVENT_TIMELINE_TEMPLATE,
    WEDDING_TIMELINE_TEMPLATE,
    generate_event_timeline_schedule,
    get_template_for_event_type,
)


# ==============================================================================
# Test Fixtures & Helpers
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
# 1. Deterministic Timeline Template & Generator Unit Tests
# ==============================================================================


def test_wedding_timeline_generation_unit() -> None:
    """Verify wedding template has 9 milestones and calculates accurate deadlines."""
    assert len(WEDDING_TIMELINE_TEMPLATE) == 9
    event_date = date(2027, 12, 15)
    ref_date = date(2027, 1, 1)

    timeline = generate_event_timeline_schedule(
        event_id="EV-TEST-WED",
        event_type=EventType.WEDDING,
        event_date=event_date,
        reference_date=ref_date,
    )

    assert timeline.event_id == "EV-TEST-WED"
    assert timeline.event_date == event_date
    assert len(timeline.milestones) == 9

    # Earliest milestone should be 180 days before Dec 15 -> June 18
    earliest = timeline.milestones[0]
    assert earliest.milestone_id == "M-WED-01"
    assert earliest.days_before_event == 180
    assert earliest.due_date == event_date - timedelta(days=180)
    assert earliest.priority == MilestonePriority.HIGH
    assert earliest.status == MilestoneStatus.PENDING
    assert earliest.is_overdue is False

    # Latest milestone should be 2 days before Dec 15 -> Dec 13
    latest = timeline.milestones[-1]
    assert latest.milestone_id == "M-WED-09"
    assert latest.days_before_event == 2
    assert latest.due_date == event_date - timedelta(days=2)


def test_birthday_timeline_generation_unit() -> None:
    """Verify birthday template has 7 milestones and calculates accurate deadlines."""
    assert len(BIRTHDAY_TIMELINE_TEMPLATE) == 7
    event_date = date(2027, 8, 20)
    ref_date = date(2027, 7, 1)

    timeline = generate_event_timeline_schedule(
        event_id="EV-TEST-BDY",
        event_type=EventType.BIRTHDAY,
        event_date=event_date,
        reference_date=ref_date,
    )

    assert timeline.event_id == "EV-TEST-BDY"
    assert timeline.event_date == event_date
    assert len(timeline.milestones) == 7

    # Check first and last milestones
    assert timeline.milestones[0].milestone_id == "M-BDY-01"
    assert timeline.milestones[0].days_before_event == 30
    assert timeline.milestones[-1].milestone_id == "M-BDY-07"
    assert timeline.milestones[-1].days_before_event == 1


def test_community_event_timeline_generation_unit() -> None:
    """Verify community event template has 8 milestones and calculates accurate deadlines."""
    assert len(COMMUNITY_EVENT_TIMELINE_TEMPLATE) == 8
    event_date = date(2027, 11, 10)
    ref_date = date(2027, 8, 1)

    timeline = generate_event_timeline_schedule(
        event_id="EV-TEST-COM",
        event_type=EventType.COMMUNITY_EVENT,
        event_date=event_date,
        reference_date=ref_date,
    )

    assert timeline.event_id == "EV-TEST-COM"
    assert timeline.event_date == event_date
    assert len(timeline.milestones) == 8

    assert timeline.milestones[0].milestone_id == "M-COM-01"
    assert timeline.milestones[0].days_before_event == 60
    assert timeline.milestones[-1].milestone_id == "M-COM-08"
    assert timeline.milestones[-1].days_before_event == 1


def test_correct_deadline_calculations_and_chronological_sorting() -> None:
    """Verify all deadlines match event_date - days_before_event and are sorted chronologically."""
    event_date = date(2027, 10, 25)
    timeline = generate_event_timeline_schedule(
        event_id="EV-TEST-SORT",
        event_type=EventType.WEDDING,
        event_date=event_date,
        reference_date=date(2027, 1, 1),
    )

    # 1. Date math verification
    for m in timeline.milestones:
        assert m.due_date == event_date - timedelta(days=m.days_before_event)

    # 2. Chronological sorting verification
    for i in range(len(timeline.milestones) - 1):
        assert timeline.milestones[i].due_date <= timeline.milestones[i + 1].due_date


def test_leap_year_dates() -> None:
    """Verify date calculations correctly account for leap year February 29."""
    # 2028 is a leap year. Event on March 1, 2028.
    # 1 day before March 1, 2028 is February 29, 2028.
    event_date = date(2028, 3, 1)
    timeline = generate_event_timeline_schedule(
        event_id="EV-TEST-LEAP",
        event_type=EventType.BIRTHDAY,
        event_date=event_date,
        reference_date=date(2028, 1, 1),
    )

    # Last milestone M-BDY-07 has days_before_event=1
    last_m = timeline.milestones[-1]
    assert last_m.days_before_event == 1
    assert last_m.due_date == date(2028, 2, 29)

    # M-BDY-06 has days_before_event=3 -> Feb 27, 2028
    m_06 = [m for m in timeline.milestones if m.milestone_id == "M-BDY-06"][0]
    assert m_06.due_date == date(2028, 2, 27)


def test_month_and_year_boundaries() -> None:
    """Verify milestone deadlines cross month and year boundaries accurately."""
    # Event on Jan 15, 2028. 60 days before crosses into November 2027.
    event_date = date(2028, 1, 15)
    timeline = generate_event_timeline_schedule(
        event_id="EV-TEST-YEAR-BOUNDARY",
        event_type=EventType.WEDDING,
        event_date=event_date,
        reference_date=date(2027, 5, 1),
    )

    # M-WED-01: 180 days before Jan 15, 2028 -> July 19, 2027
    m_01 = timeline.milestones[0]
    assert m_01.due_date.year == 2027
    assert m_01.due_date.month == 7
    assert m_01.due_date == event_date - timedelta(days=180)

    # M-WED-04: 60 days before Jan 15, 2028 -> Nov 16, 2027
    m_04 = [m for m in timeline.milestones if m.milestone_id == "M-WED-04"][0]
    assert m_04.due_date.year == 2027
    assert m_04.due_date.month == 11
    assert m_04.due_date == event_date - timedelta(days=60)

    # M-WED-09: 2 days before Jan 15, 2028 -> Jan 13, 2028
    m_09 = timeline.milestones[-1]
    assert m_09.due_date.year == 2028
    assert m_09.due_date.month == 1
    assert m_09.due_date == date(2028, 1, 13)


def test_events_scheduled_soon_with_overdue_deadlines() -> None:
    """Verify overdue flags and warnings when event date is close."""
    # Event is in 10 days relative to reference date 2027-05-01
    ref_date = date(2027, 5, 1)
    event_date = date(2027, 5, 11)

    timeline = generate_event_timeline_schedule(
        event_id="EV-TEST-SOON",
        event_type=EventType.WEDDING,
        event_date=event_date,
        reference_date=ref_date,
    )

    # Milestones with days_before_event > 10 must be overdue
    overdue_milestones = [m for m in timeline.milestones if m.is_overdue]
    future_milestones = [m for m in timeline.milestones if not m.is_overdue]

    assert len(overdue_milestones) > 0
    for m in overdue_milestones:
        assert m.due_date < ref_date

    for m in future_milestones:
        assert m.due_date >= ref_date

    # Warnings must mention overdue count and compressed window
    assert len(timeline.warnings) >= 2
    assert "milestone(s) are overdue" in timeline.warnings[0]
    assert "shorter than the standard" in timeline.warnings[1]


def test_duplicate_milestone_prevention_in_schema() -> None:
    """Verify that EventTimelineScheduleResponse rejects duplicate milestone IDs."""
    event_date = date(2027, 10, 1)
    m1 = EventMilestone(
        milestone_id="M-DUP-01",
        title="Task 1",
        description="Description 1",
        category=MilestoneCategory.VENUE,
        due_date=date(2027, 9, 1),
        days_before_event=30,
    )
    m2 = EventMilestone(
        milestone_id="M-DUP-01",  # Duplicate identifier!
        title="Task 2",
        description="Description 2",
        category=MilestoneCategory.CATERING,
        due_date=date(2027, 9, 15),
        days_before_event=16,
    )

    with pytest.raises(ValueError, match="Duplicate milestone identifiers found"):
        EventTimelineScheduleResponse(
            event_id="EV-DUP",
            event_date=event_date,
            generated_at="2027-01-01T00:00:00Z",
            milestones=[m1, m2],
        )


def test_schema_rejects_unsorted_milestones() -> None:
    """Verify that EventTimelineScheduleResponse rejects milestones that are not sorted chronologically."""
    event_date = date(2027, 10, 1)
    m_earlier = EventMilestone(
        milestone_id="M-EARLY",
        title="Early Task",
        description="Due earlier",
        category=MilestoneCategory.VENUE,
        due_date=date(2027, 8, 1),
        days_before_event=61,
    )
    m_later = EventMilestone(
        milestone_id="M-LATER",
        title="Later Task",
        description="Due later",
        category=MilestoneCategory.LOGISTICS,
        due_date=date(2027, 9, 1),
        days_before_event=30,
    )

    # Intentionally put later task first
    with pytest.raises(ValueError, match="Milestones are not sorted chronologically"):
        EventTimelineScheduleResponse(
            event_id="EV-UNSORTED",
            event_date=event_date,
            generated_at="2027-01-01T00:00:00Z",
            milestones=[m_later, m_earlier],
        )


def test_schema_rejects_inconsistent_due_date_math() -> None:
    """Verify that EventTimelineScheduleResponse validates due_date == event_date - days_before_event."""
    event_date = date(2027, 10, 1)
    m_bad = EventMilestone(
        milestone_id="M-MATH",
        title="Bad Math Task",
        description="Mismatch date",
        category=MilestoneCategory.VENUE,
        due_date=date(2027, 9, 10),  # Not 30 days before Oct 1!
        days_before_event=30,
    )

    with pytest.raises(ValueError, match="due_date .* does not match"):
        EventTimelineScheduleResponse(
            event_id="EV-MATH",
            event_date=event_date,
            generated_at="2027-01-01T00:00:00Z",
            milestones=[m_bad],
        )


# ==============================================================================
# 2. API Endpoint Integration Tests (GET /timeline & PATCH /milestones)
# ==============================================================================


def test_api_timeline_wedding_success(isolated_client: TestClient) -> None:
    """Test GET /api/v1/events/{event_id}/timeline for a wedding profile."""
    # 1. Create wedding profile
    create_payload = {
        "event_type": "wedding",
        "guest_count": 350,
        "total_budget_inr": 2_500_000,
        "city_tier": "metro",
        "city": "Mumbai",
        "event_date": "2027-11-20",
    }
    create_resp = isolated_client.post("/api/v1/events", json=create_payload)
    assert create_resp.status_code == 201
    event_id = create_resp.json()["event_id"]

    # 2. Get timeline with reference_date far in advance
    timeline_resp = isolated_client.get(
        f"/api/v1/events/{event_id}/timeline?reference_date=2027-01-01"
    )
    assert timeline_resp.status_code == 200
    data = timeline_resp.json()
    assert data["event_id"] == event_id
    assert data["event_date"] == "2027-11-20"
    assert len(data["milestones"]) == 9
    assert data["warnings"] == []

    # Check milestone details
    first_m = data["milestones"][0]
    assert first_m["milestone_id"] == "M-WED-01"
    assert first_m["category"] == "logistics"
    assert first_m["status"] == "pending"
    assert first_m["is_overdue"] is False
    assert first_m["due_date"] == "2027-05-24"  # 180 days before Nov 20, 2027


def test_api_timeline_birthday_and_community_event(isolated_client: TestClient) -> None:
    """Test GET /timeline for birthday and community event types."""
    # Birthday
    bdy_resp = isolated_client.post(
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
    assert bdy_resp.status_code == 201
    bdy_id = bdy_resp.json()["event_id"]

    timeline_bdy = isolated_client.get(
        f"/api/v1/events/{bdy_id}/timeline?reference_date=2027-07-01"
    )
    assert timeline_bdy.status_code == 200
    assert len(timeline_bdy.json()["milestones"]) == 7
    assert timeline_bdy.json()["milestones"][0]["milestone_id"].startswith("M-BDY-")

    # Community event
    com_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "community_event",
            "guest_count": 500,
            "total_budget_inr": 800_000,
            "city_tier": "tier2",
            "city": "Nagpur",
            "event_date": "2027-09-30",
        },
    )
    assert com_resp.status_code == 201
    com_id = com_resp.json()["event_id"]

    timeline_com = isolated_client.get(
        f"/api/v1/events/{com_id}/timeline?reference_date=2027-07-01"
    )
    assert timeline_com.status_code == 200
    assert len(timeline_com.json()["milestones"]) == 8
    assert timeline_com.json()["milestones"][0]["milestone_id"].startswith("M-COM-")


def test_api_timeline_unknown_event_returns_404(isolated_client: TestClient) -> None:
    """Verify that requesting a timeline for a non-existent event ID returns 404."""
    resp = isolated_client.get("/api/v1/events/EV-NONEXISTENT/timeline")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert "not found" in data["error"]["message"].lower()


def test_api_timeline_missing_event_date_handling(isolated_client: TestClient) -> None:
    """Verify that an event without an event_date returns empty milestones and clear guidance."""
    # Create profile without event_date
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 200,
            "total_budget_inr": 1_000_000,
            "city_tier": "metro",
            "city": "Delhi",
            # event_date omitted
        },
    )
    assert create_resp.status_code == 201
    event_id = create_resp.json()["event_id"]

    # Request timeline
    resp = isolated_client.get(f"/api/v1/events/{event_id}/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_id"] == event_id
    assert data["event_date"] is None
    assert data["milestones"] == []
    assert len(data["warnings"]) >= 1
    assert "Event date is not set" in data["warnings"][0]

    # Calling PATCH milestone when event_date is missing returns 422
    patch_resp = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-WED-01",
        json={"status": "completed"},
    )
    assert patch_resp.status_code == 422
    assert "event_date is not set" in patch_resp.json()["error"]["message"]



def test_api_timeline_milestone_completion_flow(isolated_client: TestClient) -> None:
    """Test marking milestones as completed, verifying overdue status update and persistence."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 300,
            "total_budget_inr": 2_000_000,
            "city_tier": "metro",
            "city": "Bengaluru",
            "event_date": "2027-06-01",
        },
    )
    assert create_resp.status_code == 201
    event_id = create_resp.json()["event_id"]

    # Simulate reference date where M-WED-01 (180 days before June 1 -> Dec 3, 2026) is overdue
    ref_date = "2027-01-15"
    t_before = isolated_client.get(
        f"/api/v1/events/{event_id}/timeline?reference_date={ref_date}"
    ).json()

    m_01_before = [m for m in t_before["milestones"] if m["milestone_id"] == "M-WED-01"][0]
    assert m_01_before["status"] == "pending"
    assert m_01_before["is_overdue"] is True

    # Complete M-WED-01 via PATCH
    patch_resp = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-WED-01?reference_date={ref_date}",
        json={"status": "completed"},
    )
    assert patch_resp.status_code == 200
    m_01_updated = patch_resp.json()
    assert m_01_updated["milestone_id"] == "M-WED-01"
    assert m_01_updated["status"] == "completed"
    # Completed milestones are NEVER overdue
    assert m_01_updated["is_overdue"] is False
    # Original due date must be preserved
    assert m_01_updated["due_date"] == m_01_before["due_date"]

    # Verify GET /timeline reflects the updated status
    t_after = isolated_client.get(
        f"/api/v1/events/{event_id}/timeline?reference_date={ref_date}"
    ).json()
    m_01_after = [m for m in t_after["milestones"] if m["milestone_id"] == "M-WED-01"][0]
    assert m_01_after["status"] == "completed"
    assert m_01_after["is_overdue"] is False

    # Toggle back to pending
    reset_resp = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-WED-01?reference_date={ref_date}",
        json={"status": "pending"},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "pending"
    assert reset_resp.json()["is_overdue"] is True


def test_api_milestone_completion_error_cases(isolated_client: TestClient) -> None:
    """Test validation and error handling for milestone status updates."""
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

    # 1. Unknown event -> 404
    resp_unknown_ev = isolated_client.patch(
        "/api/v1/events/EV-DOESNOTEXIST/timeline/milestones/M-WED-01",
        json={"status": "completed"},
    )
    assert resp_unknown_ev.status_code == 404

    # 2. Unknown milestone ID -> 404
    resp_unknown_m = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-UNKNOWN-99",
        json={"status": "completed"},
    )
    assert resp_unknown_m.status_code == 404
    assert "not a valid milestone" in resp_unknown_m.json()["error"]["message"]

    # 3. Milestone belonging to different event type -> 404
    resp_mismatched_m = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-BDY-01",
        json={"status": "completed"},
    )
    assert resp_mismatched_m.status_code == 404

    # 4. Invalid status -> 422
    resp_bad_status = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-WED-01",
        json={"status": "in_progress"},
    )
    assert resp_bad_status.status_code == 422

    # 5. Client trying to change computed deadlines or extra fields -> 422 (extra="forbid")
    resp_extra = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-WED-01",
        json={"status": "completed", "due_date": "2030-01-01"},
    )
    assert resp_extra.status_code == 422


def test_milestone_status_persists_across_profile_updates_and_rebalance(
    isolated_client: TestClient,
) -> None:
    """Verify that milestone completion state is not wiped when event profile or budget changes."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 250,
            "total_budget_inr": 1_500_000,
            "event_date": "2027-11-01",
        },
    )
    event_id = create_resp.json()["event_id"]

    # Complete M-WED-02
    patch_m = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-WED-02",
        json={"status": "completed"},
    )
    assert patch_m.status_code == 200

    # 1. Update event profile metadata (e.g. event_name)
    update_resp = isolated_client.patch(
        f"/api/v1/events/{event_id}",
        json={"event_name": "Royal Palace Wedding"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["event_name"] == "Royal Palace Wedding"

    # Verify M-WED-02 is still completed
    t1 = isolated_client.get(f"/api/v1/events/{event_id}/timeline").json()
    m_02_after_update = [m for m in t1["milestones"] if m["milestone_id"] == "M-WED-02"][0]
    assert m_02_after_update["status"] == "completed"

    # 2. Rebalance budget
    rebalance_resp = isolated_client.post(
        f"/api/v1/events/{event_id}/budget/rebalance",
        json={"new_total_budget_inr": 1_800_000},
    )
    assert rebalance_resp.status_code == 200

    # Verify M-WED-02 is still completed after rebalance
    t2 = isolated_client.get(f"/api/v1/events/{event_id}/timeline").json()
    m_02_after_rebalance = [m for m in t2["milestones"] if m["milestone_id"] == "M-WED-02"][0]
    assert m_02_after_rebalance["status"] == "completed"


def test_timeline_recalculates_when_event_date_updated(isolated_client: TestClient) -> None:
    """Verify that updating the event date via PATCH /events/{id} updates all milestone due dates."""
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "guest_count": 60,
            "total_budget_inr": 200_000,
            "event_date": "2027-06-10",
        },
    )
    event_id = create_resp.json()["event_id"]

    t_initial = isolated_client.get(f"/api/v1/events/{event_id}/timeline").json()
    assert t_initial["milestones"][-1]["due_date"] == "2027-06-09"  # 1 day before

    # Update event date to June 20
    isolated_client.patch(
        f"/api/v1/events/{event_id}",
        json={"event_date": "2027-06-20"},
    )

    t_shifted = isolated_client.get(f"/api/v1/events/{event_id}/timeline").json()
    assert t_shifted["event_date"] == "2027-06-20"
    assert t_shifted["milestones"][-1]["due_date"] == "2027-06-19"  # 1 day before new date


# ==============================================================================
# 3. Security, Demo Mode & Offline Operation Tests
# ==============================================================================


def test_timeline_operates_without_gemini_api_key_and_zero_network_calls(
    isolated_client: TestClient,
) -> None:
    """Verify that timeline scheduling operates 100% offline without Gemini credentials."""
    # Ensure any HTTP call attempt fails immediately
    with patch("urllib.request.urlopen", side_effect=RuntimeError("Outbound network disabled")):
        create_resp = isolated_client.post(
            "/api/v1/events",
            json={
                "event_type": "wedding",
                "guest_count": 400,
                "total_budget_inr": 3_000_000,
                "event_date": "2027-12-01",
            },
        )
        assert create_resp.status_code == 201
        event_id = create_resp.json()["event_id"]

        timeline_resp = isolated_client.get(f"/api/v1/events/{event_id}/timeline")
        assert timeline_resp.status_code == 200
        assert len(timeline_resp.json()["milestones"]) == 9

        # Update milestone
        patch_resp = isolated_client.patch(
            f"/api/v1/events/{event_id}/timeline/milestones/M-WED-01",
            json={"status": "completed"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "completed"


def test_existing_event_and_budget_features_remain_functional(
    isolated_client: TestClient,
) -> None:
    """End-to-end integration verifying profile, budget, and timeline features coexist smoothly."""
    # 1. Create event
    create_resp = isolated_client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 250,
            "total_budget_inr": 2_000_000,
            "city_tier": "metro",
            "city": "Hyderabad",
            "event_date": "2027-11-15",
        },
    )
    assert create_resp.status_code == 201
    event_id = create_resp.json()["event_id"]

    # 2. Get budget plan
    budget_resp = isolated_client.get(f"/api/v1/events/{event_id}/budget")
    assert budget_resp.status_code == 200
    assert budget_resp.json()["total_budget_inr"] == 2_000_000
    assert "allocations" in budget_resp.json()

    # 3. Rebalance budget
    rebal_resp = isolated_client.post(
        f"/api/v1/events/{event_id}/budget/rebalance",
        json={"new_total_budget_inr": 1_800_000},
    )
    assert rebal_resp.status_code == 200
    assert rebal_resp.json()["new_total_inr"] == 1_800_000

    # 4. Get timeline
    timeline_resp = isolated_client.get(f"/api/v1/events/{event_id}/timeline")
    assert timeline_resp.status_code == 200
    assert len(timeline_resp.json()["milestones"]) == 9

    # 5. Complete milestone
    patch_m = isolated_client.patch(
        f"/api/v1/events/{event_id}/timeline/milestones/M-WED-02",
        json={"status": "completed"},
    )
    assert patch_m.status_code == 200
    assert patch_m.json()["status"] == "completed"

    # 6. Retrieve profile and ensure consistency
    profile_resp = isolated_client.get(f"/api/v1/events/{event_id}")
    assert profile_resp.status_code == 200
    pdata = profile_resp.json()
    assert pdata["total_budget_inr"] == 1_800_000
    assert pdata["milestone_statuses"]["M-WED-02"] == "completed"

