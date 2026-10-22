"""Automated tests for Event-Specific Budget Planning (Prompt 9).

Validates:
- Deterministic 8-category budget allocation from saved event profiles.
- Wedding, birthday, and community event budget calculations.
- Exact allocation totals, integer INR amounts, and percentage calculations.
- Handling of edge cases (uneven divisions, min/max limits).
- Deterministic constraint warnings and mathematical explanations.
- Budget recalculation following PATCH profile updates.
- Event budget rebalancing endpoint protecting essential categories.
- Operation without Gemini API keys and in demo mode with zero external network calls.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import AIMode, Settings
from app.main import create_app
from app.schemas import (
    CANONICAL_BUDGET_CATEGORIES,
    CityTier,
    EventBudgetBreakdown,
    EventBudgetPlanResponse,
    EventType,
)
from app.services.budget import (
    compute_budget_warnings,
    generate_budget_explanation,
)


# ==============================================================================
# 1. Schema & Deterministic Helper Unit Tests
# ==============================================================================


def test_event_budget_breakdown_dict_access() -> None:
    """Verify that EventBudgetBreakdown supports dictionary-style key access and get()."""
    breakdown = EventBudgetBreakdown(
        venue=300_000,
        catering=250_000,
        decor=150_000,
        photo_video=100_000,
        attire_beauty=80_000,
        entertainment=50_000,
        logistics=40_000,
        buffer=30_000,
        total_budget_inr=1_000_000,
    )
    # Attribute access
    assert breakdown.venue == 300_000
    assert breakdown.catering == 250_000

    # Dict-like item access
    assert breakdown["venue"] == 300_000
    assert breakdown["catering"] == 250_000
    assert breakdown["buffer"] == 30_000

    # Dict-like get method
    assert breakdown.get("decor") == 150_000
    assert breakdown.get("unknown_category", 0) == 0

    # KeyError on invalid category
    with pytest.raises(KeyError):
        _ = breakdown["non_existent_category"]


def test_compute_budget_warnings_tight_wedding_per_guest() -> None:
    """Verify deterministic warnings when wedding budget per guest is under ₹1,500."""
    allocations = EventBudgetBreakdown(
        venue=100_000,
        catering=150_000,
        decor=50_000,
        photo_video=40_000,
        attire_beauty=30_000,
        entertainment=20_000,
        logistics=60_000,
        buffer=50_000,
        total_budget_inr=500_000,
    )
    warnings = compute_budget_warnings(
        total_budget_inr=500_000,
        guest_count=500,  # ₹1,000 per guest (< ₹1,500)
        event_type=EventType.WEDDING,
        allocations=allocations,
    )
    assert len(warnings) >= 1
    assert any("tight for a wedding celebration" in w for w in warnings)
    assert any("₹1,000" in w for w in warnings)


def test_compute_budget_warnings_near_minimum_platform_budget() -> None:
    """Verify warning when total budget is <= ₹25,000 (near platform min of ₹10,000)."""
    allocations = EventBudgetBreakdown(
        venue=3_000,
        catering=4_000,
        decor=2_000,
        photo_video=2_000,
        attire_beauty=1_000,
        entertainment=1_000,
        logistics=1_000,
        buffer=1_000,
        total_budget_inr=15_000,
    )
    warnings = compute_budget_warnings(
        total_budget_inr=15_000,
        guest_count=20,
        event_type=EventType.BIRTHDAY,
        allocations=allocations,
    )
    assert any("near the entry platform threshold" in w for w in warnings)
    assert any("Catering allocation is" in w for w in warnings)  # ₹4,000 < ₹5,000


def test_generate_budget_explanation_deterministic_content() -> None:
    """Verify explanation contains all required mathematical statements and disclaimers."""
    allocations = EventBudgetBreakdown(
        venue=750_000,
        catering=600_000,
        decor=350_000,
        photo_video=250_000,
        attire_beauty=200_000,
        entertainment=150_000,
        logistics=100_000,
        buffer=100_000,
        total_budget_inr=2_500_000,
    )
    percentages = {"buffer": 4.0}
    explanation = generate_budget_explanation(
        total_budget_inr=2_500_000,
        event_type=EventType.WEDDING,
        city_tier=CityTier.METRO,
        allocations=allocations,
        percentages=percentages,
    )
    assert "₹2,500,000" in explanation
    assert "Hamilton-Hare largest remainder method" in explanation
    assert "wedding" in explanation
    assert "metro" in explanation
    assert "zero unallocated balance" in explanation
    assert "contingency buffer of ₹100,000 (4.0%" in explanation
    assert "not binding vendor quotations" in explanation


# ==============================================================================
# 2. Integration Tests: GET /api/v1/events/{event_id}/budget
# ==============================================================================


def test_get_event_budget_wedding_metro_success(client: TestClient) -> None:
    """Verify retrieving budget plan for a saved wedding profile."""
    # 1. Create a wedding profile
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 250,
            "total_budget_inr": 2_500_000,
            "city_tier": "metro",
            "city": "Mumbai",
            "event_name": "Royal Wedding",
        },
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    # 2. Fetch budget plan
    res = client.get(f"/api/v1/events/{event_id}/budget")
    assert res.status_code == 200
    plan = res.json()

    # Core metadata
    assert plan["event_id"] == event_id
    assert plan["total_budget_inr"] == 2_500_000
    assert plan["currency"] == "INR"
    assert plan["remaining_budget_inr"] == 0

    # 8 Canonical Categories
    allocations = plan["allocations"]
    assert set(CANONICAL_BUDGET_CATEGORIES).issubset(set(allocations.keys()))
    cat_sum = sum(allocations[cat] for cat in CANONICAL_BUDGET_CATEGORIES)
    assert cat_sum == 2_500_000

    # Percentages
    percentages = plan["allocation_percentages"]
    for cat in CANONICAL_BUDGET_CATEGORIES:
        expected_pct = round((allocations[cat] / 2_500_000) * 100.0, 2)
        assert percentages[cat] == expected_pct

    # Explanation and warnings
    assert "Hamilton-Hare" in plan["explanation"]
    assert "not binding vendor quotations" in plan["explanation"]
    assert isinstance(plan["warnings"], list)


def test_get_event_budget_birthday_tier2_success(client: TestClient) -> None:
    """Verify retrieving budget plan for a saved birthday profile."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "birthday",
            "guest_count": 60,
            "total_budget_inr": 180_000,
            "city_tier": "tier2",
            "city": "Jaipur",
        },
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/budget")
    assert res.status_code == 200
    plan = res.json()

    assert plan["event_id"] == event_id
    assert plan["total_budget_inr"] == 180_000
    allocations = plan["allocations"]
    cat_sum = sum(allocations[cat] for cat in CANONICAL_BUDGET_CATEGORIES)
    assert cat_sum == 180_000
    assert plan["remaining_budget_inr"] == 0


def test_get_event_budget_community_event_tier3_success(client: TestClient) -> None:
    """Verify retrieving budget plan for a saved community event profile."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "community_event",
            "guest_count": 400,
            "total_budget_inr": 450_000,
            "city_tier": "tier3",
            "city": "Warangal",
        },
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/budget")
    assert res.status_code == 200
    plan = res.json()

    assert plan["event_id"] == event_id
    assert plan["total_budget_inr"] == 450_000
    allocations = plan["allocations"]
    cat_sum = sum(allocations[cat] for cat in CANONICAL_BUDGET_CATEGORIES)
    assert cat_sum == 450_000


def test_get_event_budget_uneven_division_edge_case(client: TestClient) -> None:
    """Verify that uneven amounts (e.g. ₹100,007) sum exactly to the last rupee."""
    create_res = client.post(
        "/api/v1/events",
        json={
            "event_type": "wedding",
            "guest_count": 80,
            "total_budget_inr": 100_007,
            "city_tier": "metro",
        },
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    res = client.get(f"/api/v1/events/{event_id}/budget")
    assert res.status_code == 200
    plan = res.json()
    assert plan["total_budget_inr"] == 100_007
    allocations = plan["allocations"]
    cat_sum = sum(allocations[cat] for cat in CANONICAL_BUDGET_CATEGORIES)
    assert cat_sum == 100_007
    assert plan["remaining_budget_inr"] == 0


def test_get_event_budget_configured_limits(client: TestClient) -> None:
    """Verify budget calculations at platform minimum (₹10,000) and maximum (₹50,000,000)."""
    # 1. Minimum limit: ₹10,000
    res_min_create = client.post(
        "/api/v1/events",
        json={"event_type": "birthday", "guest_count": 15, "total_budget_inr": 10_000},
    )
    assert res_min_create.status_code == 201
    min_id = res_min_create.json()["event_id"]

    res_min_budget = client.get(f"/api/v1/events/{min_id}/budget")
    assert res_min_budget.status_code == 200
    min_plan = res_min_budget.json()
    assert min_plan["total_budget_inr"] == 10_000
    assert sum(min_plan["allocations"][cat] for cat in CANONICAL_BUDGET_CATEGORIES) == 10_000
    assert len(min_plan["warnings"]) >= 1  # Should warn about entry platform threshold

    # 2. Maximum limit: ₹50,000,000
    res_max_create = client.post(
        "/api/v1/events",
        json={"event_type": "wedding", "guest_count": 1000, "total_budget_inr": 50_000_000},
    )
    assert res_max_create.status_code == 201
    max_id = res_max_create.json()["event_id"]

    res_max_budget = client.get(f"/api/v1/events/{max_id}/budget")
    assert res_max_budget.status_code == 200
    max_plan = res_max_budget.json()
    assert max_plan["total_budget_inr"] == 50_000_000
    assert sum(max_plan["allocations"][cat] for cat in CANONICAL_BUDGET_CATEGORIES) == 50_000_000


def test_get_event_budget_404_not_found(client: TestClient) -> None:
    """Verify that requesting budget for a non-existent event returns standard 404."""
    res = client.get("/api/v1/events/EV-NOTREAL123/budget")
    assert res.status_code == 404
    err = res.json()["error"]
    assert err["code"] == "HTTP_ERROR"
    assert "not found" in err["message"].lower()


# ==============================================================================
# 3. Recalculation & Rebalancing Tests
# ==============================================================================


def test_budget_recalculation_after_patch_profile(client: TestClient) -> None:
    """Verify that changing total_budget_inr via PATCH immediately updates GET budget response."""
    # 1. Create event with ₹1,000,000
    create_res = client.post(
        "/api/v1/events",
        json={"event_type": "wedding", "guest_count": 150, "total_budget_inr": 1_000_000},
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]

    plan1 = client.get(f"/api/v1/events/{event_id}/budget").json()
    assert plan1["total_budget_inr"] == 1_000_000
    assert sum(plan1["allocations"][cat] for cat in CANONICAL_BUDGET_CATEGORIES) == 1_000_000

    # 2. PATCH profile to ₹3,200,000
    patch_res = client.patch(
        f"/api/v1/events/{event_id}",
        json={"total_budget_inr": 3_200_000},
    )
    assert patch_res.status_code == 200

    # 3. Fetch budget again: MUST reflect ₹3,200,000 immediately without stale data
    plan2 = client.get(f"/api/v1/events/{event_id}/budget").json()
    assert plan2["total_budget_inr"] == 3_200_000
    assert sum(plan2["allocations"][cat] for cat in CANONICAL_BUDGET_CATEGORIES) == 3_200_000
    assert plan2["allocations"]["venue"] > plan1["allocations"]["venue"]


def test_rebalance_event_budget_endpoint(client: TestClient) -> None:
    """Verify POST /api/v1/events/{event_id}/budget/rebalance applies priority-based trimming."""
    # 1. Create event with ₹2,000,000
    create_res = client.post(
        "/api/v1/events",
        json={"event_type": "wedding", "guest_count": 200, "total_budget_inr": 2_000_000},
    )
    assert create_res.status_code == 201
    event_id = create_res.json()["event_id"]
    initial_catering = create_res.json()["budget"]["catering"]
    initial_buffer = create_res.json()["budget"]["buffer"]

    # 2. Rebalance downwards with strict_protect=True (protects catering & buffer)
    rebalance_res = client.post(
        f"/api/v1/events/{event_id}/budget/rebalance",
        json={"new_total_budget_inr": 1_700_000, "strict_protect": True},
    )
    assert rebalance_res.status_code == 200
    rebal_data = rebalance_res.json()
    assert rebal_data["new_total_inr"] == 1_700_000
    assert rebal_data["protected_preserved"] is True
    assert rebal_data["allocations"]["catering"] == initial_catering
    assert rebal_data["allocations"]["buffer"] == initial_buffer

    # 3. Confirm that subsequent GET /api/v1/events/{event_id}/budget reflects the rebalanced budget
    budget_plan = client.get(f"/api/v1/events/{event_id}/budget").json()
    assert budget_plan["total_budget_inr"] == 1_700_000
    assert sum(budget_plan["allocations"][cat] for cat in CANONICAL_BUDGET_CATEGORIES) == 1_700_000


def test_rebalance_event_budget_errors(client: TestClient) -> None:
    """Verify 404 for unknown events and 422 for out-of-bounds budgets on rebalance."""
    # 404 on non-existent event
    res_404 = client.post(
        "/api/v1/events/EV-GHOST/budget/rebalance",
        json={"new_total_budget_inr": 500_000},
    )
    assert res_404.status_code == 404

    # Create real event
    create_res = client.post(
        "/api/v1/events",
        json={"event_type": "wedding", "guest_count": 100, "total_budget_inr": 1_000_000},
    )
    event_id = create_res.json()["event_id"]

    # 422 on budget below minimum (< ₹10,000)
    res_low = client.post(
        f"/api/v1/events/{event_id}/budget/rebalance",
        json={"new_total_budget_inr": 5_000},
    )
    assert res_low.status_code == 422

    # 422 on budget above maximum (> ₹50,000,000)
    res_high = client.post(
        f"/api/v1/events/{event_id}/budget/rebalance",
        json={"new_total_budget_inr": 60_000_000},
    )
    assert res_high.status_code == 422


# ==============================================================================
# 4. Zero Gemini / Demo Mode / Isolation Tests
# ==============================================================================


def test_event_budget_plan_zero_gemini_calls_and_demo_mode() -> None:
    """Verify that budget planning executes 100% locally with no Gemini or network calls."""
    isolated_settings = Settings(
        ai_mode=AIMode.DEMO,
        gemini_api_key=None,
    )
    app = create_app(settings=isolated_settings)

    with TestClient(app) as local_client:
        # Create event
        create_res = local_client.post(
            "/api/v1/events",
            json={
                "event_type": "birthday",
                "guest_count": 30,
                "total_budget_inr": 120_000,
            },
        )
        assert create_res.status_code == 201
        event_id = create_res.json()["event_id"]

        # Patch Gemini client to ensure it is NEVER accessed
        with patch("google.genai.Client", side_effect=AssertionError("Gemini must never be called for budget planning")):
            res = local_client.get(f"/api/v1/events/{event_id}/budget")
            assert res.status_code == 200
            data = res.json()
            assert data["total_budget_inr"] == 120_000
            assert sum(data["allocations"][cat] for cat in CANONICAL_BUDGET_CATEGORIES) == 120_000
