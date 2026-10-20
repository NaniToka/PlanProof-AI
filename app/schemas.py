"""Pydantic schemas and models for PlanProof AI datasets and API endpoints."""

import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventType(StrEnum):
    """Supported event categories."""

    WEDDING = "wedding"
    BIRTHDAY = "birthday"
    COMMUNITY_EVENT = "community_event"


class CityTier(StrEnum):
    """Indian city tiers for logistics and pricing scale."""

    METRO = "metro"
    TIER2 = "tier2"
    TIER3 = "tier3"


class EventPhase(StrEnum):
    """Event lifecycle phases."""

    PLANNING = "planning"
    DAY_BEFORE = "day_before"
    EVENT_DAY = "event_day"


class MessageTarget(StrEnum):
    """Target audience for crisis recovery communications."""

    VENDOR = "vendor"
    GUESTS = "guests"
    FAMILY = "family"


class CrisisScenario(BaseModel):
    """Schema representing a single crisis recovery scenario record."""

    id: str = Field(..., description="Unique scenario identifier (e.g. CR0000001)")
    event_type: EventType = Field(..., description="Event type category")
    city_tier: CityTier = Field(..., description="City tier category")
    guest_count: int = Field(..., description="Total guest count (positive integer, 1 to 2000)")
    phase: EventPhase = Field(..., description="Event lifecycle phase")
    crisis_type: str = Field(..., description="Standardized category of the crisis")
    severity: int = Field(..., description="Severity level from 1 (minor) to 3 (critical)")
    description: str = Field(..., description="Description of the crisis scenario")
    recommended_fix: str = Field(..., description="Actionable immediate recovery step")
    cost_impact_pct_of_budget: float = Field(
        ..., description="Estimated percentage cost impact on total budget (finite float)"
    )
    message_target: MessageTarget = Field(..., description="Target audience for messaging")
    synthetic: bool = Field(True, description="Flag indicating synthetic assumption")

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Validate non-empty scenario identifier."""
        if not value or not value.strip():
            raise ValueError("Scenario ID cannot be empty")
        return value.strip()

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: int) -> int:
        """Validate that severity is an integer between 1 and 3."""
        if value not in (1, 2, 3):
            raise ValueError(f"Severity must be 1, 2, or 3, got: {value}")
        return value

    @field_validator("guest_count")
    @classmethod
    def validate_guest_count(cls, value: int) -> int:
        """Validate that guest count is within supported positive range (1 to 2,000)."""
        if value < 1 or value > 2000:
            raise ValueError(f"Guest count must be between 1 and 2,000, got: {value}")
        return value

    @field_validator("description", "recommended_fix", "crisis_type")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        """Validate that text fields are not blank."""
        if not value or not value.strip():
            raise ValueError("Field cannot be empty or blank")
        return value.strip()

    @field_validator("cost_impact_pct_of_budget")
    @classmethod
    def validate_cost_impact(cls, value: float) -> float:
        """Validate that cost impact is a finite numeric float."""
        if not math.isfinite(value):
            raise ValueError(f"Cost impact must be a finite number, got: {value}")
        return value

    @model_validator(mode="after")
    def validate_cost_impact_sign(self) -> "CrisisScenario":
        """Ensure negative cost impacts only apply to savings crises (e.g. guest dropout)."""
        if self.cost_impact_pct_of_budget < 0.0 and self.crisis_type != "guest_dropout":
            msg = (
                f"Negative cost impact ({self.cost_impact_pct_of_budget}%) is only permitted "
                f"for headcount savings crises ('guest_dropout'), not '{self.crisis_type}'"
            )
            raise ValueError(msg)
        return self


class BudgetSplitCategories(BaseModel):
    """Percentage allocations across the 8 standard event budget categories."""

    venue: float = Field(..., ge=0.0, le=100.0)
    catering: float = Field(..., ge=0.0, le=100.0)
    decor: float = Field(..., ge=0.0, le=100.0)
    photo_video: float = Field(..., ge=0.0, le=100.0)
    attire_beauty: float = Field(..., ge=0.0, le=100.0)
    entertainment: float = Field(..., ge=0.0, le=100.0)
    logistics: float = Field(..., ge=0.0, le=100.0)
    buffer: float = Field(..., ge=0.0, le=100.0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_sum_to_100(self) -> "BudgetSplitCategories":
        """Verify that category percentages sum to exactly 100% within 0.01% tolerance."""
        total = (
            self.venue
            + self.catering
            + self.decor
            + self.photo_video
            + self.attire_beauty
            + self.entertainment
            + self.logistics
            + self.buffer
        )
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Budget allocations must sum to 100.0%, got: {total:.2f}%")
        return self


class BudgetSplitsDataset(BaseModel):
    """Container for budget allocations covering all event types and city tiers."""

    note: str = Field(alias="_note", default="Synthetic assumptions, percent of total budget")
    splits: dict[EventType, dict[CityTier, BudgetSplitCategories]] = Field(
        ..., description="Allocations by event type and city tier"
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_all_combinations(self) -> "BudgetSplitsDataset":
        """Verify that all 3 event types and all 3 city tiers are present."""
        for event in EventType:
            if event not in self.splits:
                raise ValueError(f"Budget splits missing event type: '{event.value}'")
            for tier in CityTier:
                if tier not in self.splits[event]:
                    raise ValueError(
                        f"Budget splits for '{event.value}' missing city tier: '{tier.value}'"
                    )
        return self


class VendorChecklist(BaseModel):
    """Schema for a vendor checklist and booking timeline entry."""

    type: str = Field(..., min_length=1, description="Vendor category identifier")
    lead_time_weeks: int = Field(..., ge=0, description="Recommended booking lead time in weeks")
    typical_advance_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Typical advance booking deposit percentage"
    )
    ask_before_booking: list[str] = Field(
        ..., min_length=1, description="Key qualification questions before booking"
    )

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("typical_advance_pct")
    @classmethod
    def validate_advance_finite(cls, value: float) -> float:
        """Validate advance percentage is finite."""
        if not math.isfinite(value):
            raise ValueError(f"Advance percentage must be finite, got: {value}")
        return value

    @field_validator("ask_before_booking")
    @classmethod
    def validate_questions(cls, questions: list[str]) -> list[str]:
        """Ensure all questions are non-empty strings."""
        if not questions:
            raise ValueError("Questions list cannot be empty")
        for q in questions:
            if not q or not q.strip():
                raise ValueError("Question strings cannot be empty or blank")
        return [q.strip() for q in questions]


class VendorChecklistsDataset(BaseModel):
    """Container for vendor booking checklists and timeline guidelines."""

    note: str = Field(
        alias="_note", default="Lead times and advance percent are synthetic assumptions"
    )
    vendors: list[VendorChecklist] = Field(..., min_length=1)

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_unique_types(self) -> "VendorChecklistsDataset":
        """Ensure vendor types are unique case-insensitively."""
        seen: set[str] = set()
        for vendor in self.vendors:
            v_key = vendor.type.lower()
            if v_key in seen:
                raise ValueError(f"Duplicate vendor type detected: '{vendor.type}'")
            seen.add(v_key)
        return self


class HealthResponse(BaseModel):
    """Response schema for application health check."""

    status: str = Field("ok", description="Application status")
    app: str = Field("PlanProof AI", description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Operating environment")


class SeverityRange(BaseModel):
    """Schema representing minimum and maximum severity observed."""

    min: int = Field(..., description="Minimum severity")
    max: int = Field(..., description="Maximum severity")


class CrisisSummary(BaseModel):
    """Metadata summary of loaded crisis scenarios."""

    loaded: bool = Field(..., description="Whether crisis dataset loaded")
    row_count: int = Field(..., description="Total crisis scenarios loaded")
    available_crisis_types: list[str] = Field(default_factory=list)
    available_event_types: list[str] = Field(default_factory=list)
    available_city_tiers: list[str] = Field(default_factory=list)
    severity_range: SeverityRange = Field(...)


class BudgetSummary(BaseModel):
    """Metadata summary of loaded budget splits."""

    loaded: bool = Field(..., description="Whether budget allocations loaded")
    event_types: list[str] = Field(default_factory=list)
    city_tiers: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)


class VendorSummary(BaseModel):
    """Metadata summary of loaded vendor checklists."""

    loaded: bool = Field(..., description="Whether vendor checklists loaded")
    vendor_count: int = Field(..., description="Total vendor types cataloged")
    vendor_types: list[str] = Field(default_factory=list)


class DataStatusResponse(BaseModel):
    """Safe status metadata for all application datasets without exposing raw data."""

    status: str = Field(..., description="Data repository status: healthy, degraded, error")
    dataset_loaded: bool = Field(..., description="Overall dataset health status")

    # Detailed dataset summaries
    crisis_scenarios: CrisisSummary = Field(...)
    budget_splits: BudgetSummary = Field(...)
    vendor_checklists: VendorSummary = Field(...)

    # Top-level backward compatibility fields
    row_count: int = Field(..., description="Crisis scenario count")
    available_crisis_types: list[str] = Field(default_factory=list)
    available_event_types: list[str] = Field(default_factory=list)
    available_city_tiers: list[str] = Field(default_factory=list)
    severity_range: SeverityRange = Field(...)
    budget_splits_loaded: bool = Field(...)
    vendor_checklists_loaded: bool = Field(...)
