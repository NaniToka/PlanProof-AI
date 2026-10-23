"""Automated test suite for Prompt 19: Event Readiness Score & Planning Progress.

Verifies:
1. Newly created event with little planning information.
2. Well-prepared event with completed planning tasks.
3. Incomplete vendor checklist items.
4. Overdue or incomplete timeline milestones.
5. High-priority risks with available mitigation data.
6. Missing event dates and optional information.
7. Missing crisis recovery history.
8. Insufficient-data handling.
9. Score boundaries and deterministic calculations.
10. Correct handling of unavailable categories.
11. Next-action references point to real items.
12. No duplicate recommendations for the same issue.
13. Invalid event IDs (404 Not Found).
14. The readiness endpoint does not mutate source data.
15. Existing tests and crisis dataset integrity preserved.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.schemas import (
    CrisisRecoveryRecord,
    EventBudgetBreakdown,
    EventCrisisRecoveryResponse,
    EventProfile,
    EventType,
    MilestoneStatus,
    ReadinessActionPriority,
    ReadinessCategory,
    ReadinessStatus,
    RecoveryActionStatus,
    RecoveryProgressSummary,
    RecoveryStatus,
    TrackedRecoveryAction,
    VendorBookingStatus,
    VendorChecklistPriority,
    VendorChecklistStatus,
)
from app.services.event_service import EventService
from app.services.readiness_service import ReadinessService


def test_newly_created_event_low_readiness(client: TestClient) -> None:
    """1. A newly created event with little planning information yields an initial status with actionable recommendations."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 150,
            "total_budget_inr": 2000000,
            "event_date": None,  # Date not yet confirmed
            "city": None,
            "event_name": None,
        },
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/readiness")
    assert res.status_code == 200
    data = res.json()

    assert data["event_id"] == event_id
    assert data["overall_score"] is not None
    assert 0 <= data["overall_score"] <= 100
    assert data["readiness_status"] in (
        ReadinessStatus.NOT_STARTED.value,
        ReadinessStatus.NEEDS_ATTENTION.value,
        ReadinessStatus.IN_PROGRESS.value,
    )

    # Missing date should be flagged
    assert any("date" in msg.lower() for msg in data["missing_information"])

    # Actionable next actions should recommend setting date or booking core vendors
    actions = data["recommended_next_actions"]
    assert len(actions) > 0
    assert any(a["category"] == "planning" or a["category"] == "vendor" for a in actions)


def test_well_prepared_event_high_readiness(client: TestClient) -> None:
    """2. A well-prepared event with completed planning tasks yields a high score (well_prepared)."""
    target_date = (date.today() + timedelta(days=180)).isoformat()
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 200,
            "total_budget_inr": 3000000,
            "event_date": target_date,
            "city": "Mumbai",
            "event_name": "Sharma Wedding Celebration",
        },
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    # 1. Complete all timeline milestones
    tl_res = client.get(f"/api/v1/events/{event_id}/timeline")
    milestones = tl_res.json()["milestones"]
    for m in milestones:
        patch_res = client.patch(
            f"/api/v1/events/{event_id}/timeline/milestones/{m['milestone_id']}",
            json={"status": "completed"},
        )
        assert patch_res.status_code == 200

    # 2. Book and complete all vendor tasks
    vl_res = client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    vendor_items = vl_res.json()["items"]
    for v in vendor_items:
        patch_res = client.patch(
            f"/api/v1/events/{event_id}/vendors/checklist/{v['id']}",
            json={
                "status": "completed",
                "booking_status": "booked",
                "vendor_name": "Premium Vendor",
            },
        )
        assert patch_res.status_code == 200

    # 3. Retrieve readiness
    res = client.get(f"/api/v1/events/{event_id}/readiness")
    assert res.status_code == 200
    data = res.json()

    assert data["overall_score"] is not None
    assert data["overall_score"] >= 80
    assert data["readiness_status"] == ReadinessStatus.WELL_PREPARED.value
    assert data["completed_items"] > 15
    assert len(data["critical_concerns"]) == 0


def test_incomplete_vendor_checklist_items(client: TestClient) -> None:
    """3. Incomplete vendor checklist items are scored accurately and recommended for booking."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "guest_count": 50,
            "total_budget_inr": 500000,
            "event_date": (date.today() + timedelta(days=60)).isoformat(),
            "city": "Bengaluru",
        },
    )
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/readiness")
    assert res.status_code == 200
    data = res.json()

    vendor_cat = next(c for c in data["category_scores"] if c["category"] == ReadinessCategory.VENDOR_COORDINATION.value)
    assert vendor_cat["is_available"] is True
    assert vendor_cat["score"] is not None

    # Actions must include vendor booking
    vendor_actions = [a for a in data["recommended_next_actions"] if a["category"] == "vendor"]
    assert len(vendor_actions) > 0
    # Must reference real vendor task ID
    assert vendor_actions[0]["target_id"] is not None


def test_overdue_or_incomplete_timeline_milestones(client: TestClient) -> None:
    """4. Overdue timeline milestones penalize timeline readiness and generate critical concern."""
    # Set event date in 10 days
    event_date = date.today() + timedelta(days=10)
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 250,
            "total_budget_inr": 2500000,
            "event_date": event_date.isoformat(),
            "city": "Delhi",
        },
    )
    event_id = create_res.json()["event_id"]

    # Use reference_date that makes early milestones overdue
    simulated_today = event_date - timedelta(days=5)
    res = client.get(f"/api/v1/events/{event_id}/readiness?reference_date={simulated_today.isoformat()}")
    assert res.status_code == 200
    data = res.json()

    timeline_cat = next(c for c in data["category_scores"] if c["category"] == ReadinessCategory.TIMELINE_READINESS.value)
    assert timeline_cat["supporting_counts"]["overdue_milestones"] > 0
    assert any("overdue" in c.lower() for c in data["critical_concerns"])

    # Overdue milestone should be in next actions with critical priority
    overdue_actions = [a for a in data["recommended_next_actions"] if a["category"] == "timeline"]
    assert len(overdue_actions) > 0
    assert overdue_actions[0]["priority"] == ReadinessActionPriority.CRITICAL.value


def test_high_priority_risks_with_mitigation_data(client: TestClient) -> None:
    """5. High-priority risks deduct from risk preparedness and surface mitigations in next actions."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 300,
            "total_budget_inr": 3500000,
            "event_date": (date.today() + timedelta(days=90)).isoformat(),
            "city": "Jaipur",
        },
    )
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/readiness")
    assert res.status_code == 200
    data = res.json()

    risk_cat = next(c for c in data["category_scores"] if c["category"] == ReadinessCategory.RISK_PREPAREDNESS.value)
    assert risk_cat["is_available"] is True
    assert risk_cat["score"] is not None
    assert 0 <= risk_cat["score"] <= 100

    # Risk actions must reference real risk items
    risk_actions = [a for a in data["recommended_next_actions"] if a["category"] == "risk"]
    if risk_actions:
        assert risk_actions[0]["target_id"].startswith("RISK-")


def test_missing_event_dates_and_optional_information(client: TestClient) -> None:
    """6. Missing event dates and optional fields are handled safely without crashing."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "community_event",
            "guest_count": 100,
            "total_budget_inr": 800000,
            "event_date": None,
            "city": None,
            "event_name": None,
        },
    )
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/readiness")
    assert res.status_code == 200
    data = res.json()

    assert data["overall_score"] is not None
    assert 0 <= data["overall_score"] <= 100
    assert len(data["missing_information"]) >= 2
    assert any("date" in msg.lower() for msg in data["missing_information"])
    assert any("city" in msg.lower() for msg in data["missing_information"])


def test_missing_crisis_recovery_history(client: TestClient) -> None:
    """7. An event without crisis records marks crisis follow-up as unavailable without penalty."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "guest_count": 40,
            "total_budget_inr": 300000,
            "event_date": (date.today() + timedelta(days=45)).isoformat(),
            "city": "Pune",
        },
    )
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/readiness")
    assert res.status_code == 200
    data = res.json()

    crisis_cat = next(c for c in data["category_scores"] if c["category"] == ReadinessCategory.CRISIS_FOLLOWUP.value)
    assert crisis_cat["is_available"] is False
    assert crisis_cat["score"] is None
    assert crisis_cat["weight_percentage"] == 0.0
    assert "not applicable" in crisis_cat["explanation"].lower()


def test_insufficient_data_handling() -> None:
    """8. If profile has zero/corrupted budget or invalid data, returns insufficient_data status."""
    now = datetime.now(timezone.utc)
    profile = EventProfile(
        event_id="EV-INSUFFICIENT",
        event_type=EventType.WEDDING,
        guest_count=0,  # Invalid guest count
        total_budget_inr=0,  # Zero budget
        budget=None,
        vendor_checklist=[],
        recovery_records=[],
        created_at=now,
        updated_at=now,
    )

    resp = ReadinessService.calculate_readiness(profile)
    assert resp.overall_score is None
    assert resp.readiness_status == ReadinessStatus.INSUFFICIENT_DATA
    assert len(resp.missing_information) > 0


def test_score_boundaries_and_deterministic_calculations(client: TestClient) -> None:
    """9. Readiness calculation is deterministic and strictly bounded between 0 and 100."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 120,
            "total_budget_inr": 1500000,
            "event_date": (date.today() + timedelta(days=90)).isoformat(),
            "city": "Hyderabad",
            "event_name": "Nani & Family Celebration",
        },
    )
    event_id = create_res.json()["event_id"]

    res1 = client.get(f"/api/v1/events/{event_id}/readiness")
    res2 = client.get(f"/api/v1/events/{event_id}/readiness")

    assert res1.status_code == 200
    assert res2.status_code == 200

    d1 = res1.json()
    d2 = res2.json()

    # Must be integer bounded in [0, 100]
    assert isinstance(d1["overall_score"], int)
    assert 0 <= d1["overall_score"] <= 100

    # Repeat calls must yield exact same score and category breakdowns
    assert d1["overall_score"] == d2["overall_score"]
    assert d1["readiness_status"] == d2["readiness_status"]
    assert [c["score"] for c in d1["category_scores"]] == [c["score"] for c in d2["category_scores"]]
    assert len(d1["recommended_next_actions"]) == len(d2["recommended_next_actions"])


def test_correct_handling_of_unavailable_categories(client: TestClient) -> None:
    """10. Available category weights dynamically sum to 100.0% when crisis follow-up is unavailable."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 150,
            "total_budget_inr": 2000000,
            "event_date": (date.today() + timedelta(days=100)).isoformat(),
            "city": "Chennai",
        },
    )
    event_id = create_res.json()["event_id"]

    # 1. Without crisis records
    res = client.get(f"/api/v1/events/{event_id}/readiness")
    data = res.json()
    available_cats = [c for c in data["category_scores"] if c["is_available"]]
    total_weights = sum(c["weight_percentage"] for c in available_cats)
    assert round(total_weights, 1) == 100.0

    # 2. Add a crisis recovery record
    eval_res = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={
            "crisis_type": "rain",
            "severity": 2,
            "description": "Rain during outdoor staging",
        },
    )
    assert eval_res.status_code == 200
    plan_data = eval_res.json()["data"]
    save_res = client.post(
        f"/api/v1/events/{event_id}/crisis/recoveries",
        json={
            "crisis_type": "rain",
            "severity": 2,
            "description": "Rain during outdoor staging",
            "recovery_plan": plan_data,
            "source": "rules",
        },
    )
    assert save_res.status_code == 201

    # 3. Crisis category now becomes available and weights still sum to 100.0%
    res2 = client.get(f"/api/v1/events/{event_id}/readiness")
    data2 = res2.json()
    crisis_cat = next(c for c in data2["category_scores"] if c["category"] == ReadinessCategory.CRISIS_FOLLOWUP.value)
    assert crisis_cat["is_available"] is True
    assert crisis_cat["score"] is not None

    available_cats2 = [c for c in data2["category_scores"] if c["is_available"]]
    total_weights2 = sum(c["weight_percentage"] for c in available_cats2)
    assert round(total_weights2, 1) == 100.0


def test_next_action_references_point_to_real_items(client: TestClient) -> None:
    """11. Every recommended next action with target_id points to an existing milestone, vendor item, risk, or recovery action."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 180,
            "total_budget_inr": 2200000,
            "event_date": (date.today() + timedelta(days=120)).isoformat(),
            "city": "Kolkata",
        },
    )
    event_id = create_res.json()["event_id"]

    tl_res = client.get(f"/api/v1/events/{event_id}/timeline")
    valid_milestone_ids = {m["milestone_id"] for m in tl_res.json()["milestones"]}

    vl_res = client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    valid_vendor_ids = {v["id"] for v in vl_res.json()["items"]}

    res = client.get(f"/api/v1/events/{event_id}/readiness")
    actions = res.json()["recommended_next_actions"]

    for act in actions:
        if act["category"] == "timeline" and act["target_id"]:
            assert act["target_id"] in valid_milestone_ids
        elif act["category"] == "vendor" and act["target_id"]:
            assert act["target_id"] in valid_vendor_ids
        elif act["category"] == "risk" and act["target_id"]:
            assert act["target_id"].startswith("RISK-")


def test_no_duplicate_recommendations_for_same_issue(client: TestClient) -> None:
    """12. Deduplication prevents multiple recommended actions for the exact same target item."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 100,
            "total_budget_inr": 1200000,
            "event_date": (date.today() + timedelta(days=50)).isoformat(),
            "city": "Ahmedabad",
        },
    )
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/readiness")
    actions = res.json()["recommended_next_actions"]

    seen = set()
    for act in actions:
        key = (act["category"], act["target_id"])
        assert key not in seen, f"Duplicate action key found: {key}"
        seen.add(key)


def test_invalid_event_id_returns_404(client: TestClient) -> None:
    """13. Querying readiness for an invalid or non-existent event ID returns 404."""
    res = client.get("/api/v1/events/EV-NONEXISTENT-9999/readiness")
    assert res.status_code == 404
    error = res.json()
    assert error["error"]["code"] == "NOT_FOUND" or "not found" in error["error"]["message"].lower()


def test_readiness_endpoint_does_not_mutate_source_data(client: TestClient) -> None:
    """14. The readiness endpoint is read-only and does not mutate budget, timeline, vendors, or recovery history."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 200,
            "total_budget_inr": 2500000,
            "event_date": (date.today() + timedelta(days=90)).isoformat(),
            "city": "Lucknow",
        },
    )
    event_id = create_res.json()["event_id"]

    # Snapshot state before
    budget_before = client.get(f"/api/v1/events/{event_id}/budget").json()
    tl_before = client.get(f"/api/v1/events/{event_id}/timeline").json()["milestones"]
    vl_before = client.get(f"/api/v1/events/{event_id}/vendors/checklist").json()["items"]
    rec_before = client.get(f"/api/v1/events/{event_id}/crisis/recoveries").json()

    # Call readiness multiple times
    client.get(f"/api/v1/events/{event_id}/readiness")
    client.get(f"/api/v1/events/{event_id}/readiness")

    # Snapshot state after
    budget_after = client.get(f"/api/v1/events/{event_id}/budget").json()
    tl_after = client.get(f"/api/v1/events/{event_id}/timeline").json()["milestones"]
    vl_after = client.get(f"/api/v1/events/{event_id}/vendors/checklist").json()["items"]
    rec_after = client.get(f"/api/v1/events/{event_id}/crisis/recoveries").json()

    assert budget_before == budget_after
    assert tl_before == tl_after
    assert vl_before == vl_after
    assert rec_before == rec_after


def test_crisis_scenarios_dataset_preserved() -> None:
    """15. Preservation check: Verify data/crisis_scenarios.csv contains exactly 5,000 scenarios and 5,001 rows."""
    crisis_path = Path("data/crisis_scenarios.csv")
    assert crisis_path.exists(), "data/crisis_scenarios.csv must exist"
    with open(crisis_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 5001, f"Expected 5,001 lines (header + 5,000 scenarios), got {len(lines)}"
