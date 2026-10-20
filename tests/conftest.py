"""Pytest configuration and shared fixtures for PlanProof AI test suite."""

import csv
import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.data_loader import REQUIRED_CRISIS_COLUMNS
from app.main import create_app


@pytest.fixture
def sample_crisis_row() -> dict[str, str]:
    """Return a single valid crisis scenario row as string dictionary."""
    return {
        "id": "CR0000001",
        "event_type": "wedding",
        "city_tier": "metro",
        "guest_count": "150",
        "phase": "event_day",
        "crisis_type": "rain",
        "severity": "2",
        "description": "Outdoor lawn flooded",
        "recommended_fix": "Move to indoor banquet hall",
        "cost_impact_pct_of_budget": "3.5",
        "message_target": "guests",
        "synthetic": "True",
    }


@pytest.fixture
def valid_csv_file(tmp_path: Path, sample_crisis_row: dict[str, str]) -> Path:
    """Create a temporary valid CSV file with sample data."""
    csv_path = tmp_path / "valid_crisis.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(REQUIRED_CRISIS_COLUMNS))
        writer.writeheader()
        writer.writerow(sample_crisis_row)
    return csv_path


@pytest.fixture
def valid_budget_json_file(tmp_path: Path) -> Path:
    """Create a temporary valid budget splits JSON file."""
    json_path = tmp_path / "budget_splits.json"
    data = {
        "_note": "Synthetic test assumptions",
        "splits": {
            "wedding": {
                "metro": {
                    "venue": 26,
                    "catering": 30,
                    "decor": 11,
                    "photo_video": 9,
                    "attire_beauty": 10,
                    "entertainment": 5,
                    "logistics": 3,
                    "buffer": 6,
                }
            }
        },
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return json_path


@pytest.fixture
def valid_vendor_json_file(tmp_path: Path) -> Path:
    """Create a temporary valid vendor checklists JSON file."""
    json_path = tmp_path / "vendor_checklists.json"
    data = {
        "_note": "Synthetic test assumptions",
        "vendors": [
            {
                "type": "venue",
                "lead_time_weeks": 26,
                "typical_advance_pct": 30,
                "ask_before_booking": ["Indoor backup?"],
            }
        ],
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return json_path


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test client using application lifespan with repository datasets."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
