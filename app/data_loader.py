"""Safe data loading and strict validation for PlanProof AI datasets."""

import csv
import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.schemas import (
    BudgetSplitCategories,
    BudgetSplitsDataset,
    BudgetSummary,
    CrisisScenario,
    CrisisSummary,
    DataStatusResponse,
    SeverityRange,
    VendorChecklistsDataset,
    VendorSummary,
)

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
    """Verify that a path exists, is a regular file, and is not 0 bytes."""
    if not path.exists() or not path.is_file():
        raise DatasetNotFoundError(f"Dataset file not found: {path.name}")
    if path.stat().st_size == 0:
        raise DatasetEmptyError(f"Dataset file is empty: {path.name}")


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
                raise DatasetEmptyError(f"No header found in CSV: {path.name}")

            missing = [c for c in REQUIRED_CRISIS_COLUMNS if c not in reader.fieldnames]
            if missing:
                raise DatasetMalformedError(
                    f"CSV missing required columns: {missing} in {path.name}"
                )

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
        raise DatasetMalformedError(f"Malformed CSV content in {path.name}: {err}") from err

    if not scenarios:
        raise DatasetEmptyError(f"CSV contains 0 scenario records: {path.name}")

    logger.info("Loaded and validated %d crisis scenarios from %s", len(scenarios), path.name)
    return scenarios


def load_budget_splits(file_path: Path | str) -> BudgetSplitsDataset:
    """Load and validate budget category percentage allocations from JSON."""
    path = Path(file_path)
    _check_file_exists_and_non_empty(path)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise DatasetMalformedError(f"Invalid JSON in {path.name}: {err}") from err

    try:
        dataset = BudgetSplitsDataset.model_validate(data)
    except (ValidationError, ValueError) as err:
        raise DatasetValidationError(
            f"Budget splits validation failed in {path.name}: {err}"
        ) from err

    return dataset


def load_vendor_checklists(file_path: Path | str) -> VendorChecklistsDataset:
    """Load and validate vendor checklists from JSON."""
    path = Path(file_path)
    _check_file_exists_and_non_empty(path)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise DatasetMalformedError(f"Invalid JSON in {path.name}: {err}") from err

    try:
        dataset = VendorChecklistsDataset.model_validate(data)
    except (ValidationError, ValueError) as err:
        raise DatasetValidationError(
            f"Vendor checklists validation failed in {path.name}: {err}"
        ) from err

    return dataset


class DatasetRepository:
    """In-memory repository holding preloaded, validated application datasets."""

    def __init__(self) -> None:
        self.scenarios: list[CrisisScenario] = []
        self.budget_splits: BudgetSplitsDataset | None = None
        self.vendor_checklists: VendorChecklistsDataset | None = None
        self.load_error: str | None = None

    @property
    def is_loaded(self) -> bool:
        """Return True if crisis dataset was successfully loaded without error."""
        return len(self.scenarios) > 0 and self.load_error is None

    def load_all(
        self,
        crisis_path: Path | str,
        budget_path: Path | str,
        vendor_path: Path | str,
    ) -> None:
        """Load and strictly validate all application datasets."""
        self.load_error = None
        try:
            self.scenarios = load_crisis_scenarios(crisis_path)
            self.budget_splits = load_budget_splits(budget_path)
            self.vendor_checklists = load_vendor_checklists(vendor_path)
        except DataLoaderError as err:
            self.load_error = str(err)
            logger.error("Dataset loading failed: %s", err)

    def get_status_summary(self) -> DataStatusResponse:
        """Produce safe metadata summary for API status endpoint."""
        severities = [s.severity for s in self.scenarios] if self.scenarios else [0]
        sev_min, sev_max = (min(severities), max(severities)) if self.scenarios else (0, 0)

        crisis_sum = CrisisSummary(
            loaded=len(self.scenarios) > 0,
            row_count=len(self.scenarios),
            available_crisis_types=sorted({s.crisis_type for s in self.scenarios}),
            available_event_types=sorted({s.event_type.value for s in self.scenarios}),
            available_city_tiers=sorted({s.city_tier.value for s in self.scenarios}),
            severity_range=SeverityRange(min=sev_min, max=sev_max),
        )

        b_types = [e.value for e in self.budget_splits.splits] if self.budget_splits else []
        b_tiers = (
            [t.value for t in next(iter(self.budget_splits.splits.values()))]
            if self.budget_splits and self.budget_splits.splits
            else []
        )
        b_cats = list(BudgetSplitCategories.model_fields.keys()) if self.budget_splits else []
        budget_sum = BudgetSummary(
            loaded=self.budget_splits is not None,
            event_types=b_types,
            city_tiers=b_tiers,
            categories=b_cats,
        )

        v_vendors = self.vendor_checklists.vendors if self.vendor_checklists else []
        vendor_sum = VendorSummary(
            loaded=self.vendor_checklists is not None,
            vendor_count=len(v_vendors),
            vendor_types=[v.type for v in v_vendors],
        )

        return DataStatusResponse(
            status="healthy" if self.is_loaded else ("error" if self.load_error else "degraded"),
            dataset_loaded=self.is_loaded,
            crisis_scenarios=crisis_sum,
            budget_splits=budget_sum,
            vendor_checklists=vendor_sum,
            row_count=crisis_sum.row_count,
            available_crisis_types=crisis_sum.available_crisis_types,
            available_event_types=crisis_sum.available_event_types,
            available_city_tiers=crisis_sum.available_city_tiers,
            severity_range=crisis_sum.severity_range,
            budget_splits_loaded=budget_sum.loaded,
            vendor_checklists_loaded=vendor_sum.loaded,
        )
