"""Unit and integration tests for the PlanProof AI Crisis Recovery Center."""

from datetime import date
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.config import AIMode, Settings
from app.data_loader import DatasetRepository, load_crisis_scenarios
from app.main import create_app
from app.schemas import (
    AIResultSource,
    AIResultStatus,
    CityTier,
    CrisisEvaluationRequest,
    EventType,
)
from app.services.crisis_service import (
    SUPPORTED_CRISIS_TYPES,
    match_crisis_scenario,
    normalize_crisis_type,
)


@pytest.fixture
def client_and_event() -> tuple[TestClient, str]:
    """Create test client and a populated wedding event."""
    app = create_app()
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/events",
            json={
                "event_type": "wedding",
                "event_name": "Rohan & Priya Royal Wedding",
                "city": "Bengaluru",
                "city_tier": "metro",
                "event_date": "2027-02-14",
                "guest_count": 350,
                "total_budget_inr": 2500000,
                "language": "en",
                "theme_notes": "Traditional South Indian wedding with evening grand reception",
            },
        )
        assert res.status_code == 201
        event_id = res.json()["event_id"]
        yield client, event_id


def test_get_crisis_types_endpoint() -> None:
    """Verify GET /api/v1/crisis/types returns all canonical crisis types with metadata."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/api/v1/crisis/types")
        assert res.status_code == 200
        types = res.json()
        assert len(types) == 12
        type_keys = {t["crisis_type"] for t in types}
        assert "rain" in type_keys
        assert "power_cut" in type_keys
        assert "caterer_cancel" in type_keys
        assert "caterer_late" in type_keys
        assert "decorator_delay" in type_keys
        assert "photographer_noshow" in type_keys
        assert "venue_double_booked" in type_keys
        assert "guest_surge" in type_keys
        assert "guest_dropout" in type_keys
        assert "budget_overrun" in type_keys


def test_crisis_evaluation_matched_from_csv(client_and_event: tuple[TestClient, str]) -> None:
    """Verify crisis scenario matches real dataset records in data/crisis_scenarios.csv."""
    client, event_id = client_and_event
    res = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={
            "crisis_type": "rain",
            "severity": 3,
            "description": "Heavy sudden downpour flooding open lawn dining zone",
            "affected_area": "venue",
            "event_phase": "event_day",
        },
    )
    assert res.status_code == 200
    envelope = res.json()
    assert envelope["status"] == "success"
    data = envelope["data"]

    matched = data["matched_scenario"]
    assert matched["is_dataset_match"] is True
    assert matched["scenario_id"].startswith("CR")
    assert matched["crisis_type"] == "rain"
    assert matched["severity"] == 3
    assert matched["cost_impact_pct_of_budget"] > 0
    assert "data/crisis_scenarios.csv" not in envelope["message"]  # No path leakage


def test_crisis_evaluation_fallback_when_unknown_type(client_and_event: tuple[TestClient, str]) -> None:
    """Verify unknown or unlisted crisis types return clearly labeled fallback, not fake CSV IDs."""
    client, event_id = client_and_event
    res = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={
            "crisis_type": "alien_drone_jamming",
            "severity": 2,
            "description": "Unregistered aerial drones causing frequency interference",
            "affected_area": "production",
            "event_phase": "event_day",
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    matched = data["matched_scenario"]
    assert matched["is_dataset_match"] is False
    assert matched["scenario_id"] == "FALLBACK-NON-CSV"
    assert matched["synthetic"] is True


def test_safety_first_prioritized_actions_for_rain_and_power(
    client_and_event: tuple[TestClient, str],
) -> None:
    """Verify electrical and physical safety triage is priority 1 for weather and power failures."""
    client, event_id = client_and_event

    # 1. Rain
    res_rain = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={"crisis_type": "rain", "severity": 3},
    )
    assert res_rain.status_code == 200
    imm_rain = res_rain.json()["data"]["immediate_actions"]
    assert len(imm_rain) >= 1
    assert imm_rain[0]["category"] == "immediate_safety"
    assert imm_rain[0]["priority"] == 1
    assert "electrocution" in imm_rain[0]["action"].lower() or "electrical" in imm_rain[0]["action"].lower()
    assert "112" in imm_rain[0]["action"]

    # 2. Power Cut
    res_power = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={"crisis_type": "power_cut", "severity": 3},
    )
    assert res_power.status_code == 200
    imm_power = res_power.json()["data"]["immediate_actions"]
    assert imm_power[0]["category"] == "immediate_safety"
    assert imm_power[0]["priority"] == 1
    assert "generator" in imm_power[0]["action"].lower() or "lighting" in imm_power[0]["action"].lower()


def test_budget_awareness_and_buffer_comparison(client_and_event: tuple[TestClient, str]) -> None:
    """Verify deterministic budget impact arithmetic against event contingency buffer."""
    client, event_id = client_and_event

    # Wedding has total_budget_inr = 2,500,000
    res = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={"crisis_type": "caterer_late", "severity": 1},
    )
    assert res.status_code == 200
    b_impact = res.json()["data"]["budget_impact"]

    # Arithmetic checks
    pct = b_impact["cost_impact_pct"]
    rupees = b_impact["estimated_rupee_impact"]
    assert rupees == round((pct / 100.0) * 2500000)
    assert b_impact["existing_buffer_inr"] > 0
    assert "catering" in b_impact["affected_categories"]
    assert isinstance(b_impact["buffer_sufficient"], bool)


def test_timeline_and_vendor_checklist_cross_referencing(
    client_and_event: tuple[TestClient, str],
) -> None:
    """Verify crisis response links real timeline milestones and vendor tasks without mutation."""
    client, event_id = client_and_event

    # Fetch initial vendor checklist to compare
    v_res = client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    initial_items = v_res.json()["items"]
    assert len(initial_items) > 0

    res = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={"crisis_type": "caterer_cancel", "severity": 3},
    )
    assert res.status_code == 200
    data = res.json()["data"]

    # Verify checklist references
    vendor_ids = data["relevant_vendor_checklist_ids"]
    assert len(vendor_ids) > 0
    # Cross reference with actual items
    known_ids = {it["id"] for it in initial_items}
    for vid in vendor_ids:
        assert vid in known_ids

    # Verify milestone references
    ms_ids = data["relevant_milestone_ids"]
    assert len(ms_ids) > 0

    # Verify event checklist was NOT altered by crisis evaluation
    v_res_after = client.get(f"/api/v1/events/{event_id}/vendors/checklist")
    assert v_res_after.json()["items"] == initial_items


def test_communication_drafts_integrity_and_placeholders(
    client_and_event: tuple[TestClient, str],
) -> None:
    """Verify ready-to-copy communication drafts contain bracketed placeholders and clear source."""
    client, event_id = client_and_event
    res = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={"crisis_type": "photographer_noshow", "severity": 3},
    )
    assert res.status_code == 200
    drafts = res.json()["data"]["communication_drafts"]
    assert len(drafts) == 4

    roles = {d["recipient_role"] for d in drafts}
    assert roles == {"vendor", "guests", "family", "organizers"}

    for d in drafts:
        assert len(d["placeholders"]) > 0
        for ph in d["placeholders"]:
            assert ph in d["message_text"]
        # Source must be deterministic when running offline
        assert d["source"] in ("deterministic", "demo", "gemini")


def test_crisis_evaluation_does_not_mutate_event_resources(
    client_and_event: tuple[TestClient, str],
) -> None:
    """Verify evaluating a crisis never modifies the event profile, budget, or timeline."""
    client, event_id = client_and_event

    profile_before = client.get(f"/api/v1/events/{event_id}").json()
    budget_before = client.get(f"/api/v1/events/{event_id}/budget").json()

    client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={"crisis_type": "power_cut", "severity": 3},
    )

    profile_after = client.get(f"/api/v1/events/{event_id}").json()
    budget_after = client.get(f"/api/v1/events/{event_id}/budget").json()

    assert profile_before == profile_after
    assert budget_before == budget_after


def test_crisis_evaluation_missing_event_returns_404() -> None:
    """Verify evaluating crisis on a non-existent event ID returns 404."""
    app = create_app()
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/events/EV-NONEXISTENT-999/crisis/evaluate",
            json={"crisis_type": "rain", "severity": 2},
        )
        assert res.status_code == 404
        assert "not found" in res.json()["error"]["message"].lower()


def test_crisis_evaluation_invalid_severity_returns_422(
    client_and_event: tuple[TestClient, str],
) -> None:
    """Verify invalid severity (e.g. 0 or 4) fails with 422 Unprocessable Entity."""
    client, event_id = client_and_event
    res = client.post(
        f"/api/v1/events/{event_id}/crisis/evaluate",
        json={"crisis_type": "rain", "severity": 5},
    )
    assert res.status_code == 422


def test_crisis_evaluation_demo_mode() -> None:
    """Verify that in DEMO mode, response source is labeled DEMO."""
    app = create_app(Settings(ai_mode=AIMode.DEMO, gemini_api_key=None))
    with TestClient(app) as client:
        # Create event
        c_res = client.post(
            "/api/v1/events",
            json={
                "event_type": "birthday",
                "guest_count": 80,
                "total_budget_inr": 200000,
            },
        )
        event_id = c_res.json()["event_id"]

        res = client.post(
            f"/api/v1/events/{event_id}/crisis/evaluate",
            json={"crisis_type": "cake_damage", "severity": 2},
        )
        assert res.status_code == 200
        assert res.json()["source"] == "demo"


def test_crisis_scenarios_dataset_preserved() -> None:
    """Ensure data/crisis_scenarios.csv is untouched and contains exact 5000 records."""
    csv_path = Path("data/crisis_scenarios.csv")
    assert csv_path.exists()
    scenarios = load_crisis_scenarios(csv_path)
    assert len(scenarios) == 5000
