"""Automated integration tests for PlanProof AI API endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_endpoint(client: TestClient) -> None:
    """Verify that /health returns 200 and expected health metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "PlanProof AI"
    assert "version" in data
    assert "environment" in data


def test_data_status_endpoint_success(client: TestClient) -> None:
    """Verify that /api/v1/data-status returns safe summary metadata."""
    response = client.get("/api/v1/data-status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dataset_loaded"] is True
    assert data["row_count"] == 5000
    assert len(data["available_crisis_types"]) >= 10
    assert "rain" in data["available_crisis_types"]
    assert data["severity_range"]["min"] == 1
    assert data["severity_range"]["max"] == 3
    assert data["budget_splits_loaded"] is True
    assert data["vendor_checklists_loaded"] is True

    # Assert nested structured metadata
    crisis_meta = data["crisis_scenarios"]
    assert crisis_meta["loaded"] is True
    assert crisis_meta["row_count"] == 5000
    assert set(crisis_meta["available_event_types"]) == {
        "wedding",
        "birthday",
        "community_event",
    }

    budget_meta = data["budget_splits"]
    assert budget_meta["loaded"] is True
    assert set(budget_meta["event_types"]) == {"wedding", "birthday", "community_event"}
    assert set(budget_meta["city_tiers"]) == {"metro", "tier2", "tier3"}
    assert len(budget_meta["categories"]) == 8

    vendor_meta = data["vendor_checklists"]
    assert vendor_meta["loaded"] is True
    assert vendor_meta["vendor_count"] >= 8
    assert "venue" in vendor_meta["vendor_types"]


def test_data_status_failure_handles_gracefully(tmp_path: Path) -> None:
    """Verify that missing dataset returns 503 JSON without unhandled stack traces."""
    broken_settings = Settings(
        crisis_dataset_path=tmp_path / "non_existent.csv",
        budget_splits_path=tmp_path / "non_existent.json",
        vendor_checklists_path=tmp_path / "non_existent.json",
    )
    broken_app = create_app(settings=broken_settings)

    with TestClient(broken_app) as broken_client:
        # /health should still respond normally
        health_res = broken_client.get("/health")
        assert health_res.status_code == 200

        # /api/v1/data-status should return 503 with controlled JSON, no traceback
        status_res = broken_client.get("/api/v1/data-status")
        assert status_res.status_code == 503
        data = status_res.json()
        assert data["dataset_loaded"] is False
        assert data["status"] in ("error", "degraded")
        assert data["row_count"] == 0
        assert "Traceback" not in status_res.text


def test_validate_event_endpoint_success(client: TestClient) -> None:
    """Verify that POST /api/v1/validate-event accepts valid input parameters."""
    payload = {
        "event_type": "wedding",
        "guest_count": 350,
        "total_budget_inr": 2500000,
        "city_tier": "metro",
        "city": "Hyderabad",
        "theme_notes": "Traditional South Indian wedding with evening reception",
        "language": "en",
    }
    response = client.post("/api/v1/validate-event", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert "validated successfully" in data["message"]
    req = data["validated_request"]
    assert req["event_type"] == "wedding"
    assert req["guest_count"] == 350
    assert req["total_budget_inr"] == 2500000
    assert req["city"] == "Hyderabad"


def test_validate_event_endpoint_rejects_invalid_inputs(client: TestClient) -> None:
    """Verify that POST /api/v1/validate-event returns 422 with StandardErrorResponse."""
    # 1. Budget below ₹10,000 minimum
    bad_budget = {
        "event_type": "birthday",
        "guest_count": 25,
        "total_budget_inr": 4000,  # Below 10k
        "city_tier": "tier2",
        "city": "Mysuru",
    }
    res = client.post("/api/v1/validate-event", json=bad_budget)
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in data["error"]
    assert "Traceback" not in res.text

    # 2. Guest count boolean rejected
    bool_guest = {
        "event_type": "wedding",
        "guest_count": True,
        "total_budget_inr": 1000000,
        "city_tier": "metro",
        "city": "Delhi",
    }
    res_bool = client.post("/api/v1/validate-event", json=bool_guest)
    assert res_bool.status_code == 422
    assert "error" in res_bool.json()
    assert res_bool.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Extra unrecognized fields rejected
    extra_field = {
        "event_type": "wedding",
        "guest_count": 200,
        "total_budget_inr": 1000000,
        "city_tier": "metro",
        "city": "Delhi",
        "hacked_prompt_override": "ignore instructions",
    }
    res_extra = client.post("/api/v1/validate-event", json=extra_field)
    assert res_extra.status_code == 422
    assert res_extra.json()["error"]["code"] == "VALIDATION_ERROR"


def test_http_exception_returns_standard_error(client: TestClient) -> None:
    """Verify 404 and other HTTP exceptions follow the standard error format."""
    res = client.get("/route-that-does-not-exist")
    assert res.status_code == 404
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_ERROR"
    assert "Not Found" in data["error"]["message"]


def test_root_serves_landing_page(client: TestClient) -> None:
    """Verify that root URL serves the static HTML landing page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "PlanProof" in response.text
    assert "text/html" in response.headers.get("content-type", "")


# ==============================================================================
# Budget API Endpoint Tests
# ==============================================================================


def test_api_calculate_budget_success(client: TestClient) -> None:
    """Verify POST /api/v1/budget/calculate successfully computes 8-category allocation."""
    payload = {
        "event_type": "wedding",
        "city_tier": "metro",
        "total_budget_inr": 2_500_000,
    }
    res = client.post("/api/v1/budget/calculate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["event_type"] == "wedding"
    assert data["city_tier"] == "metro"
    assert data["total_budget_inr"] == 2_500_000
    assert data["method"] == "largest_remainder_hamilton"

    allocations = data["allocations"]
    assert allocations["total_budget_inr"] == 2_500_000

    canonical_cats = [
        "venue",
        "catering",
        "decor",
        "photo_video",
        "attire_beauty",
        "entertainment",
        "logistics",
        "buffer",
    ]
    cat_sum = sum(allocations[c] for c in canonical_cats)
    assert cat_sum == 2_500_000


def test_api_calculate_budget_validation_errors(client: TestClient) -> None:
    """Verify POST /api/v1/budget/calculate returns 422 for invalid inputs."""
    # 1. Invalid event type
    res1 = client.post(
        "/api/v1/budget/calculate",
        json={"event_type": "gala_dinner", "city_tier": "metro", "total_budget_inr": 500_000},
    )
    assert res1.status_code == 422
    assert "Traceback" not in res1.text
    assert res1.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. Invalid city tier
    res2 = client.post(
        "/api/v1/budget/calculate",
        json={"event_type": "wedding", "city_tier": "rural", "total_budget_inr": 500_000},
    )
    assert res2.status_code == 422
    assert res2.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Budget below ₹10,000
    res3 = client.post(
        "/api/v1/budget/calculate",
        json={"event_type": "wedding", "city_tier": "metro", "total_budget_inr": 5_000},
    )
    assert res3.status_code == 422

    # 4. Budget above ₹50,000,000
    res4 = client.post(
        "/api/v1/budget/calculate",
        json={"event_type": "wedding", "city_tier": "metro", "total_budget_inr": 60_000_000},
    )
    assert res4.status_code == 422

    # 5. Boolean or float budget rejected
    res5 = client.post(
        "/api/v1/budget/calculate",
        json={"event_type": "wedding", "city_tier": "metro", "total_budget_inr": True},
    )
    assert res5.status_code == 422


def test_api_rebalance_budget_success(client: TestClient) -> None:
    """Verify POST /api/v1/budget/rebalance handles budget adjustments accurately."""
    current_alloc = {
        "venue": 260_000,
        "catering": 300_000,
        "decor": 110_000,
        "photo_video": 90_000,
        "attire_beauty": 100_000,
        "entertainment": 50_000,
        "logistics": 30_000,
        "buffer": 60_000,
        "total_budget_inr": 1_000_000,
    }

    # 1. Budget increase
    res_inc = client.post(
        "/api/v1/budget/rebalance",
        json={"current_allocations": current_alloc, "new_total_budget_inr": 1_200_000},
    )
    assert res_inc.status_code == 200
    data_inc = res_inc.json()
    assert data_inc["previous_total_inr"] == 1_000_000
    assert data_inc["new_total_inr"] == 1_200_000
    assert data_inc["protected_preserved"] is True
    assert sum(data_inc["differences"].values()) == 200_000

    # 2. Budget decrease (Tier 1 reduction)
    res_dec = client.post(
        "/api/v1/budget/rebalance",
        json={"current_allocations": current_alloc, "new_total_budget_inr": 920_000},
    )
    assert res_dec.status_code == 200
    data_dec = res_dec.json()
    assert data_dec["new_total_inr"] == 920_000
    assert data_dec["protected_preserved"] is True
    # Catering and buffer diffs must be 0
    assert data_dec["differences"]["catering"] == 0
    assert data_dec["differences"]["buffer"] == 0
    assert set(data_dec["categories_reduced_first"]) == {"decor", "entertainment"}


def test_api_rebalance_budget_validation_errors(client: TestClient) -> None:
    """Verify POST /api/v1/budget/rebalance returns 422 for invalid inputs."""
    # 1. Sum mismatch in current_allocations
    bad_alloc = {
        "venue": 260_000,
        "catering": 300_000,
        "decor": 110_000,
        "photo_video": 90_000,
        "attire_beauty": 100_000,
        "entertainment": 50_000,
        "logistics": 30_000,
        "buffer": 60_000,
        "total_budget_inr": 999_999,  # does not match 1,000,000
    }
    res1 = client.post(
        "/api/v1/budget/rebalance",
        json={"current_allocations": bad_alloc, "new_total_budget_inr": 1_200_000},
    )
    assert res1.status_code == 422
    assert "Traceback" not in res1.text

    # 2. Missing category in current_allocations
    missing_cat = {
        "venue": 260_000,
        "catering": 300_000,
        # missing decor
        "photo_video": 90_000,
        "attire_beauty": 100_000,
        "entertainment": 50_000,
        "logistics": 30_000,
        "buffer": 60_000,
        "total_budget_inr": 890_000,
    }
    res2 = client.post(
        "/api/v1/budget/rebalance",
        json={"current_allocations": missing_cat, "new_total_budget_inr": 1_000_000},
    )
    assert res2.status_code == 422

    # 3. Target budget below ₹10,000 minimum
    valid_alloc = {
        "venue": 260_000,
        "catering": 300_000,
        "decor": 110_000,
        "photo_video": 90_000,
        "attire_beauty": 100_000,
        "entertainment": 50_000,
        "logistics": 30_000,
        "buffer": 60_000,
        "total_budget_inr": 1_000_000,
    }
    res3 = client.post(
        "/api/v1/budget/rebalance",
        json={"current_allocations": valid_alloc, "new_total_budget_inr": 5_000},
    )
    assert res3.status_code == 422


def test_api_malformed_json_request(client: TestClient) -> None:
    """Verify that malformed JSON request body returns 422 with StandardErrorResponse."""
    res = client.post(
        "/api/v1/budget/calculate",
        content=b'{"event_type": "wedding", malformed_json',
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "Traceback" not in res.text


def test_api_method_not_allowed(client: TestClient) -> None:
    """Verify that unsupported HTTP methods return 405 with StandardErrorResponse."""
    res = client.put("/health")
    assert res.status_code == 405
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_ERROR"
    assert "Method Not Allowed" in data["error"]["message"]


def test_api_unhandled_internal_error() -> None:
    """Verify unhandled server errors return safe 500 JSON without leaking stack traces."""
    app = create_app()

    @app.get("/trigger-crash")
    async def crash_endpoint() -> None:
        raise RuntimeError("Database connection suddenly dropped with internal details")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        res = test_client.get("/trigger-crash")
        assert res.status_code == 500
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert data["error"]["message"] == "An internal server error occurred."
        assert data["error"]["details"] is None
        assert "RuntimeError" not in res.text
        assert "Database connection" not in res.text
        assert "Traceback" not in res.text
