"""Automated tests for PlanProof AI data loader and validation modules."""

import csv
from pathlib import Path

import pytest

from app.data_loader import (
    DatasetEmptyError,
    DatasetMalformedError,
    DatasetNotFoundError,
    DatasetRepository,
    DatasetValidationError,
    load_budget_splits,
    load_crisis_scenarios,
    load_vendor_checklists,
)


def test_load_real_crisis_scenarios() -> None:
    """Verify that the actual 5,000-row crisis dataset loads with zero validation errors."""
    csv_path = Path("data/crisis_scenarios.csv")
    assert csv_path.exists(), "data/crisis_scenarios.csv should exist"
    scenarios = load_crisis_scenarios(csv_path)

    assert len(scenarios) == 5000
    first = scenarios[0]
    assert first.id.startswith("CR")
    assert first.severity in (1, 2, 3)
    assert first.guest_count > 0
    assert first.description
    assert first.recommended_fix


def test_load_real_budget_splits() -> None:
    """Verify that the actual budget splits JSON loads and sums to 100%."""
    json_path = Path("data/budget_splits.json")
    assert json_path.exists(), "data/budget_splits.json should exist"
    data = load_budget_splits(json_path)

    assert "splits" in data
    assert "wedding" in data["splits"]
    for event_type, tiers in data["splits"].items():
        for tier_name, categories in tiers.items():
            assert sum(categories.values()) == 100


def test_load_real_vendor_checklists() -> None:
    """Verify that the actual vendor checklists JSON loads valid vendor records."""
    json_path = Path("data/vendor_checklists.json")
    assert json_path.exists(), "data/vendor_checklists.json should exist"
    data = load_vendor_checklists(json_path)

    assert "vendors" in data
    assert len(data["vendors"]) >= 5


def test_load_missing_file_raises_not_found(tmp_path: Path) -> None:
    """Verify that attempting to load a nonexistent file raises DatasetNotFoundError."""
    non_existent = tmp_path / "does_not_exist.csv"
    with pytest.raises(DatasetNotFoundError):
        load_crisis_scenarios(non_existent)


def test_load_empty_csv_raises_empty_error(tmp_path: Path) -> None:
    """Verify that an empty file raises DatasetEmptyError."""
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("", encoding="utf-8")
    with pytest.raises(DatasetEmptyError):
        load_crisis_scenarios(empty_file)


def test_load_header_only_csv_raises_empty_error(tmp_path: Path) -> None:
    """Verify that a CSV with only a header and no data rows raises DatasetEmptyError."""
    header_only = tmp_path / "header_only.csv"
    header_only.write_text(
        "id,event_type,city_tier,guest_count,phase,crisis_type,severity,description,"
        "recommended_fix,cost_impact_pct_of_budget,message_target,synthetic\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetEmptyError):
        load_crisis_scenarios(header_only)


def test_load_missing_columns_detected(tmp_path: Path) -> None:
    """Verify that a CSV missing required columns raises DatasetMalformedError."""
    incomplete_csv = tmp_path / "missing_columns.csv"
    incomplete_csv.write_text(
        "id,event_type,city_tier\nCR0001,wedding,metro\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetMalformedError) as exc_info:
        load_crisis_scenarios(incomplete_csv)
    assert "missing required columns" in str(exc_info.value).lower()


def test_invalid_severity_rejected(tmp_path: Path, sample_crisis_row: dict[str, str]) -> None:
    """Verify that invalid severity levels (e.g. 5) raise DatasetValidationError."""
    bad_row = dict(sample_crisis_row)
    bad_row["severity"] = "5"

    bad_csv = tmp_path / "bad_severity.csv"
    with open(bad_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(bad_row.keys()))
        writer.writeheader()
        writer.writerow(bad_row)

    with pytest.raises(DatasetValidationError) as exc_info:
        load_crisis_scenarios(bad_csv)
    assert "severity" in str(exc_info.value).lower()


def test_invalid_guest_count_rejected(tmp_path: Path, sample_crisis_row: dict[str, str]) -> None:
    """Verify that non-positive guest count raises DatasetValidationError."""
    bad_row = dict(sample_crisis_row)
    bad_row["guest_count"] = "-10"

    bad_csv = tmp_path / "bad_guests.csv"
    with open(bad_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(bad_row.keys()))
        writer.writeheader()
        writer.writerow(bad_row)

    with pytest.raises(DatasetValidationError) as exc_info:
        load_crisis_scenarios(bad_csv)
    assert "guest count" in str(exc_info.value).lower()


def test_dataset_repository_lifecycle(
    valid_csv_file: Path,
    valid_budget_json_file: Path,
    valid_vendor_json_file: Path,
) -> None:
    """Verify DatasetRepository correctly loads and creates status summary."""
    repo = DatasetRepository()
    assert not repo.is_loaded

    repo.load_all(valid_csv_file, valid_budget_json_file, valid_vendor_json_file)
    assert repo.is_loaded
    assert repo.load_error is None

    summary = repo.get_status_summary()
    assert summary.status == "healthy"
    assert summary.dataset_loaded is True
    assert summary.row_count == 1
    assert "rain" in summary.available_crisis_types
    assert summary.severity_range.min == 2
    assert summary.severity_range.max == 2
