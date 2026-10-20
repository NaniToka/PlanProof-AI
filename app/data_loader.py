"""Safe data loading and validation for PlanProof AI datasets."""

import csv
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas import CrisisScenario, DataStatusResponse, SeverityRange

logger = logging.getLogger(__name__)

REQUIRED_CRISIS_COLUMNS = (
    "id",
    "event_type",
    "city_tier",
    "guest_count",
    "phase",
    "crisis_type",
    "severity",
    "description",
    "recommended_fix",
    "cost_impact_pct_of_budget",
    "message_target",
    "synthetic",
)

EXPECTED_BUDGET_CATEGORIES = {
    "venue",
    "catering",
    "decor",
    "photo_video",
    "attire_beauty",
    "entertainment",
    "logistics",
    "buffer",
}


class DataLoaderError(Exception):
    """Base exception for all data loading errors."""


class DatasetNotFoundError(DataLoaderError):
    """Raised when a requested dataset file does not exist."""


class DatasetEmptyError(DataLoaderError):
    """Raised when a dataset file is empty or contains no records."""


class DatasetMalformedError(DataLoaderError):
    """Raised when dataset structure, header, or syntax is invalid."""


class DatasetValidationError(DataLoaderError):
    """Raised when data values fail schema validation."""


def _check_file_exists_and_non_empty(path: Path) -> None:
    """Verify that a path exists, is a file, and is not empty."""
    if not path.exists() or not path.is_file():
        raise DatasetNotFoundError(f"Dataset file not found: {path}")
    if path.stat().st_size == 0:
        raise DatasetEmptyError(f"Dataset file is empty: {path}")


def load_crisis_scenarios(file_path: Path | str) -> list[CrisisScenario]:
    """Load and validate crisis scenarios CSV safely.

    Raises:
        DatasetNotFoundError: If file does not exist.
        DatasetEmptyError: If file is empty or has only a header.
        DatasetMalformedError: If columns are missing or CSV syntax is invalid.
        DatasetValidationError: If any row fails value validation.
    """
    path = Path(file_path)
    _check_file_exists_and_non_empty(path)

    scenarios: list[CrisisScenario] = []
    try:
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise DatasetEmptyError(f"No header found in CSV: {path}")

            missing = [c for c in REQUIRED_CRISIS_COLUMNS if c not in reader.fieldnames]
            if missing:
                raise DatasetMalformedError(f"CSV missing required columns: {missing} in {path}")

            for line_no, row in enumerate(reader, start=2):
                if not any(row.values()):
                    continue  # skip trailing blank lines
                try:
                    scenarios.append(CrisisScenario.model_validate(row))
                except (ValidationError, ValueError) as err:
                    raise DatasetValidationError(
                        f"Validation error at line {line_no} in {path.name}: {err}"
                    ) from err
    except (csv.Error, UnicodeDecodeError) as err:
        raise DatasetMalformedError(f"Malformed CSV content in {path}: {err}") from err

    if not scenarios:
        raise DatasetEmptyError(f"CSV contains 0 scenario records: {path}")

    logger.info("Loaded %d crisis scenarios from %s", len(scenarios), path.name)
    return scenarios


def load_budget_splits(file_path: Path | str) -> dict[str, Any]:
    """Load and validate budget category percentage allocations from JSON."""
    path = Path(file_path)
    _check_file_exists_and_non_empty(path)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise DatasetMalformedError(f"Invalid JSON in {path}: {err}") from err

    splits = data.get("splits")
    if not isinstance(splits, dict) or not splits:
        raise DatasetMalformedError(f"Missing 'splits' mapping in {path}")

    for event_type, tiers in splits.items():
        if not isinstance(tiers, dict):
            raise DatasetMalformedError(f"Invalid tier dict for event '{event_type}'")
        for tier_name, categories in tiers.items():
            if not isinstance(categories, dict):
                raise DatasetMalformedError(f"Invalid category split in {event_type}.{tier_name}")
            cats = set(categories.keys())
            if cats != EXPECTED_BUDGET_CATEGORIES:
                raise DatasetValidationError(
                    f"Unexpected categories for {event_type}.{tier_name}: {cats}"
                )
            total = sum(categories.values())
            if total != 100:
                msg = f"Budget split is {total}% (must be 100%) in {event_type}.{tier_name}"
                raise DatasetValidationError(msg)

    return data


def load_vendor_checklists(file_path: Path | str) -> dict[str, Any]:
    """Load and validate vendor checklists from JSON."""
    path = Path(file_path)
    _check_file_exists_and_non_empty(path)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise DatasetMalformedError(f"Invalid JSON in {path}: {err}") from err

    vendors = data.get("vendors")
    if not isinstance(vendors, list) or not vendors:
        raise DatasetMalformedError(f"Missing or empty 'vendors' list in {path}")

    required_fields = {"type", "lead_time_weeks", "typical_advance_pct", "ask_before_booking"}
    for idx, vendor in enumerate(vendors):
        if not isinstance(vendor, dict) or not required_fields.issubset(vendor.keys()):
            raise DatasetValidationError(f"Vendor record at index {idx} missing required fields")

    return data


class DatasetRepository:
    """In-memory repository holding preloaded, validated application datasets."""

    def __init__(self) -> None:
        self.scenarios: list[CrisisScenario] = []
        self.budget_splits: dict[str, Any] = {}
        self.vendor_checklists: dict[str, Any] = {}
        self.load_error: str | None = None

    @property
    def is_loaded(self) -> bool:
        """Return True if crisis dataset was successfully loaded."""
        return len(self.scenarios) > 0 and self.load_error is None

    def load_all(
        self,
        crisis_path: Path | str,
        budget_path: Path | str,
        vendor_path: Path | str,
    ) -> None:
        """Load and validate all application datasets, recording errors safely."""
        self.load_error = None
        try:
            self.scenarios = load_crisis_scenarios(crisis_path)
            self.budget_splits = load_budget_splits(budget_path)
            self.vendor_checklists = load_vendor_checklists(vendor_path)
        except DataLoaderError as err:
            self.load_error = str(err)
            logger.error("Dataset loading failed: %s", err)

    def get_status_summary(self) -> DataStatusResponse:
        """Produce safe metadata summary without exposing full dataset."""
        if not self.is_loaded:
            return DataStatusResponse(
                status="error" if self.load_error else "degraded",
                dataset_loaded=False,
                row_count=0,
                available_crisis_types=[],
                available_event_types=[],
                available_city_tiers=[],
                severity_range=SeverityRange(min=0, max=0),
                budget_splits_loaded=bool(self.budget_splits),
                vendor_checklists_loaded=bool(self.vendor_checklists),
            )

        severities = [s.severity for s in self.scenarios]
        return DataStatusResponse(
            status="healthy",
            dataset_loaded=True,
            row_count=len(self.scenarios),
            available_crisis_types=sorted({s.crisis_type for s in self.scenarios}),
            available_event_types=sorted({s.event_type for s in self.scenarios}),
            available_city_tiers=sorted({s.city_tier for s in self.scenarios}),
            severity_range=SeverityRange(min=min(severities), max=max(severities)),
            budget_splits_loaded=bool(self.budget_splits),
            vendor_checklists_loaded=bool(self.vendor_checklists),
        )
