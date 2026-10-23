"""Automated unit and integration tests for Crisis Recovery History and Action Tracker (Prompt 18).

Covers all 14 required verification scenarios:
1. Saving a valid recovery record.
2. Listing records for the correct event.
3. Retrieving an individual record.
4. Rejecting invalid event or recovery IDs.
5. Preventing cross-event record access.
6. Updating recovery status.
7. Updating action status and notes.
8. Rejecting invalid status values.
9. Enforcing text-length limits.
10. Correct recovery progress counts.
11. Avoiding automatic resolution when actions remain incomplete.
12. Ensuring history updates do not mutate unrelated budget, timeline, or checklist data.
13. Handling missing or malformed recovery plans.
14. Preserving existing tests and crisis dataset integrity.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.data_loader import load_crisis_scenarios
from app.main import create_app
from app.schemas import (
    RecoveryActionStatus,
    RecoveryStatus,
)


@pytest.fixture
def client_and_events() -> tuple[TestClient, str, str]:
    """Create test client and two distinct test events for isolation and cross-event checks."""
    app = create_app()
    with TestClient(app) as client:
        # Event 1: Wedding in Bengaluru
        res1 = client.post(
            "/api/v1/events",
            json={
                "event_type": "wedding",
                "event_name": "Aarav & Maya Grand Wedding",
                "city": "Bengaluru",
                "city_tier": "metro",
                "event_date": "2027-04-18",
                "guest_count": 400,
                "total_budget_inr": 3000000,
                "language": "en",
                "theme_notes": "Royal outdoor mandap and glass banquet dinner",
            },
        )
        assert res1.status_code == 201
        event_1_id = res1.json()["event_id"]

        # Event 2: Birthday in Pune
        res2 = client.post(
            "/api/v1/events",
            json={
                "event_type": "birthday",
                "event_name": "Rohan 10th Birthday Jubilee",
                "city": "Pune",
                "city_tier": "tier2",
                "event_date": "2027-06-10",
                "guest_count": 80,
                "total_budget_inr": 250000,
                "language": "en",
            },
        )
        assert res2.status_code == 201
        event_2_id = res2.json()["event_id"]

        yield client, event_1_id, event_2_id


def _evaluate_crisis(client: TestClient, event_id: str, crisis_type: str = "rain", severity: int = 3) -> dict:
    """Helper to evaluate crisis and return recovery plan data."""
    res = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={
            "crisis_type": crisis_type,
            "severity": severity,
            "description": "Heavy unseasonal deluge flooding open pavilion lawn",
            "affected_area": "venue",
            "event_phase": "event_day",
        },
    )
    assert res.status_code == 200
    envelope = res.json()
    assert envelope["status"] == "success"
    return envelope["data"]


# ==============================================================================
# 1. Saving a valid recovery record
# ==============================================================================


def test_save_valid_recovery_record_default_actions(client_and_events: tuple[TestClient, str, str]) -> None:
    """Verify saving a recovery record extracts recommended actions and assigns stable IDs."""
    client, event_1, _ = client_and_events
    plan_data = _evaluate_crisis(client, event_1, crisis_type="rain", severity=3)

    res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={
            "crisis_type": "rain",
            "severity": 3,
            "description": "Severe thunderstorm flooding lawn setup",
            "recovery_plan": plan_data,
            "source": "rules",
            "status": "open",
        },
    )
    assert res.status_code == 201
    record = res.json()

    assert record["recovery_id"].startswith("REC-")
    assert record["event_id"] == event_1
    assert record["crisis_type"] == "rain"
    assert record["severity"] == 3
    assert record["source"] == "rules"
    assert record["status"] == "open"
    assert len(record["actions"]) >= 2

    # Check stable action IDs and initial pending state
    for action in record["actions"]:
        assert action["action_id"].startswith("ACT-")
        assert action["status"] == "pending"
        assert action["priority"] in (1, 2, 3)
        assert len(action["title"]) > 0
        assert len(action["description"]) > 0
        assert "created_at" in action
        assert "updated_at" in action

    # Check summary counts
    progress = record["progress"]
    assert progress["total_actions"] == len(record["actions"])
    assert progress["pending_actions"] == len(record["actions"])
    assert progress["in_progress_actions"] == 0
    assert progress["completed_actions"] == 0
    assert progress["completion_percentage"] == 0.0


def test_save_valid_recovery_record_custom_selected_actions(
    client_and_events: tuple[TestClient, str, str],
) -> None:
    """Verify user can explicitly select and customize which recommended actions to track."""
    client, event_1, _ = client_and_events
    plan_data = _evaluate_crisis(client, event_1, crisis_type="power_cut", severity=2)

    selected_actions = [
        {
            "action_id": "ACT-CUSTOM-01",
            "title": "Start backup silent diesel generator",
            "description": "Switch power grid to secondary silent genset within 3 minutes",
            "priority": 1,
            "status": "pending",
            "notes": "Generator technician stationed at east substation",
        },
        {
            "action_id": "ACT-CUSTOM-02",
            "title": "Route emergency sound console battery",
            "description": "Power podium microphones through UPS unit",
            "priority": 2,
            "status": "pending",
            "notes": None,
        },
    ]

    res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={
            "crisis_type": "power_cut",
            "severity": 2,
            "description": "Sudden substation power cut during banquet speeches",
            "recovery_plan": plan_data,
            "source": "rules",
            "actions": selected_actions,
        },
    )
    assert res.status_code == 201
    record = res.json()
    assert record["total_actions"] == 2
    assert record["actions"][0]["action_id"] == "ACT-CUSTOM-01"
    assert record["actions"][0]["notes"] == "Generator technician stationed at east substation"
    assert record["actions"][1]["action_id"] == "ACT-CUSTOM-02"


# ==============================================================================
# 2. Listing records for the correct event
# ==============================================================================


def test_list_recovery_records_scoped_and_newest_first(
    client_and_events: tuple[TestClient, str, str],
) -> None:
    """Verify listing returns newest records first and strictly scopes records to owning event."""
    client, event_1, event_2 = client_and_events
    plan_rain = _evaluate_crisis(client, event_1, crisis_type="rain", severity=3)
    plan_power = _evaluate_crisis(client, event_1, crisis_type="power_cut", severity=2)

    # Save 2 records on Event 1
    res_rec1 = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={
            "crisis_type": "rain",
            "severity": 3,
            "recovery_plan": plan_rain,
            "description": "First incident: rain storm",
        },
    )
    assert res_rec1.status_code == 201
    rec1_id = res_rec1.json()["recovery_id"]

    res_rec2 = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={
            "crisis_type": "power_cut",
            "severity": 2,
            "recovery_plan": plan_power,
            "description": "Second incident: power cut",
        },
    )
    assert res_rec2.status_code == 201
    rec2_id = res_rec2.json()["recovery_id"]

    # List Event 1 records
    list_res = client.get(f"/api/v1/events/{event_1}/crisis/recoveries")
    assert list_res.status_code == 200
    records = list_res.json()
    assert len(records) == 2

    # Newest first: rec2 was created second, so should be at index 0
    assert records[0]["recovery_id"] == rec2_id
    assert records[1]["recovery_id"] == rec1_id

    # Event 2 must have zero recovery records
    list_event2_res = client.get(f"/api/v1/events/{event_2}/crisis/recoveries")
    assert list_event2_res.status_code == 200
    assert len(list_event2_res.json()) == 0


# ==============================================================================
# 3. Retrieving an individual record
# ==============================================================================


def test_retrieve_individual_record_success(client_and_events: tuple[TestClient, str, str]) -> None:
    """Verify GET /{recovery_id} returns the complete record with plan and action tracking."""
    client, event_1, _ = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="caterer_late", severity=1)

    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={
            "crisis_type": "caterer_late",
            "severity": 1,
            "recovery_plan": plan,
            "description": "Buffet delivery delayed by 30 mins due to traffic",
        },
    )
    assert save_res.status_code == 201
    rec_id = save_res.json()["recovery_id"]

    get_res = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}")
    assert get_res.status_code == 200
    record = get_res.json()
    assert record["recovery_id"] == rec_id
    assert record["event_id"] == event_1
    assert record["crisis_type"] == "caterer_late"
    assert "recovery_plan" in record
    assert record["recovery_plan"]["severity"] == 1
    assert len(record["actions"]) > 0


# ==============================================================================
# 4. Rejecting invalid event or recovery IDs
# ==============================================================================


def test_reject_invalid_event_or_recovery_or_action_ids(
    client_and_events: tuple[TestClient, str, str],
) -> None:
    """Verify 404 response for non-existent event, recovery, or action IDs."""
    client, event_1, _ = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="rain", severity=3)

    # 1. Non-existent event on POST
    res_bad_ev_post = client.post(
        "/api/v1/events/EV-NONEXISTENT-999/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": plan},
    )
    assert res_bad_ev_post.status_code == 404
    assert "not found" in res_bad_ev_post.json()["error"]["message"].lower()

    # 2. Non-existent event on GET list
    res_bad_ev_list = client.get("/api/v1/events/EV-NONEXISTENT-999/crisis/recoveries")
    assert res_bad_ev_list.status_code == 404

    # 3. Non-existent recovery on valid event
    res_bad_rec = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/REC-DOESNOTEXIST")
    assert res_bad_rec.status_code == 404

    # 4. Non-existent recovery on PATCH
    res_bad_patch_rec = client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/REC-DOESNOTEXIST",
        json={"status": "in_progress"},
    )
    assert res_bad_patch_rec.status_code == 404

    # 5. Non-existent action on valid recovery
    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": plan},
    )
    rec_id = save_res.json()["recovery_id"]

    res_bad_act = client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/ACT-GHOST-99",
        json={"status": "completed"},
    )
    assert res_bad_act.status_code == 404


# ==============================================================================
# 5. Preventing cross-event record access
# ==============================================================================


def test_prevent_cross_event_record_access(client_and_events: tuple[TestClient, str, str]) -> None:
    """Verify that records belonging to Event 1 cannot be viewed or modified through Event 2 routes."""
    client, event_1, event_2 = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="rain", severity=3)

    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": plan},
    )
    rec_id = save_res.json()["recovery_id"]
    action_id = save_res.json()["actions"][0]["action_id"]

    # Attempt to GET Event 1's record through Event 2 route -> 404
    cross_get = client.get(f"/api/v1/events/{event_2}/crisis/recoveries/{rec_id}")
    assert cross_get.status_code == 404

    # Attempt to PATCH Event 1's record through Event 2 route -> 404
    cross_patch = client.patch(
        f"/api/v1/events/{event_2}/crisis/recoveries/{rec_id}",
        json={"status": "resolved"},
    )
    assert cross_patch.status_code == 404

    # Attempt to PATCH Event 1's action through Event 2 route -> 404
    cross_action = client.patch(
        f"/api/v1/events/{event_2}/crisis/recoveries/{rec_id}/actions/{action_id}",
        json={"status": "completed"},
    )
    assert cross_action.status_code == 404


# ==============================================================================
# 6. Updating recovery status
# ==============================================================================


def test_update_recovery_status_and_description(
    client_and_events: tuple[TestClient, str, str],
) -> None:
    """Verify PATCH /{recovery_id} allows updating status and host description."""
    client, event_1, _ = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="power_cut", severity=2)

    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "power_cut", "severity": 2, "recovery_plan": plan},
    )
    rec_id = save_res.json()["recovery_id"]
    assert save_res.json()["status"] == "open"

    # Update to in_progress
    patch_res = client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}",
        json={"status": "in_progress", "description": "Electrician deployed on-site"},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["status"] == "in_progress"
    assert updated["description"] == "Electrician deployed on-site"

    # Retrieve again to verify persistence
    get_res = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}")
    assert get_res.json()["status"] == "in_progress"


# ==============================================================================
# 7. Updating action status and notes
# ==============================================================================


def test_update_action_status_and_notes(client_and_events: tuple[TestClient, str, str]) -> None:
    """Verify PATCH .../actions/{action_id} updates status, notes, and parent progress snapshot."""
    client, event_1, _ = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="photographer_noshow", severity=3)

    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "photographer_noshow", "severity": 3, "recovery_plan": plan},
    )
    rec_id = save_res.json()["recovery_id"]
    action_1_id = save_res.json()["actions"][0]["action_id"]

    patch_res = client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{action_1_id}",
        json={
            "status": "in_progress",
            "notes": "Spoke to associate shooter, ETA 15 minutes",
        },
    )
    assert patch_res.status_code == 200
    act = patch_res.json()
    assert act["action_id"] == action_1_id
    assert act["status"] == "in_progress"
    assert act["notes"] == "Spoke to associate shooter, ETA 15 minutes"
    assert act["progress"]["in_progress_actions"] == 1


# ==============================================================================
# 8. Rejecting invalid status values
# ==============================================================================


def test_reject_invalid_status_values(client_and_events: tuple[TestClient, str, str]) -> None:
    """Verify 422 Unprocessable Entity when client passes unsupported status strings."""
    client, event_1, _ = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="rain", severity=3)

    # 1. Invalid status in POST
    bad_post = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": plan, "status": "all_good_now"},
    )
    assert bad_post.status_code == 422

    # 2. Save valid record
    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": plan},
    )
    rec_id = save_res.json()["recovery_id"]
    act_id = save_res.json()["actions"][0]["action_id"]

    # 3. Invalid status on PATCH recovery
    bad_patch_rec = client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}",
        json={"status": "abandoned"},
    )
    assert bad_patch_rec.status_code == 422

    # 4. Invalid status on PATCH action
    bad_patch_act = client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_id}",
        json={"status": "waiting_forever"},
    )
    assert bad_patch_act.status_code == 422


# ==============================================================================
# 9. Enforcing text-length limits
# ==============================================================================


def test_enforce_text_length_limits(client_and_events: tuple[TestClient, str, str]) -> None:
    """Verify 422 Unprocessable Entity when description or notes exceed 1000 characters."""
    client, event_1, _ = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="rain", severity=3)

    long_text = "A" * 1001

    # 1. Long description on POST
    bad_post = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": plan, "description": long_text},
    )
    assert bad_post.status_code == 422

    # 2. Save valid record
    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": plan},
    )
    rec_id = save_res.json()["recovery_id"]
    act_id = save_res.json()["actions"][0]["action_id"]

    # 3. Long description on PATCH recovery
    bad_patch_desc = client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}",
        json={"description": long_text},
    )
    assert bad_patch_desc.status_code == 422

    # 4. Long notes on PATCH action
    bad_patch_notes = client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_id}",
        json={"notes": long_text},
    )
    assert bad_patch_notes.status_code == 422


# ==============================================================================
# 10. Correct recovery progress counts
# ==============================================================================


def test_correct_recovery_progress_counts(client_and_events: tuple[TestClient, str, str]) -> None:
    """Verify summary counts and completion percentage update accurately on action status changes."""
    client, event_1, _ = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="caterer_cancel", severity=3)

    custom_actions = [
        {"title": "Action 1", "description": "Triage step 1", "priority": 1},
        {"title": "Action 2", "description": "Triage step 2", "priority": 2},
        {"title": "Action 3", "description": "Triage step 3", "priority": 2},
        {"title": "Action 4", "description": "Triage step 4", "priority": 3},
    ]

    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={
            "crisis_type": "caterer_cancel",
            "severity": 3,
            "recovery_plan": plan,
            "actions": custom_actions,
        },
    )
    rec = save_res.json()
    rec_id = rec["recovery_id"]
    act_ids = [a["action_id"] for a in rec["actions"]]
    assert len(act_ids) == 4

    # Baseline: 4 pending, 0%
    prog0 = rec["progress"]
    assert prog0["total_actions"] == 4
    assert prog0["pending_actions"] == 4
    assert prog0["completed_actions"] == 0
    assert prog0["completion_percentage"] == 0.0

    # Step 1: Update action 1 to in_progress
    client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_ids[0]}",
        json={"status": "in_progress"},
    )
    rec1 = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}").json()
    assert rec1["progress"]["pending_actions"] == 3
    assert rec1["progress"]["in_progress_actions"] == 1
    assert rec1["progress"]["completed_actions"] == 0
    assert rec1["progress"]["completion_percentage"] == 0.0

    # Step 2: Complete action 1 (1/4 = 25.0%)
    client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_ids[0]}",
        json={"status": "completed"},
    )
    rec2 = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}").json()
    assert rec2["progress"]["pending_actions"] == 3
    assert rec2["progress"]["in_progress_actions"] == 0
    assert rec2["progress"]["completed_actions"] == 1
    assert rec2["progress"]["completion_percentage"] == 25.0

    # Step 3: Complete action 2 (2/4 = 50.0%)
    client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_ids[1]}",
        json={"status": "completed"},
    )
    rec3 = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}").json()
    assert rec3["progress"]["completed_actions"] == 2
    assert rec3["progress"]["completion_percentage"] == 50.0


# ==============================================================================
# 11. Avoiding automatic resolution when actions remain incomplete
# ==============================================================================


def test_avoiding_automatic_resolution_when_actions_remain_incomplete(
    client_and_events: tuple[TestClient, str, str],
) -> None:
    """Verify recovery does not prematurely resolve while any action is pending or in progress."""
    client, event_1, _ = client_and_events
    plan = _evaluate_crisis(client, event_1, crisis_type="venue_double_booked", severity=3)

    custom_actions = [
        {"title": "Check contract", "description": "Verify hall booking clause", "priority": 1},
        {"title": "Talk to manager", "description": "Meet hall manager in cabin", "priority": 1},
        {"title": "Arrange banquet B", "description": "Partition hall B backup", "priority": 2},
    ]

    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={
            "crisis_type": "venue_double_booked",
            "severity": 3,
            "recovery_plan": plan,
            "actions": custom_actions,
        },
    )
    rec = save_res.json()
    rec_id = rec["recovery_id"]
    act_ids = [a["action_id"] for a in rec["actions"]]

    # When created, status is open (not resolved)
    assert rec["status"] == "open"

    # Complete action 1: actions remain incomplete (2 pending) -> status is in_progress, NOT resolved
    client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_ids[0]}",
        json={"status": "completed"},
    )
    rec_step1 = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}").json()
    assert rec_step1["status"] == "in_progress"
    assert rec_step1["status"] != "resolved"

    # Complete action 2: action 3 is still pending -> status remains in_progress, NOT resolved
    client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_ids[1]}",
        json={"status": "completed"},
    )
    rec_step2 = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}").json()
    assert rec_step2["status"] == "in_progress"
    assert rec_step2["status"] != "resolved"

    # Complete final action 3: all actions are now completed -> status automatically transitions to resolved
    client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_ids[2]}",
        json={"status": "completed"},
    )
    rec_step3 = client.get(f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}").json()
    assert rec_step3["status"] == "resolved"
    assert rec_step3["progress"]["completion_percentage"] == 100.0


# ==============================================================================
# 12. Ensuring history updates do not mutate unrelated budget, timeline, checklist
# ==============================================================================


def test_recovery_updates_do_not_mutate_budget_timeline_or_checklist(
    client_and_events: tuple[TestClient, str, str],
) -> None:
    """Verify that saving or updating recovery records never silently modifies event resources."""
    client, event_1, _ = client_and_events

    # Fetch initial state of event resources
    budget_before = client.get(f"/api/v1/events/{event_1}/budget").json()
    timeline_before = client.get(f"/api/v1/events/{event_1}/timeline").json()
    checklist_before = client.get(f"/api/v1/events/{event_1}/vendors/checklist").json()

    # Perform full recovery history operations
    plan = _evaluate_crisis(client, event_1, crisis_type="rain", severity=3)
    save_res = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": plan},
    )
    rec_id = save_res.json()["recovery_id"]
    act_id = save_res.json()["actions"][0]["action_id"]

    # Update recovery record
    client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}",
        json={"status": "in_progress", "description": "Active coordination in progress"},
    )

    # Update action item
    client.patch(
        f"/api/v1/events/{event_1}/crisis/recoveries/{rec_id}/actions/{act_id}",
        json={"status": "completed", "notes": "Completed initial drainage"},
    )

    # Fetch state after recovery updates
    budget_after = client.get(f"/api/v1/events/{event_1}/budget").json()
    timeline_after = client.get(f"/api/v1/events/{event_1}/timeline").json()
    checklist_after = client.get(f"/api/v1/events/{event_1}/vendors/checklist").json()

    # Must be 100% identical
    assert budget_before == budget_after
    assert timeline_before["milestones"] == timeline_after["milestones"]
    assert checklist_before["items"] == checklist_after["items"]
    assert checklist_before["summary"] == checklist_after["summary"]


# ==============================================================================
# 13. Handling missing or malformed recovery plans
# ==============================================================================


def test_handling_missing_or_malformed_recovery_plans(
    client_and_events: tuple[TestClient, str, str],
) -> None:
    """Verify 422 response when recovery_plan is omitted, null, or structurally invalid."""
    client, event_1, _ = client_and_events

    # 1. Missing recovery_plan key entirely
    res_missing = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3},
    )
    assert res_missing.status_code == 422

    # 2. Null recovery_plan
    res_null = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": None},
    )
    assert res_null.status_code == 422

    # 3. String instead of dict
    res_str = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={"crisis_type": "rain", "severity": 3, "recovery_plan": "not a plan object"},
    )
    assert res_str.status_code == 422

    # 4. Malformed recovery_plan (missing required immediate_actions)
    res_malformed = client.post(
        f"/api/v1/events/{event_1}/crisis/recoveries",
        json={
            "crisis_type": "rain",
            "severity": 3,
            "recovery_plan": {
                "event_id": event_1,
                "event_type": "wedding",
                "severity": 3,
                # immediate_actions omitted
            },
        },
    )
    assert res_malformed.status_code == 422


# ==============================================================================
# 14. Preserving existing tests and crisis dataset integrity
# ==============================================================================


def test_crisis_scenarios_dataset_preserved() -> None:
    """Ensure data/crisis_scenarios.csv is untouched and contains exact 5000 records."""
    csv_path = Path("data/crisis_scenarios.csv")
    assert csv_path.exists()
    scenarios = load_crisis_scenarios(csv_path)
    assert len(scenarios) == 5000
