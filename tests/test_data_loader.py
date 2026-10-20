"""Automated tests for PlanProof AI data loader and strict validation modules."""

import csv
import json
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
from app.schemas import CityTier, EventPhase, EventType, MessageTarget


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


def test_crisis_supported_enums_represented() -> None:
    """Verify that all enum values for event type, tier, phase, and target exist in the dataset."""
    scenarios = load_crisis_scenarios(Path("data/crisis_scenarios.csv"))

    event_types = {s.event_type for s in scenarios}
    city_tiers = {s.city_tier for s in scenarios}
    phases = {s.phase for s in scenarios}
    targets = {s.message_target for s in scenarios}

    assert event_types == set(EventType)
    assert city_tiers == set(CityTier)
    assert phases == set(EventPhase)
    assert targets == set(MessageTarget)


def test_all_nine_budget_allocation_combinations() -> None:
    """Verify all 9 (3 event types x 3 city tiers) budget allocations total exactly 100%."""
    json_path = Path("data/budget_splits.json")
    dataset = load_budget_splits(json_path)

    for event in EventType:
        assert event in dataset.splits
        for tier in CityTier:
            assert tier in dataset.splits[event]
            alloc = dataset.splits[event][tier]
            total = (
                alloc.venue
                + alloc.catering
                + alloc.decor
                + alloc.photo_video
                + alloc.attire_beauty
                + alloc.entertainment
                + alloc.logistics
                + alloc.buffer
            )
            assert abs(total - 100.0) <= 0.01, f"{event}.{tier} total is {total}%"


def test_load_real_vendor_checklists() -> None:
    """Verify that the actual vendor checklists JSON loads valid vendor records."""
    json_path = Path("data/vendor_checklists.json")
    dataset = load_vendor_checklists(json_path)

    assert len(dataset.vendors) >= 8
    types = [v.type for v in dataset.vendors]
    assert "venue" in types
    assert "caterer" in types
    assert len(types) == len(set(types)), "Vendor types must be unique"


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


def test_invalid_event_type_rejected(tmp_path: Path, sample_crisis_row: dict[str, str]) -> None:
    """Verify that unknown event types are rejected."""
    bad_row = dict(sample_crisis_row)
    bad_row["event_type"] = "anniversary_gala"

    bad_csv = tmp_path / "bad_event.csv"
    with open(bad_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(bad_row.keys()))
        writer.writeheader()
        writer.writerow(bad_row)

    with pytest.raises(DatasetValidationError):
        load_crisis_scenarios(bad_csv)


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


def test_non_finite_cost_impact_rejected(tmp_path: Path, sample_crisis_row: dict[str, str]) -> None:
    """Verify that NaN or inf cost impact raises DatasetValidationError."""
    bad_row = dict(sample_crisis_row)
    bad_row["cost_impact_pct_of_budget"] = "nan"

    bad_csv = tmp_path / "bad_cost_nan.csv"
    with open(bad_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(bad_row.keys()))
        writer.writeheader()
        writer.writerow(bad_row)

    with pytest.raises(DatasetValidationError):
        load_crisis_scenarios(bad_csv)


def test_negative_cost_impact_validation(tmp_path: Path, sample_crisis_row: dict[str, str]) -> None:
    """Verify negative cost impact is allowed for guest_dropout, but rejected for other crises."""
    # Disallowed for rain
    bad_row = dict(sample_crisis_row)
    bad_row["crisis_type"] = "rain"
    bad_row["cost_impact_pct_of_budget"] = "-2.0"

    bad_csv = tmp_path / "bad_rain_negative.csv"
    with open(bad_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(bad_row.keys()))
        writer.writeheader()
        writer.writerow(bad_row)

    with pytest.raises(DatasetValidationError) as exc_info:
        load_crisis_scenarios(bad_csv)
    assert "guest_dropout" in str(exc_info.value)

    # Allowed for guest_dropout
    good_dropout = dict(sample_crisis_row)
    good_dropout["crisis_type"] = "guest_dropout"
    good_dropout["cost_impact_pct_of_budget"] = "-2.0"

    good_csv = tmp_path / "good_dropout.csv"
    with open(good_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(good_dropout.keys()))
        writer.writeheader()
        writer.writerow(good_dropout)

    loaded = load_crisis_scenarios(good_csv)
    assert len(loaded) == 1
    assert loaded[0].cost_impact_pct_of_budget == -2.0


def test_budget_splits_missing_category_rejected(tmp_path: Path) -> None:
    """Verify missing budget category raises DatasetValidationError."""
    bad_splits = {
        "_note": "Incomplete test",
        "splits": {
            "wedding": {
                "metro": {
                    "venue": 30,
                    "catering": 40,
                    "decor": 10,
                    "photo_video": 10,
                    "attire_beauty": 10,
                    # missing logistics, entertainment, buffer
                }
            }
        },
    }
    p = tmp_path / "bad_splits.json"
    p.write_text(json.dumps(bad_splits), encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_budget_splits(p)


def test_budget_splits_extra_category_rejected(tmp_path: Path) -> None:
    """Verify unknown extra budget category raises DatasetValidationError."""
    bad_splits = {
        "_note": "Extra category",
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
                    "fireworks": 10,  # extra
                }
            }
        },
    }
    p = tmp_path / "extra_cat.json"
    p.write_text(json.dumps(bad_splits), encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_budget_splits(p)


def test_budget_splits_not_summing_to_100_rejected(tmp_path: Path) -> None:
    """Verify allocations totaling != 100% raise DatasetValidationError."""
    bad_splits = {
        "_note": "Bad total",
        "splits": {
            "wedding": {
                "metro": {
                    "venue": 20,
                    "catering": 20,
                    "decor": 10,
                    "photo_video": 10,
                    "attire_beauty": 10,
                    "entertainment": 10,
                    "logistics": 10,
                    "buffer": 5,  # total = 95%
                }
            }
        },
    }
    p = tmp_path / "bad_sum.json"
    p.write_text(json.dumps(bad_splits), encoding="utf-8")
    with pytest.raises(DatasetValidationError) as exc:
        load_budget_splits(p)
    assert "100.0%" in str(exc.value)


def test_vendor_negative_lead_time_rejected(tmp_path: Path) -> None:
    """Verify negative vendor lead time raises DatasetValidationError."""
    bad_vendors = {
        "vendors": [
            {
                "type": "venue",
                "lead_time_weeks": -4,
                "typical_advance_pct": 30,
                "ask_before_booking": ["Questions?"],
            }
        ]
    }
    p = tmp_path / "bad_vendors.json"
    p.write_text(json.dumps(bad_vendors), encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_vendor_checklists(p)


def test_vendor_advance_pct_out_of_bounds_rejected(tmp_path: Path) -> None:
    """Verify advance pct > 100 raises DatasetValidationError."""
    bad_vendors = {
        "vendors": [
            {
                "type": "venue",
                "lead_time_weeks": 4,
                "typical_advance_pct": 120,
                "ask_before_booking": ["Questions?"],
            }
        ]
    }
    p = tmp_path / "bad_advance.json"
    p.write_text(json.dumps(bad_vendors), encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_vendor_checklists(p)


def test_vendor_empty_questions_rejected(tmp_path: Path) -> None:
    """Verify empty ask_before_booking list raises DatasetValidationError."""
    bad_vendors = {
        "vendors": [
            {
                "type": "venue",
                "lead_time_weeks": 4,
                "typical_advance_pct": 30,
                "ask_before_booking": [],
            }
        ]
    }
    p = tmp_path / "empty_questions.json"
    p.write_text(json.dumps(bad_vendors), encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_vendor_checklists(p)


def test_vendor_duplicate_type_rejected(tmp_path: Path) -> None:
    """Verify case-insensitive duplicate vendor types raise DatasetValidationError."""
    dup_vendors = {
        "vendors": [
            {
                "type": "Caterer",
                "lead_time_weeks": 8,
                "typical_advance_pct": 25,
                "ask_before_booking": ["Menu?"],
            },
            {
                "type": "caterer",  # duplicate case-insensitively
                "lead_time_weeks": 12,
                "typical_advance_pct": 30,
                "ask_before_booking": ["Backup staff?"],
            },
        ]
    }
    p = tmp_path / "dup_vendors.json"
    p.write_text(json.dumps(dup_vendors), encoding="utf-8")
    with pytest.raises(DatasetValidationError) as exc:
        load_vendor_checklists(p)
    assert "duplicate vendor type" in str(exc.value).lower()


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
    assert summary.crisis_scenarios.loaded is True
    assert summary.budget_splits.loaded is True
    assert summary.vendor_checklists.loaded is True
