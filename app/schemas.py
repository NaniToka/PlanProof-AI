"""Pydantic schemas and data contracts for PlanProof AI.

Defines:
- Core domain enums (EventType, CityTier, EventPhase, MessageTarget, LanguageCode, BookingStatus)
- Dataset validation models (CrisisScenario, BudgetSplitsDataset, VendorChecklistsDataset)
- Event planning input request model (EventPlanRequest)
- Event planning output models (Budget, Timeline, Vendors, Ideas, Risks, Family Council, Crisis)
- Standard error and status envelope models
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ==============================================================================
# 1. Domain Enums
# ==============================================================================


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


class LanguageCode(StrEnum):
    """Supported regional languages for communications and planning."""

    EN = "en"
    HI = "hi"
    TE = "te"


class BookingStatus(StrEnum):
    """Status of vendor bookings across planning milestones."""

    PENDING = "pending"
    CONTACTED = "contacted"
    SHORTLISTED = "shortlisted"
    BOOKED = "booked"
    NOT_NEEDED = "not_needed"


class MilestoneCategory(StrEnum):
    """Controlled functional category for timeline milestones."""

    VENUE = "venue"
    CATERING = "catering"
    DECOR = "decor"
    INVITATIONS = "invitations"
    LOGISTICS = "logistics"
    FINAL_CHECKS = "final_checks"


class MilestonePriority(StrEnum):
    """Task urgency level."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MilestoneStatus(StrEnum):
    """Milestone execution status."""

    PENDING = "pending"
    COMPLETED = "completed"


class VendorChecklistCategory(StrEnum):
    """Functional categories for event vendor coordination tasks."""

    VENUE_PERMISSIONS = "venue_permissions"
    CATERING_REFRESHMENTS = "catering_refreshments"
    DECORATION_SETUP = "decoration_setup"
    PHOTOGRAPHY_VIDEOGRAPHY = "photography_videography"
    ATTIRE_BEAUTY = "attire_beauty"
    ENTERTAINMENT_EQUIPMENT = "entertainment_equipment"
    TRANSPORT_LOGISTICS = "transport_logistics"
    INVITATIONS_COORDINATION = "invitations_coordination"
    CLEANUP_POST_EVENT = "cleanup_post_event"


class VendorChecklistStatus(StrEnum):
    """Progress status of a vendor checklist task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class VendorBookingStatus(StrEnum):
    """User-recorded booking progression for a vendor category."""

    NOT_STARTED = "not_started"
    RESEARCHING = "researching"
    CONTACTED = "contacted"
    BOOKED = "booked"
    CANCELLED = "cancelled"


class VendorChecklistPriority(StrEnum):
    """Priority level for vendor checklist tasks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IdeaCategory(StrEnum):
    """Category classification for event creative ideas and recommendations."""

    THEME_ATMOSPHERE = "theme_atmosphere"
    DECORATION = "decoration"
    FOOD_REFRESHMENTS = "food_refreshments"
    GUEST_ENGAGEMENT = "guest_engagement"
    ENTERTAINMENT = "entertainment"
    INVITATIONS_COMMUNICATION = "invitations_communication"
    ACCESSIBILITY_INCLUSIVITY = "accessibility_inclusivity"
    SUSTAINABLE_PLANNING = "sustainable_planning"


class EstimatedCostLevel(StrEnum):
    """Relative qualitative cost scale for recommendation ideas."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class BudgetFit(StrEnum):
    """How well an idea aligns with the event's total and category budget."""

    FITS = "fits"
    POSSIBLE_WITH_ADJUSTMENTS = "possible_with_adjustments"
    UNKNOWN = "unknown"


class IdeaSource(StrEnum):
    """Provenance of the recommendation: deterministic rules, demo fixtures, or Gemini AI."""

    RULES = "rules"
    DEMO = "demo"
    GEMINI = "gemini"


class RiskLikelihood(StrEnum):
    """Estimated likelihood level for an event pre-mortem risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class RiskImpact(StrEnum):
    """Potential operational or financial severity of an event risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(StrEnum):
    """Classification of event operational failure modes."""

    BUDGET_OVERRUN = "budget_overrun"
    TIMELINE_DELAY = "timeline_delay"
    VENDOR_COORDINATION = "vendor_coordination"
    GUEST_CATERING = "guest_catering"
    WEATHER_EXPOSURE = "weather_exposure"
    TRANSPORT_LOGISTICS = "transport_logistics"
    SAFETY_ACCESSIBILITY = "safety_accessibility"
    PERMISSIONS_COMPLIANCE = "permissions_compliance"
    SUPPLIER_DISRUPTION = "supplier_disruption"
    COMMUNICATION_GAPS = "communication_gaps"


class RiskSource(StrEnum):
    """Provenance origin of risk identification: rules, demo, or gemini."""

    RULES = "rules"
    DEMO = "demo"
    GEMINI = "gemini"


class RecoveryStatus(StrEnum):
    """Lifecycle status of a crisis recovery record."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class RecoveryActionStatus(StrEnum):
    """Lifecycle status of a tracked recovery action."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"



# ==============================================================================
# 2. Dataset Schemas (Preloaded Data Integrity)
# ==============================================================================


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


# ==============================================================================
# 3. Event Planning Input & Profile Schemas
# ==============================================================================

INDIA_TZ = ZoneInfo("Asia/Kolkata")


def get_current_ist_date() -> date:
    """Return the current calendar date in Indian Standard Time (IST, UTC+05:30)."""
    return datetime.now(INDIA_TZ).date()


def validate_event_date(
    event_date: date | None,
    allow_past: bool = False,
    reference_date: date | None = None,
) -> date | None:
    """Validate that event_date is not in the past unless explicitly allowed.

    Timezone Convention:
        Indian Standard Time (Asia/Kolkata, UTC+05:30). Dates are validated
        against the current calendar date in India unless reference_date is supplied.

    Args:
        event_date: Target date to validate.
        allow_past: If True, allows past dates (e.g. for in-progress / crisis recovery events).
        reference_date: Optional explicit comparison date for independent unit testing.

    Returns:
        The validated date or None.

    Raises:
        ValueError: If event_date is prior to reference_date for an upcoming event.
    """
    if event_date is None:
        return None

    today = reference_date or get_current_ist_date()
    if not allow_past and event_date < today:
        raise ValueError(
            f"event_date '{event_date.isoformat()}' cannot be in the past for an upcoming event. "
            f"Current date is '{today.isoformat()}' (IST)."
        )
    return event_date


def validate_strict_guest_count_value(value: Any) -> int:
    """Reject booleans and decimals for guest count, enforce 1..2000 range."""
    if isinstance(value, bool):
        raise ValueError("guest_count must be an integer, not a boolean")
    if isinstance(value, float):
        raise ValueError("guest_count must be an integer, not a decimal")
    try:
        val_int = int(value)
    except (ValueError, TypeError) as err:
        raise ValueError("guest_count must be a valid integer") from err

    if val_int < 1 or val_int > 2000:
        raise ValueError(f"guest_count must be between 1 and 2,000, got: {val_int}")
    return val_int


def validate_strict_budget_inr_value(value: Any) -> int:
    """Reject booleans and decimals for budget, enforce ₹10,000 to ₹50,000,000."""
    if isinstance(value, bool):
        raise ValueError("total_budget_inr must be an integer, not a boolean")
    if isinstance(value, float):
        raise ValueError("total_budget_inr must be an integer amount in INR, not a decimal")
    try:
        val_int = int(value)
    except (ValueError, TypeError) as err:
        raise ValueError("total_budget_inr must be a valid integer amount in INR") from err

    if val_int < 10000 or val_int > 50000000:
        raise ValueError(
            f"total_budget_inr must be between ₹10,000 and ₹50,000,000, got: ₹{val_int:,}"
        )
    return val_int


class EventPlanRequest(BaseModel):
    """Strict input schema for event planning requests."""

    event_type: EventType = Field(
        ..., description="Event category: wedding, birthday, community_event"
    )
    guest_count: int = Field(..., description="Estimated guest count (strict integer, 1 to 2000)")
    total_budget_inr: int = Field(
        ..., description="Total event budget in INR (strict integer, ₹10,000 to ₹50,000,000)"
    )
    city_tier: CityTier = Field(..., description="Indian city tier: metro, tier2, tier3")
    city: str = Field(
        ..., min_length=1, max_length=100, description="City name (e.g. Hyderabad, Jaipur)"
    )
    theme_notes: str = Field(
        default="", max_length=1000, description="Optional theme, culture, or style notes"
    )
    language: LanguageCode = Field(
        default=LanguageCode.EN, description="Preferred language: en, hi, te"
    )
    event_name: str | None = Field(
        default=None, max_length=150, description="Optional user-provided event title"
    )
    event_date: date | None = Field(
        default=None, description="Optional event scheduled date"
    )
    is_in_progress: bool = Field(
        default=False, description="Whether event is active/in-progress for crisis mode"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("guest_count", mode="before")
    @classmethod
    def validate_strict_guest_count(cls, value: Any) -> int:
        return validate_strict_guest_count_value(value)

    @field_validator("total_budget_inr", mode="before")
    @classmethod
    def validate_strict_budget_inr(cls, value: Any) -> int:
        return validate_strict_budget_inr_value(value)

    @field_validator("city")
    @classmethod
    def validate_city_non_empty(cls, value: str) -> str:
        """Ensure city string is not blank."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("City name cannot be empty or whitespace")
        return stripped

    @field_validator("event_name")
    @classmethod
    def clean_event_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @model_validator(mode="after")
    def validate_event_date_model(self) -> "EventPlanRequest":
        if self.event_date is not None:
            validate_event_date(self.event_date, allow_past=self.is_in_progress)
        return self


class EventCreateRequest(BaseModel):
    """Schema for creating a new event profile."""

    event_type: EventType = Field(
        ..., description="Event category: wedding, birthday, community_event"
    )
    guest_count: int = Field(
        ..., description="Estimated guest count (strict integer, 1 to 2000)"
    )
    total_budget_inr: int = Field(
        ..., description="Total event budget in INR (strict integer, ₹10,000 to ₹50,000,000)"
    )
    city_tier: CityTier = Field(
        default=CityTier.METRO, description="Indian city tier: metro, tier2, tier3"
    )
    city: str | None = Field(
        default=None, max_length=100, description="Optional city name (e.g. Hyderabad, Jaipur)"
    )
    event_name: str | None = Field(
        default=None, max_length=150, description="Optional user-provided event title"
    )
    event_date: date | None = Field(
        default=None, description="Optional event scheduled date"
    )
    language: LanguageCode = Field(
        default=LanguageCode.EN, description="Preferred language: en, hi, te"
    )
    theme_notes: str = Field(
        default="", max_length=1000, description="Optional theme, culture, or style notes"
    )
    is_in_progress: bool = Field(
        default=False, description="Flag indicating event is currently active/ongoing"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("guest_count", mode="before")
    @classmethod
    def validate_guest_count(cls, value: Any) -> int:
        return validate_strict_guest_count_value(value)

    @field_validator("total_budget_inr", mode="before")
    @classmethod
    def validate_budget(cls, value: Any) -> int:
        return validate_strict_budget_inr_value(value)

    @field_validator("city", "event_name")
    @classmethod
    def clean_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @model_validator(mode="after")
    def validate_event_date_field(self) -> "EventCreateRequest":
        if self.event_date is not None:
            validate_event_date(self.event_date, allow_past=self.is_in_progress)
        return self


class EventUpdateRequest(BaseModel):
    """Schema for updating an existing event profile (PATCH)."""

    event_type: EventType | None = Field(default=None, description="Event category")
    guest_count: int | None = Field(
        default=None, description="Estimated guest count (strict integer, 1 to 2000)"
    )
    total_budget_inr: int | None = Field(
        default=None, description="Total event budget in INR (strict integer, ₹10,000 to ₹50,000,000)"
    )
    city_tier: CityTier | None = Field(default=None, description="Indian city tier")
    city: str | None = Field(default=None, max_length=100, description="City location")
    event_name: str | None = Field(default=None, max_length=150, description="Event title")
    event_date: date | None = Field(default=None, description="Event date")
    language: LanguageCode | None = Field(default=None, description="Preferred language")
    theme_notes: str | None = Field(default=None, max_length=1000, description="Theme notes")
    is_in_progress: bool | None = Field(default=None, description="In-progress flag")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("guest_count", mode="before")
    @classmethod
    def validate_guest_count(cls, value: Any) -> int | None:
        if value is None:
            return None
        return validate_strict_guest_count_value(value)

    @field_validator("total_budget_inr", mode="before")
    @classmethod
    def validate_budget(cls, value: Any) -> int | None:
        if value is None:
            return None
        return validate_strict_budget_inr_value(value)

    @field_validator("city", "event_name")
    @classmethod
    def clean_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @model_validator(mode="after")
    def validate_event_date_field(self) -> "EventUpdateRequest":
        if self.event_date is not None and self.is_in_progress is not None:
            validate_event_date(self.event_date, allow_past=self.is_in_progress)
        return self



class EventValidationResponse(BaseModel):
    """Confirmation response for validated event inputs without generating full plan."""

    valid: bool = Field(default=True, description="Input validation confirmation flag")
    message: str = Field(
        default="Event plan request validated successfully.",
        description="Validation outcome message",
    )
    validated_request: EventPlanRequest = Field(..., description="Normalized request payload")


# ==============================================================================
# 4. Response Schemas for Future Features (Data Contracts)
# ==============================================================================


# Canonical 8 budget categories in order
CANONICAL_BUDGET_CATEGORIES: tuple[str, ...] = (
    "venue",
    "catering",
    "decor",
    "photo_video",
    "attire_beauty",
    "entertainment",
    "logistics",
    "buffer",
)


class EventBudgetBreakdown(BaseModel):
    """Category budget allocations in integer INR amounts summing exactly to total."""

    venue: int = Field(..., ge=0, description="Venue rental & space costs in INR")
    catering: int = Field(..., ge=0, description="Food & beverage costs in INR")
    decor: int = Field(..., ge=0, description="Decoration, floral & staging in INR")
    photo_video: int = Field(..., ge=0, description="Photography & videography in INR")
    attire_beauty: int = Field(..., ge=0, description="Attire, styling & makeup in INR")
    entertainment: int = Field(..., ge=0, description="DJ, music, MC & sound in INR")
    logistics: int = Field(..., ge=0, description="Transport, accommodation & licenses in INR")
    buffer: int = Field(..., ge=0, description="Emergency buffer reserve in INR")
    total_budget_inr: int = Field(..., ge=0, description="Stated total event budget in INR")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_sum_equals_total(self) -> "EventBudgetBreakdown":
        """Verify that category allocations sum exactly to the stated total budget."""
        category_sum = (
            self.venue
            + self.catering
            + self.decor
            + self.photo_video
            + self.attire_beauty
            + self.entertainment
            + self.logistics
            + self.buffer
        )
        if category_sum != self.total_budget_inr:
            raise ValueError(
                f"Budget category allocations sum to ₹{category_sum:,}, which does not match "
                f"the stated total budget of ₹{self.total_budget_inr:,}"
            )
        return self

    def __getitem__(self, item: str) -> int:
        """Allow dict-like key access to budget category amounts."""
        if hasattr(self, item):
            val = getattr(self, item)
            if isinstance(val, int):
                return val
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        """Allow dict-like get method for budget categories."""
        if hasattr(self, item):
            return getattr(self, item)
        return default


class EventVendorChecklistItem(BaseModel):
    """Event-specific vendor checklist item tracking tasks, deadlines, and coordination."""

    id: str = Field(..., min_length=1, max_length=50, description="Stable unique item identifier")
    category: VendorChecklistCategory = Field(..., description="Vendor coordination category")
    title: str = Field(..., min_length=1, max_length=150, description="Short task name")
    description: str = Field(..., min_length=1, max_length=500, description="Concise task description")
    status: VendorChecklistStatus = Field(
        default=VendorChecklistStatus.PENDING,
        description="Task progress status (pending, in_progress, completed, skipped)",
    )
    due_date: date | None = Field(
        default=None, description="Target calendar deadline derived from event date"
    )
    days_before_event: int | None = Field(
        default=None, ge=0, description="Lead time in days before event date"
    )
    priority: VendorChecklistPriority = Field(
        default=VendorChecklistPriority.MEDIUM, description="Task urgency level"
    )
    notes: str | None = Field(
        default=None, max_length=500, description="Optional user-entered coordination notes"
    )
    vendor_name: str | None = Field(
        default=None, max_length=100, description="Optional user-entered vendor business or contact name"
    )
    booking_status: VendorBookingStatus = Field(
        default=VendorBookingStatus.NOT_STARTED,
        description="User-recorded booking progression (never auto-set to booked)",
    )
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last update timestamp in UTC")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("notes", "vendor_name", mode="before")
    @classmethod
    def strip_and_empty_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value


class EventProfile(BaseModel):
    """Complete domain model representing an event profile."""

    event_id: str = Field(..., description="Server-generated unique identifier (e.g. EV-...)")
    event_type: EventType = Field(
        ..., description="Event category: wedding, birthday, community_event"
    )
    event_name: str | None = Field(default=None, description="Optional user-provided event title")
    city: str | None = Field(default=None, description="City location")
    city_tier: CityTier = Field(default=CityTier.METRO, description="City logistics tier")
    event_date: date | None = Field(default=None, description="Event scheduled date")
    guest_count: int = Field(..., description="Guest headcount within configured limits")
    total_budget_inr: int = Field(..., description="Total budget in INR within configured limits")
    language: LanguageCode = Field(
        default=LanguageCode.EN, description="Preferred communication language"
    )
    theme_notes: str = Field(default="", description="Optional theme or special instructions")
    is_in_progress: bool = Field(
        default=False, description="Whether event is active/in-progress for crisis mode"
    )
    budget: EventBudgetBreakdown | None = Field(
        default=None, description="Deterministic 8-category budget allocation"
    )
    milestone_statuses: dict[str, MilestoneStatus] = Field(
        default_factory=dict, description="Completion status overrides for timeline milestones"
    )
    vendor_checklist: list[EventVendorChecklistItem] = Field(
        default_factory=list, description="Event-specific vendor checklist and coordination items"
    )
    recovery_records: list[CrisisRecoveryRecord] = Field(
        default_factory=list, description="Historical crisis recovery records and action trackers"
    )
    created_at: datetime = Field(..., description="Server creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Server last modification timestamp (UTC)")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    def to_plan_request(self) -> EventPlanRequest:
        """Convert this profile into a validated EventPlanRequest for downstream AI orchestration."""
        return EventPlanRequest(
            event_type=self.event_type,
            guest_count=self.guest_count,
            total_budget_inr=self.total_budget_inr,
            city_tier=self.city_tier,
            city=self.city or "Event Location",
            theme_notes=self.theme_notes,
            language=self.language,
            event_name=self.event_name,
            event_date=self.event_date,
            is_in_progress=self.is_in_progress,
        )


class EventListResponse(BaseModel):
    """Paginated list response of event profiles."""

    total: int = Field(..., ge=0, description="Total count of active event profiles")
    skip: int = Field(default=0, ge=0, description="Pagination offset")
    limit: int = Field(default=50, ge=1, le=100, description="Pagination batch size")
    events: list[EventProfile] = Field(default_factory=list, description="List of event profiles")

    model_config = ConfigDict(extra="forbid")


class EventBudgetPlanResponse(BaseModel):
    """Event-specific budget plan response with deterministic allocations, percentages, and warnings."""

    event_id: str = Field(..., description="Server-generated unique identifier")
    total_budget_inr: int = Field(..., description="Total event budget in INR")
    currency: Literal["INR"] = Field(default="INR", description="Three-letter currency code, fixed to INR")
    allocations: EventBudgetBreakdown = Field(..., description="8-category deterministic rupee allocation")
    allocation_percentages: dict[str, float] = Field(
        ..., description="Exact percentage shares corresponding to category allocations"
    )
    remaining_budget_inr: int = Field(
        default=0, ge=0, description="Remaining unallocated rupee balance (0 when exact)"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Deterministic budget constraints and warnings"
    )
    explanation: str = Field(
        ..., description="Deterministic mathematical explanation of the allocation and buffer policy"
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_plan_balance(self) -> "EventBudgetPlanResponse":
        """Verify that allocations match total_budget_inr and remaining_budget_inr is consistent."""
        if self.allocations.total_budget_inr != self.total_budget_inr:
            raise ValueError(
                f"Allocations total budget ₹{self.allocations.total_budget_inr:,} does not match "
                f"plan total budget ₹{self.total_budget_inr:,}"
            )
        category_sum = (
            self.allocations.venue
            + self.allocations.catering
            + self.allocations.decor
            + self.allocations.photo_video
            + self.allocations.attire_beauty
            + self.allocations.entertainment
            + self.allocations.logistics
            + self.allocations.buffer
        )
        if category_sum + self.remaining_budget_inr != self.total_budget_inr:
            raise ValueError(
                f"Category sum (₹{category_sum:,}) + remaining (₹{self.remaining_budget_inr:,}) "
                f"does not equal total budget (₹{self.total_budget_inr:,})"
            )
        return self


class EventBudgetRebalanceRequest(BaseModel):
    """Input request schema for rebalancing a saved event profile's budget."""

    new_total_budget_inr: int = Field(
        ...,
        description="New total event budget in INR (strict integer, ₹10,000 to ₹50,000,000)",
    )
    strict_protect: bool = Field(
        default=False,
        description="If True, disallow cuts to catering and buffer reserve",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_total_budget_inr", mode="before")
    @classmethod
    def validate_budget(cls, value: Any) -> int:
        return validate_strict_budget_inr_value(value)


class EventMilestone(BaseModel):
    """Individual planning milestone with deadline and status."""

    milestone_id: str = Field(
        ..., min_length=1, max_length=50, description="Stable milestone identifier"
    )
    title: str = Field(
        ..., min_length=1, max_length=150, description="Short task name"
    )
    description: str = Field(
        ..., min_length=1, max_length=500, description="Concise explanation"
    )
    category: MilestoneCategory = Field(
        ..., description="Controlled milestone functional category"
    )
    due_date: date = Field(
        ..., description="Target completion calendar date (ISO 8601)"
    )
    days_before_event: int = Field(
        ..., ge=0, description="Lead time in days before the event date"
    )
    priority: MilestonePriority = Field(
        default=MilestonePriority.MEDIUM, description="Task urgency level"
    )
    status: MilestoneStatus = Field(
        default=MilestoneStatus.PENDING, description="Completion status"
    )
    is_overdue: bool = Field(
        default=False, description="Whether milestone is past due relative to reference date"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class EventTimelineScheduleResponse(BaseModel):
    """Deterministic timeline and milestone schedule for a saved event profile."""

    event_id: str = Field(..., description="Server-generated event identifier")
    event_date: date | None = Field(default=None, description="Event scheduled calendar date")
    generated_at: datetime = Field(..., description="Server generation timestamp in UTC")
    milestones: list[EventMilestone] = Field(
        default_factory=list, description="Chronologically sorted milestone checklist"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Schedule warnings or date alerts"
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_milestones_integrity(self) -> "EventTimelineScheduleResponse":
        # 1. Prevent duplicate milestone IDs
        ids = [m.milestone_id for m in self.milestones]
        if len(ids) != len(set(ids)):
            duplicates = [mid for mid in ids if ids.count(mid) > 1]
            raise ValueError(f"Duplicate milestone identifiers found: {set(duplicates)}")

        # 2. If event_date is present, verify due_date == event_date - timedelta(days=days_before_event)
        if self.event_date:
            for m in self.milestones:
                expected_due = self.event_date - timedelta(days=m.days_before_event)
                if m.due_date != expected_due:
                    raise ValueError(
                        f"Milestone '{m.milestone_id}' due_date {m.due_date} does not match "
                        f"event_date ({self.event_date}) - {m.days_before_event} days ({expected_due})"
                    )

        # 3. Verify chronological sorting (earliest due_date first; ties broken by milestone_id)
        for i in range(len(self.milestones) - 1):
            if (self.milestones[i].due_date, self.milestones[i].milestone_id) > (
                self.milestones[i + 1].due_date,
                self.milestones[i + 1].milestone_id,
            ):
                raise ValueError(
                    f"Milestones are not sorted chronologically: "
                    f"'{self.milestones[i].milestone_id}' ({self.milestones[i].due_date}) comes before "
                    f"'{self.milestones[i + 1].milestone_id}' ({self.milestones[i + 1].due_date})"
                )
        return self


class MilestoneStatusUpdateRequest(BaseModel):
    """Request payload to update milestone completion status."""

    status: MilestoneStatus = Field(
        ..., description="New milestone completion status (pending or completed)"
    )

    model_config = ConfigDict(extra="forbid")


class VendorChecklistSummary(BaseModel):
    """Aggregated status counts for vendor checklist items."""

    total_items: int = Field(..., ge=0, description="Total checklist items")
    pending: int = Field(default=0, ge=0, description="Count of pending tasks")
    in_progress: int = Field(default=0, ge=0, description="Count of in-progress tasks")
    completed: int = Field(default=0, ge=0, description="Count of completed tasks")
    skipped: int = Field(default=0, ge=0, description="Count of skipped tasks")
    booking_statuses: dict[str, int] = Field(
        default_factory=dict, description="Counts of user-recorded booking statuses"
    )

    model_config = ConfigDict(extra="forbid")


class EventVendorChecklistResponse(BaseModel):
    """Response envelope for event vendor checklist and coordination workflow."""

    event_id: str = Field(..., description="Server-generated event identifier")
    event_type: EventType = Field(..., description="Event type category")
    event_date: date | None = Field(default=None, description="Event scheduled date")
    generated_at: datetime = Field(..., description="Timestamp of generation/response in UTC")
    summary: VendorChecklistSummary = Field(..., description="Summary of item and booking statuses")
    items: list[EventVendorChecklistItem] = Field(
        default_factory=list, description="Event-specific vendor coordination items"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Advisory messages"
    )

    model_config = ConfigDict(extra="forbid")


class VendorChecklistItemUpdateRequest(BaseModel):
    """Payload to update an event vendor checklist item."""

    status: VendorChecklistStatus | None = Field(
        default=None, description="New task status (pending, in_progress, completed, skipped)"
    )
    notes: str | None = Field(
        default=None, max_length=500, description="User-entered coordination notes (max 500 characters)"
    )
    priority: VendorChecklistPriority | None = Field(
        default=None, description="New task priority (low, medium, high)"
    )
    vendor_name: str | None = Field(
        default=None, max_length=100, description="User-entered vendor name (max 100 characters)"
    )
    booking_status: VendorBookingStatus | None = Field(
        default=None,
        description="New booking status (not_started, researching, contacted, booked, cancelled)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("notes", "vendor_name", mode="before")
    @classmethod
    def strip_and_empty_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value


class EventRecommendationItem(BaseModel):
    """Curated creative recommendation for an event profile."""

    id: str = Field(..., min_length=1, max_length=50, description="Stable unique recommendation identifier, e.g. IDEA-WED-01")
    category: IdeaCategory = Field(..., description="Recommendation category")
    title: str = Field(..., min_length=1, max_length=200, description="Concept title")
    description: str = Field(..., min_length=1, max_length=1000, description="Detailed concept description")
    reason: str = Field(..., min_length=1, max_length=500, description="Contextual rationale tailored to event type, budget, or theme")
    estimated_cost_level: EstimatedCostLevel = Field(
        default=EstimatedCostLevel.UNKNOWN,
        description="Relative cost tier: low, medium, high, or unknown (not a verified market quote)"
    )
    budget_fit: BudgetFit = Field(
        default=BudgetFit.UNKNOWN,
        description="Budget feasibility assessment: fits, possible_with_adjustments, or unknown"
    )
    implementation_tips: list[str] = Field(
        default_factory=list, description="Actionable execution and practical sourcing steps"
    )
    alternatives: list[str] | None = Field(
        default=None, description="Optional simpler, DIY, or lower-cost alternatives"
    )
    source: IdeaSource = Field(
        default=IdeaSource.RULES, description="Origin source: rules, demo, or gemini"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: Any) -> Any:
        """Allow 'deterministic' to be normalized to 'rules'."""
        if isinstance(value, str):
            val_lower = value.strip().lower()
            if val_lower == "deterministic":
                return IdeaSource.RULES
        return value


class EventIdeasResponse(BaseModel):
    """Personalized event recommendations response payload."""

    event_id: str = Field(..., description="Associated event profile ID")
    event_type: EventType = Field(..., description="Event type category")
    total_ideas: int = Field(..., ge=0, description="Total count of recommendations returned")
    ideas: list[EventRecommendationItem] = Field(
        default_factory=list, description="List of personalized recommendations"
    )
    budget_context_inr: int = Field(..., ge=0, description="Event total budget context in INR")
    disclaimer: str = Field(
        default=(
            "Recommendations and cost levels are qualitative planning guidance for inspiration. "
            "They do not constitute real vendor discovery, verified quotes, or guaranteed prices."
        ),
        description="Advisory disclaimer regarding qualitative estimates"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class EventRiskItem(BaseModel):
    """Curated pre-mortem risk item with priority scoring, warning signs, and mitigations."""

    id: str = Field(..., min_length=1, max_length=50, description="Stable unique risk identifier (e.g. RISK-BUDGET-01)")
    category: RiskCategory = Field(..., description="Risk domain category")
    title: str = Field(..., min_length=1, max_length=200, description="Concise failure mode title")
    description: str = Field(..., min_length=1, max_length=1000, description="Detailed explanation of potential failure mode")
    likelihood: RiskLikelihood = Field(default=RiskLikelihood.UNKNOWN, description="Planning estimate likelihood: low, medium, high, unknown")
    impact: RiskImpact = Field(default=RiskImpact.MEDIUM, description="Operational severity: low, medium, high, critical")
    priority_score: int = Field(..., ge=1, le=12, description="Deterministic bounded priority score (1 to 12)")
    warning_signs: list[str] = Field(default_factory=list, description="Observable early indicators of this risk")
    mitigations: list[str] = Field(default_factory=list, description="Actionable preventive measures")
    contingency_plan: str = Field(..., min_length=1, max_length=500, description="Practical fallback if risk occurs")
    related_budget_category: str | None = Field(default=None, description="Related budget category, if applicable")
    related_milestone_id: str | None = Field(default=None, description="Related timeline milestone reference, if applicable")
    source: RiskSource = Field(default=RiskSource.RULES, description="Origin provenance: rules, demo, or gemini")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: Any) -> Any:
        if isinstance(value, str):
            val_lower = value.strip().lower()
            if val_lower == "deterministic":
                return RiskSource.RULES
        return value


class RiskSummary(BaseModel):
    """Summary counts of identified risks broken down by severity level."""

    total_risks: int = Field(..., ge=0, description="Total risks identified")
    critical_risks: int = Field(default=0, ge=0, description="Count of critical risks (score >= 9)")
    high_risks: int = Field(default=0, ge=0, description="Count of high risks (score 6 to 8)")
    medium_risks: int = Field(default=0, ge=0, description="Count of medium risks (score 3 to 5)")
    low_risks: int = Field(default=0, ge=0, description="Count of low risks (score < 3)")
    highest_priority_score: int = Field(default=0, ge=0, le=12, description="Highest priority score among identified risks")

    model_config = ConfigDict(extra="forbid")


class EventRisksResponse(BaseModel):
    """Complete pre-mortem risk assessment response for a saved event."""

    event_id: str = Field(..., description="Server-generated event identifier")
    event_type: EventType = Field(..., description="Event type category")
    total_risks: int = Field(..., ge=0, description="Total count of risks returned")
    summary: RiskSummary = Field(..., description="Aggregated risk count breakdown by priority")
    risks: list[EventRiskItem] = Field(default_factory=list, description="Deterministically sorted risk items")
    missing_data_warnings: list[str] = Field(default_factory=list, description="Warnings highlighting missing event data affecting analysis")
    disclaimer: str = Field(
        default="Risk scores and assessments are deterministic planning estimates based on current event profile parameters, not statistically calibrated probabilities or guaranteed predictions.",
        description="Advisory planning disclaimer"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class PlanningMilestone(BaseModel):
    """Pre-event planning milestone with relative week offset or target calendar date."""

    milestone_name: str = Field(..., min_length=1, description="Actionable milestone title")
    phase: EventPhase = Field(..., description="Lifecycle phase")
    weeks_before: int | None = Field(default=None, ge=0, description="Weeks before event date")
    target_date: date | None = Field(default=None, description="Optional target calendar date")
    description: str = Field(..., description="Milestone instructions and checklist items")
    completed: bool = Field(default=False, description="Completion toggle")


class RunSheetItem(BaseModel):
    """Event-day timeline run-sheet entry."""

    start_time: str = Field(..., description="Start time (e.g. '09:00 AM' or '14:30')")
    end_time: str = Field(..., description="End time (e.g. '10:30 AM' or '16:00')")
    activity_name: str = Field(..., min_length=1, description="Program segment or activity title")
    responsible_party: str = Field(..., description="Lead organizer, vendor, or family contact")
    description: str = Field(..., description="Details and special cues")

    @model_validator(mode="after")
    def validate_time_range(self) -> "RunSheetItem":
        """Validate start and end time order if provided in HH:MM 24h format."""
        pattern = r"^([01]?\d|2[0-3]):([0-5]\d)$"
        m_start = re.match(pattern, self.start_time.strip())
        m_end = re.match(pattern, self.end_time.strip())
        if m_start and m_end:
            h_start, min_start = int(m_start.group(1)), int(m_start.group(2))
            h_end, min_end = int(m_end.group(1)), int(m_end.group(2))
            t_start = h_start * 60 + min_start
            t_end = h_end * 60 + min_end
            if t_end < t_start:
                msg = (
                    f"Run-sheet end time '{self.end_time}' cannot be earlier "
                    f"than start time '{self.start_time}'"
                )
                raise ValueError(msg)
        return self


class EventTimelineResponse(BaseModel):
    """Composite event timeline combining planning milestones and day-of-event run-sheet."""

    planning_milestones: list[PlanningMilestone] = Field(
        default_factory=list, description="Pre-event milestone checklist"
    )
    run_sheet: list[RunSheetItem] = Field(
        default_factory=list, description="Day-of event schedule and run-sheet"
    )


class VendorPlanItem(BaseModel):
    """Vendor checklist plan item for event booking."""

    vendor_type: str = Field(..., description="Vendor category identifier")
    lead_time_weeks: int = Field(..., ge=0, description="Recommended booking lead time in weeks")
    typical_advance_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Typical advance deposit percentage"
    )
    allocated_budget_inr: int = Field(
        default=0, ge=0, description="Budget allocated for this vendor in INR"
    )
    booking_status: BookingStatus = Field(
        default=BookingStatus.PENDING, description="Booking workflow status"
    )
    ask_before_booking: list[str] = Field(
        default_factory=list, description="Key screening questions"
    )


class PersonalizedIdea(BaseModel):
    """Personalized creative suggestion for event enhancement."""

    title: str = Field(..., min_length=1, description="Concept title")
    explanation: str = Field(..., description="Rationale and cultural/theme alignment")
    implementation_details: str = Field(..., description="Practical execution and sourcing steps")
    estimated_cost_inr: int | None = Field(
        default=None, ge=0, description="Estimated incremental cost in INR"
    )
    target_category: str | None = Field(default=None, description="Relevant budget category")


class PreMortemRisk(BaseModel):
    """Pre-mortem risk assessment with probability and concrete mitigation."""

    risk_description: str = Field(..., min_length=1, description="Identified failure mode or risk")
    probability: float = Field(
        ..., ge=0.0, le=1.0, description="Estimated risk probability between 0 and 1"
    )
    cost_impact_pct_of_budget: float = Field(..., description="Potential cost impact percentage")
    mitigation: str = Field(..., min_length=1, description="Concrete mitigation strategy or Plan B")

    @field_validator("probability")
    @classmethod
    def validate_probability(cls, value: float) -> float:
        """Validate probability is finite and between 0.0 and 1.0."""
        if not math.isfinite(value) or value < 0.0 or value > 1.0:
            raise ValueError(f"Risk probability must be between 0.0 and 1.0, got: {value}")
        return value


class PersonaReview(BaseModel):
    """Review and feedback from a single family council persona."""

    persona_name: str = Field(..., description="Name/title of the persona")
    concerns: list[str] = Field(
        ..., min_length=1, description="Key concerns identified by this persona"
    )
    suggested_changes: list[str] = Field(
        ..., min_length=1, description="Specific alterations requested"
    )


class FamilyCouncilCompromise(BaseModel):
    """Synthesized compromise reconciling persona objections into an agreed plan."""

    agreed_plan: str = Field(
        ..., description="Balanced synthesis that addresses primary persona concerns"
    )
    remaining_objections: dict[str, list[str]] = Field(
        default_factory=dict, description="Documented remaining trade-offs per persona"
    )


class FamilyCouncilResponse(BaseModel):
    """Multi-perspective family council deliberation covering four distinct personas."""

    budget_holder: PersonaReview = Field(..., description="Pragmatic treasurer / financier review")
    elder_relative: PersonaReview = Field(..., description="Traditional elder cultural review")
    picky_friend: PersonaReview = Field(..., description="Modern peer aesthetic/experience review")
    parent_with_kids: PersonaReview = Field(..., description="Family logistics and comfort review")
    compromise: FamilyCouncilCompromise = Field(..., description="Synthesized family consensus")


# ==============================================================================
# Event Family Council (Prompt 14)
# ==============================================================================


class CouncilPriority(StrEnum):
    """Priority urgency level of council assessment recommendations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CouncilSource(StrEnum):
    """Provenance origin of family council persona evaluation."""

    RULES = "rules"
    DEMO = "demo"
    GEMINI = "gemini"


class CouncilPersonaAssessment(BaseModel):
    """Deliberation and assessment from a single simulated family council persona."""

    persona_id: str = Field(..., description="Stable persona identifier (e.g. budget_guardian)")
    persona_name: str = Field(..., description="Descriptive display name (e.g. The Budget Guardian)")
    perspective: str = Field(..., description="Concise description of this persona's primary focus")
    overall_assessment: str = Field(..., description="Short summary of this persona's overall evaluation")
    strengths: list[str] = Field(default_factory=list, description="Positive aspects grounded in the event plan")
    concerns: list[str] = Field(default_factory=list, description="Identified issues and risks with explanations")
    recommendations: list[str] = Field(default_factory=list, description="Actionable recommendations referencing budget, timeline, or vendors")
    priority: CouncilPriority = Field(default=CouncilPriority.MEDIUM, description="Urgency priority level: low, medium, or high")
    source: CouncilSource = Field(default=CouncilSource.RULES, description="Provenance source: rules, demo, or gemini")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: Any) -> Any:
        """Normalize legacy source aliases to CouncilSource enum."""
        if isinstance(value, str):
            val_lower = value.strip().lower()
            if val_lower == "deterministic":
                return CouncilSource.RULES
        return value


class CouncilTradeOff(BaseModel):
    """Documented creative tension or disagreement between two council personas."""

    perspective_a: str = Field(..., description="First persona perspective (e.g. The Budget Guardian)")
    perspective_b: str = Field(..., description="Second persona perspective (e.g. The Guest Comfort Advocate)")
    topic: str = Field(..., description="Core area of tension (e.g. Catering variety vs emergency buffer)")
    trade_off_description: str = Field(..., description="Clear explanation of the differing priorities without false consensus")
    suggestion: str = Field(..., description="Balanced practical compromise suggestion")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CouncilSummary(BaseModel):
    """Consolidated executive summary of family council deliberation."""

    strongest_aspects: list[str] = Field(default_factory=list, description="Top positive features agreed across the plan")
    critical_concerns: list[str] = Field(default_factory=list, description="Primary planning gaps requiring attention")
    recommended_next_actions: list[str] = Field(default_factory=list, description="Practical immediate next steps for the hosts")
    trade_offs: list[CouncilTradeOff] = Field(default_factory=list, description="Identified trade-offs between competing priorities")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class EventFamilyCouncilResponse(BaseModel):
    """Complete 4-persona family council review for a saved event."""

    event_id: str = Field(..., description="Server-generated unique event identifier")
    event_type: EventType = Field(..., description="Event type category")
    summary: CouncilSummary = Field(..., description="Executive summary of council consensus and key trade-offs")
    personas: list[CouncilPersonaAssessment] = Field(..., description="Exactly four differentiated persona assessments")
    missing_data_warnings: list[str] = Field(default_factory=list, description="Advisory warnings highlighting missing event fields")
    disclaimer: str = Field(
        default=(
            "Family Council assessments represent simulated advisory planning perspectives, not real family members or authoritative professional advice. "
            "No assumptions are made regarding religion, caste, family hierarchy, or personal cultural practices."
        ),
        description="Planning disclaimer confirming simulated nature of personas and neutral cultural handling",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("personas")
    @classmethod
    def validate_four_personas(cls, v: list[CouncilPersonaAssessment]) -> list[CouncilPersonaAssessment]:
        """Verify that exactly four distinct personas are returned."""
        if len(v) != 4:
            raise ValueError(f"Family Council must contain exactly 4 personas, got {len(v)}")
        ids = [p.persona_id for p in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate persona IDs detected in Family Council response")
        return v


class WhatsAppMessageDraft(BaseModel):
    """Plain-text crisis communication message ready to be copied."""

    target: MessageTarget = Field(..., description="Target audience: vendor, guests, family")
    recipient_label: str = Field(
        ..., description="Recipient identifier (e.g. 'All Guests', 'Backup Caterer')"
    )
    message_text: str = Field(
        ..., min_length=1, description="Formatted message suitable for copying"
    )


class CrisisRecoveryPlan(BaseModel):
    """Actionable crisis recovery playbook with timeline updates and communication drafts."""

    detected_crisis_type: str = Field(..., description="Category of the crisis encountered")
    severity: int = Field(
        ..., ge=1, le=3, description="Crisis severity rating (1=minor, 3=critical)"
    )
    timeline_changes: list[str] = Field(
        default_factory=list, description="Immediate timeline adjustments"
    )
    explanation: str = Field(..., description="Root cause and operational impact assessment")
    recommended_actions: list[str] = Field(
        ..., min_length=1, description="Step-by-step recovery actions"
    )
    whatsapp_message_drafts: list[WhatsAppMessageDraft] = Field(
        default_factory=list, description="Ready-to-copy WhatsApp messages for stakeholders"
    )


class CrisisEvaluationRequest(BaseModel):
    """Request payload to evaluate an active or potential event crisis."""

    crisis_type: str = Field(
        ..., min_length=2, max_length=100, description="Category of the crisis encountered"
    )
    severity: int = Field(
        ..., ge=1, le=3, description="Crisis severity level (1=minor, 2=moderate, 3=critical)"
    )
    description: str | None = Field(
        default=None, max_length=1000, description="Optional host description of what happened"
    )
    affected_area: str | None = Field(
        default=None, max_length=100, description="Affected area (e.g. catering, venue, weather, power)"
    )
    event_phase: EventPhase = Field(
        default=EventPhase.EVENT_DAY, description="Phase during which the crisis emerged"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MatchedCrisisScenario(BaseModel):
    """Scenario record matched from the validated CSV dataset or generated as fallback."""

    scenario_id: str = Field(..., description="Unique scenario ID from dataset or fallback identifier")
    is_dataset_match: bool = Field(
        ..., description="Whether this scenario was found in the validated CSV dataset"
    )
    crisis_type: str = Field(..., description="Standardized category of the crisis")
    severity: int = Field(..., ge=1, le=3, description="Severity rating (1=minor, 3=critical)")
    event_type: EventType = Field(..., description="Event type category")
    phase: EventPhase = Field(..., description="Lifecycle phase when disruption occurred")
    description: str = Field(..., description="Concise summary of disruption")
    recommended_fix: str = Field(..., description="Standard immediate fix guideline")
    cost_impact_pct_of_budget: float = Field(
        ..., description="Calibrated cost impact percentage on total budget"
    )
    message_target: MessageTarget = Field(..., description="Primary audience for initial messaging")
    synthetic: bool = Field(..., description="Whether scenario is synthetic data")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CrisisActionItem(BaseModel):
    """Specific prioritized action step in crisis recovery."""

    priority: int = Field(..., ge=1, le=3, description="1=immediate/urgent, 2=operational, 3=follow-up")
    category: str = Field(..., description="Action focus category (e.g. immediate_safety, operational_continuity)")
    title: str = Field(..., description="Action title")
    action: str = Field(..., description="Detailed actionable instruction")
    responsible_party: str = Field(..., description="Designated role responsible for execution")
    timeframe: str = Field(..., description="Estimated completion window (e.g. Immediate (0-15 mins))")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CrisisBudgetImpact(BaseModel):
    """Financial impact analysis of the crisis on event budget."""

    cost_impact_pct: float = Field(..., description="Estimated cost change percentage")
    estimated_rupee_impact: int = Field(..., description="Calculated cost impact in INR")
    affected_categories: list[str] = Field(
        default_factory=list, description="Primary budget categories impacted"
    )
    existing_buffer_inr: int = Field(..., description="Current contingency buffer in INR")
    buffer_sufficient: bool = Field(
        ..., description="Whether the emergency buffer can absorb the estimated impact"
    )
    advice: str = Field(..., description="Deterministic financial advice without fabricated quotes")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CrisisCommunicationDraft(BaseModel):
    """Ready-to-copy stakeholder communication draft with clear placeholders."""

    recipient_role: str = Field(..., description="Recipient role: vendor, guests, family, organizers")
    recipient_label: str = Field(..., description="Friendly display label for recipient")
    subject_or_header: str = Field(..., description="Message subject line or broadcast header")
    message_text: str = Field(..., description="Formatted message with placeholders")
    source: str = Field(default="deterministic", description="Provenance source: deterministic, demo, or gemini")
    placeholders: list[str] = Field(
        default_factory=list, description="List of placeholder tokens needing user completion"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class EventCrisisRecoveryResponse(BaseModel):
    """Comprehensive recovery plan for a crisis occurring on an event."""

    event_id: str = Field(..., description="Target event ID")
    event_type: EventType = Field(..., description="Event type category")
    event_name: str | None = Field(default=None, description="Event name if set")
    event_phase: EventPhase = Field(..., description="Event phase when crisis occurred")
    matched_scenario: MatchedCrisisScenario = Field(
        ..., description="Scenario matched from dataset or labeled fallback"
    )
    crisis_summary: str = Field(..., description="Concise assessment of the situation")
    severity: int = Field(..., ge=1, le=3, description="Crisis severity rating")
    affected_area: str = Field(..., description="Primary affected operational area")
    immediate_actions: list[CrisisActionItem] = Field(
        ..., min_length=1, description="Top-priority actions focusing on safety and triage"
    )
    next_step_actions: list[CrisisActionItem] = Field(
        default_factory=list, description="Secondary operational continuity actions"
    )
    alternatives: list[str] = Field(
        default_factory=list, description="Practical alternative options and contingency steps"
    )
    budget_impact: CrisisBudgetImpact = Field(
        ..., description="Deterministic budget impact and buffer comparison"
    )
    timeline_implications: list[str] = Field(
        default_factory=list, description="Timeline adjustments and milestone delays"
    )
    relevant_milestone_ids: list[str] = Field(
        default_factory=list, description="IDs of affected timeline milestones"
    )
    relevant_vendor_checklist_ids: list[str] = Field(
        default_factory=list, description="IDs of affected vendor checklist tasks"
    )
    escalation_guidance: str = Field(
        ..., description="Clear escalation guidance and emergency service contact recommendations"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Operational warnings and assumptions"
    )
    communication_drafts: list[CrisisCommunicationDraft] = Field(
        default_factory=list, description="Copyable communication drafts for stakeholders"
    )
    disclaimer: str = Field(
        default=(
            "PlanProof AI crisis recovery plans provide deterministic advisory coordination steps. "
            "The system does not automatically execute bookings, alter budgets, cancel contracts, "
            "or contact external vendors. For life safety emergencies, contact local emergency services immediately (112 / 108 / 101)."
        ),
        description="Operational safety disclaimer",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CrisisTypeMetadata(BaseModel):
    """Metadata descriptor for supported crisis categories."""

    crisis_type: str = Field(..., description="Identifier matching CSV crisis_type")
    title: str = Field(..., description="Human-readable title")
    affected_area: str = Field(..., description="Default affected operational area")
    typical_severity: int = Field(..., description="Typical severity level")
    description: str = Field(..., description="Short explanation of crisis type")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RecoveryProgressSummary(BaseModel):
    """Summary counts and completion percentage calculated from tracked actions."""

    total_actions: int = Field(default=0, ge=0, description="Total count of tracked recovery actions")
    pending_actions: int = Field(default=0, ge=0, description="Count of actions currently pending")
    in_progress_actions: int = Field(default=0, ge=0, description="Count of actions currently in progress")
    completed_actions: int = Field(default=0, ge=0, description="Count of actions successfully completed")
    completion_percentage: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Calculated action completion percentage (0-100)"
    )

    model_config = ConfigDict(extra="forbid")


class TrackedRecoveryAction(BaseModel):
    """Individual actionable recovery step tracked within an event crisis record."""

    action_id: str = Field(..., description="Stable, unique action identifier (e.g. ACT-1 or ACT-...)")
    recovery_id: str | None = Field(default=None, description="Owning crisis recovery identifier")
    title: str = Field(..., min_length=1, max_length=200, description="Concise action item title")
    description: str = Field(..., min_length=1, max_length=1000, description="Detailed actionable instruction")
    priority: int = Field(default=2, ge=1, le=3, description="Priority rating (1=immediate, 2=operational, 3=follow-up)")
    status: RecoveryActionStatus = Field(
        default=RecoveryActionStatus.PENDING, description="Current tracking status"
    )
    notes: str | None = Field(
        default=None, max_length=1000, description="Optional coordinator execution notes or updates"
    )
    created_at: datetime = Field(..., description="Timestamp when action was added to tracking (UTC)")
    updated_at: datetime = Field(..., description="Timestamp when action was last modified (UTC)")
    progress: RecoveryProgressSummary | None = Field(
        default=None, description="Optional parent recovery progress summary snapshot"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CrisisRecoveryRecord(BaseModel):
    """Saved recovery record and action tracker scoped to an event."""

    recovery_id: str = Field(..., description="Unique server-generated recovery identifier (e.g. REC-...)")
    event_id: str = Field(..., description="Owning event identifier")
    crisis_type: str = Field(..., min_length=2, max_length=100, description="Category of the crisis encountered")
    severity: int = Field(..., ge=1, le=3, description="Crisis severity rating (1=minor, 2=moderate, 3=critical)")
    description: str | None = Field(
        default=None, max_length=1000, description="Validated, length-limited description of the crisis"
    )
    recovery_plan: EventCrisisRecoveryResponse = Field(
        ..., description="Validated recovery plan snapshot at the time of crisis evaluation"
    )
    source: str = Field(
        default="rules", max_length=50, description="Actual provenance source of the plan (e.g. rules, demo, gemini)"
    )
    status: RecoveryStatus = Field(
        default=RecoveryStatus.OPEN, description="Overall recovery lifecycle status (open, in_progress, resolved)"
    )
    actions: list[TrackedRecoveryAction] = Field(
        default_factory=list, description="List of tracked action items with execution status and notes"
    )
    progress: RecoveryProgressSummary = Field(
        default_factory=RecoveryProgressSummary, description="Recalculated action progress summary"
    )
    total_actions: int = Field(default=0, ge=0, description="Total count of saved actions")
    completed_actions: int = Field(default=0, ge=0, description="Count of completed actions")
    created_at: datetime = Field(..., description="Timestamp when recovery record was created (UTC)")
    updated_at: datetime = Field(..., description="Timestamp when recovery record was last updated (UTC)")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class TrackedActionInput(BaseModel):
    """Input payload to specify or customize an action to track when saving a recovery plan."""

    action_id: str | None = Field(default=None, max_length=100, description="Optional stable action ID")
    title: str = Field(..., min_length=1, max_length=200, description="Action title")
    description: str = Field(..., min_length=1, max_length=1000, description="Detailed actionable instruction")
    priority: int = Field(default=2, ge=1, le=3, description="Priority rating (1=high, 2=medium, 3=low)")
    status: RecoveryActionStatus = Field(
        default=RecoveryActionStatus.PENDING, description="Initial action status"
    )
    notes: str | None = Field(default=None, max_length=1000, description="Optional initial notes")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RecoveryRecordCreateRequest(BaseModel):
    """Request payload to save a validated recovery record from a generated crisis plan."""

    crisis_type: str = Field(..., min_length=2, max_length=100, description="Category of the crisis")
    severity: int = Field(..., ge=1, le=3, description="Crisis severity rating (1=minor, 2=moderate, 3=critical)")
    description: str | None = Field(
        default=None, max_length=1000, description="Optional host description of the crisis"
    )
    recovery_plan: EventCrisisRecoveryResponse = Field(
        ..., description="Validated recovery plan snapshot generated by crisis evaluation"
    )
    source: str = Field(
        default="rules", max_length=50, description="Source attribution (e.g. rules, demo, gemini)"
    )
    status: RecoveryStatus = Field(
        default=RecoveryStatus.OPEN, description="Initial recovery status"
    )
    actions: list[TrackedActionInput] | None = Field(
        default=None,
        description="Optional list of specific actions to track. If omitted, extracted from recovery_plan.",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RecoveryRecordUpdateRequest(BaseModel):
    """Request payload to partially update a recovery record (e.g. status or description)."""

    status: RecoveryStatus | None = Field(default=None, description="Updated recovery status")
    description: str | None = Field(
        default=None, max_length=1000, description="Updated crisis description"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class TrackedActionUpdateRequest(BaseModel):
    """Request payload to update an action's execution status and coordinator notes."""

    status: RecoveryActionStatus | None = Field(default=None, description="Updated action status")
    notes: str | None = Field(
        default=None, max_length=1000, description="Updated coordinator execution notes"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class EventPlanResponse(BaseModel):
    """Full composite event plan data contract for future AI generation."""

    event_name: str = Field(..., description="Generated descriptive event title")
    event_type: EventType = Field(..., description="Event type")
    city_tier: CityTier = Field(..., description="City tier")
    city: str = Field(..., description="City location")
    guest_count: int = Field(..., description="Guest headcount")
    total_budget_inr: int = Field(..., description="Total budget in INR")
    budget: EventBudgetBreakdown = Field(..., description="Deterministic category budget breakdown")
    timeline: EventTimelineResponse = Field(..., description="Planning and execution timeline")
    vendor_plan: list[VendorPlanItem] = Field(
        default_factory=list, description="Vendor booking checklist"
    )
    personalized_ideas: list[PersonalizedIdea] = Field(
        default_factory=list, description="Curated personalized ideas"
    )
    risks: list[PreMortemRisk] = Field(
        default_factory=list, description="Pre-mortem risk assessment"
    )
    family_council: FamilyCouncilResponse = Field(
        ..., description="Four-persona family council review"
    )


# ==============================================================================
# 5. System Status and Standard Error Schemas
# ==============================================================================


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
    crisis_scenarios: CrisisSummary = Field(...)
    budget_splits: BudgetSummary = Field(...)
    vendor_checklists: VendorSummary = Field(...)
    row_count: int = Field(..., description="Crisis scenario count")
    available_crisis_types: list[str] = Field(default_factory=list)
    available_event_types: list[str] = Field(default_factory=list)
    available_city_tiers: list[str] = Field(default_factory=list)
    severity_range: SeverityRange = Field(...)
    budget_splits_loaded: bool = Field(...)
    vendor_checklists_loaded: bool = Field(...)


class ErrorDetail(BaseModel):
    """Standardized error envelope payload."""

    code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Human-readable explanation of the error")
    details: Any | None = Field(default=None, description="Optional safe structured context")


class StandardErrorResponse(BaseModel):
    """Consistent application error response envelope."""

    error: ErrorDetail = Field(..., description="Standardized error details")


# ==============================================================================
# 6. Budget Engine Schemas
# ==============================================================================


class BudgetCalculateRequest(BaseModel):
    """Input request schema for initial budget calculation."""

    event_type: EventType = Field(..., description="Event category")
    city_tier: CityTier = Field(..., description="City tier category")
    total_budget_inr: int = Field(
        ...,
        description="Total event budget in INR (strict integer, ₹10,000 to ₹50,000,000)",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("total_budget_inr", mode="before")
    @classmethod
    def validate_strict_budget_inr(cls, value: Any) -> int:
        """Reject booleans and decimals for budget, enforce ₹10,000 to ₹50,000,000."""
        if isinstance(value, bool):
            raise ValueError("total_budget_inr must be an integer, not a boolean")
        if isinstance(value, float):
            raise ValueError("total_budget_inr must be an integer amount in INR, not a decimal")
        try:
            val_int = int(value)
        except (ValueError, TypeError) as err:
            raise ValueError("total_budget_inr must be a valid integer amount in INR") from err

        if val_int < 10000 or val_int > 50000000:
            raise ValueError(
                f"total_budget_inr must be between ₹10,000 and ₹50,000,000, got: ₹{val_int:,}"
            )
        return val_int


class BudgetCalculationResponse(BaseModel):
    """Detailed initial budget calculation response."""

    event_type: EventType = Field(..., description="Event category")
    city_tier: CityTier = Field(..., description="City tier category")
    total_budget_inr: int = Field(..., description="Total event budget in INR")
    allocations: EventBudgetBreakdown = Field(..., description="Category rupee allocations")
    percentages: dict[str, float] = Field(..., description="Per-category percentage breakdown")
    method: str = Field(
        default="largest_remainder_hamilton",
        description="Deterministic rounding algorithm used",
    )


class BudgetRebalanceRequest(BaseModel):
    """Input request schema for budget rebalancing."""

    current_allocations: EventBudgetBreakdown = Field(
        ..., description="Existing valid 8-category budget allocation"
    )
    new_total_budget_inr: int = Field(
        ...,
        description="New total event budget in INR (strict integer, ₹10,000 to ₹50,000,000)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_total_budget_inr", mode="before")
    @classmethod
    def validate_strict_new_budget(cls, value: Any) -> int:
        """Reject booleans and decimals for new budget, enforce ₹10,000 to ₹50,000,000."""
        if isinstance(value, bool):
            raise ValueError("new_total_budget_inr must be an integer, not a boolean")
        if isinstance(value, float):
            raise ValueError("new_total_budget_inr must be an integer amount in INR, not a decimal")
        try:
            val_int = int(value)
        except (ValueError, TypeError) as err:
            raise ValueError("new_total_budget_inr must be a valid integer amount in INR") from err

        if val_int < 10000 or val_int > 50000000:
            raise ValueError(
                f"new_total_budget_inr must be between ₹10,000 and ₹50,000,000, got: ₹{val_int:,}"
            )
        return val_int


class BudgetRebalanceResponse(BaseModel):
    """Detailed budget rebalance outcome with differences and explanation."""

    previous_total_inr: int = Field(..., description="Previous total event budget in INR")
    new_total_inr: int = Field(..., description="New total event budget in INR")
    allocations: EventBudgetBreakdown = Field(..., description="Updated category allocations")
    differences: dict[str, int] = Field(
        ..., description="Per-category rupee differences (new - old)"
    )
    percentages: dict[str, float] = Field(..., description="Per-category percentage of new total")
    categories_reduced_first: list[str] = Field(
        default_factory=list, description="Discretionary categories trimmed first"
    )
    protected_categories: list[str] = Field(
        default_factory=lambda: ["catering", "buffer"],
        description="Essential categories protected from cuts where possible",
    )
    protected_preserved: bool = Field(
        ...,
        description="Whether protected categories (catering, buffer) were preserved without cuts",
    )
    explanation: str = Field(
        ..., description="Deterministic human-readable explanation of adjustments"
    )


class AIStatusResponse(BaseModel):
    """Configuration status for the Google Gemini AI integration."""

    configured: bool = Field(..., description="Whether Gemini API is configured with an API key")
    model: str = Field(..., description="Configured Gemini model identifier")
    timeout_seconds: float = Field(..., description="Configured request timeout in seconds")
    max_retries: int = Field(..., description="Configured maximum retries for transient failures")
    mode: str = Field(default="auto", description="Configured AI operation mode: auto, demo, gemini")


# ==============================================================================
# 7. AI Operation & Fallback Result Envelopes
# ==============================================================================

DataT = TypeVar("DataT")


class AIResultStatus(StrEnum):
    """Operation outcome status for AI-dependent tasks."""

    SUCCESS = "success"
    FALLBACK = "fallback"
    UNAVAILABLE = "unavailable"


class AIResultSource(StrEnum):
    """Provenance source of the result payload."""

    GEMINI = "gemini"
    DETERMINISTIC = "deterministic"
    DEMO = "demo"


class AITask(StrEnum):
    """Standardized task classifications for AI orchestration."""

    EVENT_TIMELINE = "event_timeline"
    EVENT_RISKS = "event_risks"
    CRISIS_RECOVERY = "crisis_recovery"
    FAMILY_COUNCIL = "family_council"
    PERSONALIZED_IDEAS = "personalized_ideas"
    FULL_EVENT_PLAN = "full_event_plan"


def sanitize_safe_text(text: str) -> str:
    """Sanitize text to strip absolute filesystem paths and protect system information."""
    if not text:
        return text
    # Strip absolute Unix (/Users/... or /home/...) and Windows (C:\...) paths
    cleaned = re.sub(r"(/[a-zA-Z0-9_\.\-]+)+/([a-zA-Z0-9_\.\-]+)", r"\2", text)
    cleaned = re.sub(r"([a-zA-Z]:\\[a-zA-Z0-9_\.\-\\]+)\\([a-zA-Z0-9_\.\-]+)", r"\2", cleaned)
    return cleaned


class AIResultEnvelope(BaseModel, Generic[DataT]):
    """Standardized response envelope for AI-dependent operations."""

    status: AIResultStatus = Field(
        ..., description="Operation outcome status: success, fallback, or unavailable"
    )
    source: AIResultSource = Field(
        ..., description="Result source provenance: gemini, deterministic, or demo"
    )
    data: DataT | None = Field(
        default=None, description="Validated feature-specific result payload"
    )
    message: str | None = Field(
        default=None, description="Optional user-safe explanation"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-sensitive operational warnings"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("message")
    @classmethod
    def sanitize_envelope_message(cls, value: str | None) -> str | None:
        """Sanitize message to eliminate absolute filesystem paths."""
        return sanitize_safe_text(value) if value else value

    @field_validator("warnings")
    @classmethod
    def sanitize_envelope_warnings(cls, warnings: list[str]) -> list[str]:
        """Sanitize warnings list to prevent path or token leakage."""
        return [sanitize_safe_text(w) for w in warnings if w and w.strip()]

    @model_validator(mode="after")
    def validate_envelope_integrity(self) -> "AIResultEnvelope[DataT]":
        """Enforce envelope consistency between status, source, and payload presence."""
        if self.status in (AIResultStatus.SUCCESS, AIResultStatus.FALLBACK) and self.data is None:
            raise ValueError(
                f"Result envelope data cannot be None when status is '{self.status.value}'"
            )
        if self.status == AIResultStatus.UNAVAILABLE and self.data is not None:
            raise ValueError(
                f"Result envelope data must be None when status is '{self.status.value}'"
            )
        return self


# ==============================================================================
# PROMPT 19: EVENT READINESS SCORE & PLANNING PROGRESS SCHEMAS
# ==============================================================================


class ReadinessStatus(StrEnum):
    """Lifecycle and progress status for overall event readiness."""

    NOT_STARTED = "not_started"
    NEEDS_ATTENTION = "needs_attention"
    IN_PROGRESS = "in_progress"
    WELL_PREPARED = "well_prepared"
    INSUFFICIENT_DATA = "insufficient_data"


class ReadinessCategory(StrEnum):
    """Core evaluation domain for event readiness assessment."""

    PLANNING_COMPLETENESS = "planning_completeness"
    BUDGET_READINESS = "budget_readiness"
    TIMELINE_READINESS = "timeline_readiness"
    VENDOR_COORDINATION = "vendor_coordination"
    RISK_PREPAREDNESS = "risk_preparedness"
    CRISIS_FOLLOWUP = "crisis_followup"


class ReadinessActionPriority(StrEnum):
    """Urgency priority for recommended next planning actions."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReadinessCategoryScore(BaseModel):
    """Category-level score, status, explanation, and supporting metrics."""

    category: ReadinessCategory = Field(..., description="Evaluation domain category")
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable category name")
    score: int | None = Field(
        default=None, ge=0, le=100, description="Deterministic category score (0-100), or None if unavailable"
    )
    weight_percentage: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Normalized weight percentage in overall score"
    )
    is_available: bool = Field(
        default=True, description="Whether sufficient underlying data exists to score this category"
    )
    explanation: str = Field(
        ..., min_length=1, max_length=500, description="Concise diagnostic summary of category health"
    )
    supporting_counts: dict[str, int | float] = Field(
        default_factory=dict, description="Supporting operational counts and metrics"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ReadinessNextAction(BaseModel):
    """Prioritized planning action item referencing real existing tasks or risks."""

    action_id: str = Field(..., min_length=1, max_length=100, description="Unique action identifier")
    title: str = Field(..., min_length=1, max_length=200, description="Short actionable title")
    description: str = Field(..., min_length=1, max_length=500, description="Detailed instructions")
    priority: ReadinessActionPriority = Field(..., description="Action priority level")
    category: str = Field(..., min_length=1, max_length=50, description="Domain category (timeline, vendor, risk, etc.)")
    target_id: str | None = Field(
        default=None, max_length=100, description="Referenced entity ID (milestone, vendor task, risk, recovery action)"
    )
    target_view: str = Field(
        ..., min_length=1, max_length=50, description="Frontend navigation target view"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class EventReadinessResponse(BaseModel):
    """Comprehensive deterministic event readiness assessment and planning progress."""

    event_id: str = Field(..., min_length=1, description="Target event profile identifier")
    overall_score: int | None = Field(
        default=None, ge=0, le=100, description="Deterministic overall readiness score (0-100), or None if insufficient data"
    )
    readiness_status: ReadinessStatus = Field(
        ..., description="Overall readiness state (not_started, needs_attention, in_progress, well_prepared, insufficient_data)"
    )
    category_scores: list[ReadinessCategoryScore] = Field(
        default_factory=list, description="Detailed category breakdowns"
    )
    completed_items: int = Field(default=0, ge=0, description="Total count of completed planning items")
    outstanding_items: int = Field(default=0, ge=0, description="Total count of pending/incomplete planning items")
    critical_concerns: list[str] = Field(
        default_factory=list, description="Critical risks, overdue milestones, or missing safety buffers requiring attention"
    )
    recommended_next_actions: list[ReadinessNextAction] = Field(
        default_factory=list, description="Prioritized next steps referencing real planning items"
    )
    missing_information: list[str] = Field(
        default_factory=list, description="Information gaps that reduce readiness or prevent full evaluation"
    )
    calculation_method: str = Field(
        default="Deterministic multi-category weighted average (Planning: 15%, Budget: 25%, Timeline: 20%, Vendors: 25%, Risks: 15%; dynamically normalized for available categories).",
        description="Scoring methodology description"
    )
    generated_at: datetime = Field(..., description="Generation timestamp in UTC")
    disclaimer: str = Field(
        default="The Event Readiness Score is a deterministic planning progress metric reflecting documented completion of tasks, buffer allocation, and risk mitigations. It is an operational guide, not a guarantee or statistical prediction of event success.",
        description="Planning disclaimer"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


# Rebuild EventProfile to resolve forward reference to CrisisRecoveryRecord
EventProfile.model_rebuild()


