"""Reliability and lifecycle tests for PlanProof AI.

Verifies application startup, lifespan dataset loading, in-memory caching,
custom settings injection, and graceful handling of degraded dataset states.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.data_loader import DatasetRepository
from app.main import create_app


def test_lifespan_loads_datasets_into_state(client: TestClient) -> None:
    """Verify that lifespan initializes dataset_repo into app.state at startup."""
    app = client.app
    repo: DatasetRepository | None = getattr(app.state, "dataset_repo", None)
    assert repo is not None
    assert isinstance(repo, DatasetRepository)
    assert repo.is_loaded is True
    assert len(repo.scenarios) > 0
    assert repo.budget_splits is not None
    assert repo.vendor_checklists is not None


def test_repeated_requests_do_not_reload_datasets(client: TestClient) -> None:
    """Verify that repeated requests reuse the in-memory repository without reloading from disk."""
    app = client.app
    initial_repo = getattr(app.state, "dataset_repo", None)
    initial_id = id(initial_repo)

    # Perform multiple API requests
    for _ in range(5):
        res = client.get("/api/v1/data-status")
        assert res.status_code == 200

    # The in-memory repository object instance must remain identical
    current_repo = getattr(app.state, "dataset_repo", None)
    assert id(current_repo) == initial_id


def test_isolated_settings_injection(tmp_path: Path, valid_csv_file: Path) -> None:
    """Verify that create_app accepts isolated settings without modifying defaults."""
    custom_settings = Settings(
        app_name="Isolated Test App",
        app_env="test",
        crisis_dataset_path=valid_csv_file,
    )
    isolated_app = create_app(settings=custom_settings)

    with TestClient(isolated_app) as isolated_client:
        res = isolated_client.get("/health")
        assert res.status_code == 200
        assert res.json()["app"] == "Isolated Test App"
        assert res.json()["environment"] == "test"


def test_missing_dataset_during_lifespan_handled_gracefully(tmp_path: Path) -> None:
    """Verify that missing dataset file during startup sets load_error and returns 503 safely."""
    missing_csv = tmp_path / "non_existent_crisis.csv"
    bad_settings = Settings(
        app_name="Degraded Test App",
        crisis_dataset_path=missing_csv,
    )
    app = create_app(settings=bad_settings)

    with TestClient(app) as test_client:
        res = test_client.get("/api/v1/data-status")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "error"
        assert data["dataset_loaded"] is False
        assert data["row_count"] == 0
        # Ensure absolute filesystem path is not exposed in status summary
        assert str(tmp_path) not in res.text


def test_empty_dataset_during_lifespan_handled_gracefully(tmp_path: Path) -> None:
    """Verify that empty CSV during startup results in a graceful degraded status."""
    empty_csv = tmp_path / "empty_crisis.csv"
    empty_csv.write_text("", encoding="utf-8")
    bad_settings = Settings(
        app_name="Empty Dataset App",
        crisis_dataset_path=empty_csv,
    )
    app = create_app(settings=bad_settings)

    with TestClient(app) as test_client:
        res = test_client.get("/api/v1/data-status")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "error"
        assert data["dataset_loaded"] is False
