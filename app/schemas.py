"""Pydantic schemas and data contracts for PlanProof AI.

Defines:
- Core domain enums (EventType, CityTier, EventPhase, MessageTarget, LanguageCode, BookingStatus)
- Dataset validation models (CrisisScenario, BudgetSplitsDataset, VendorChecklistsDataset)
- Event planning input request model (EventPlanRequest)
- Event planning output models (Budget, Timeline, Vendors, Ideas, Risks, Family Council, Crisis)
- Standard error and status envelope models
"""

import math
import re
from datetime import date
from enum import StrEnum
from typing import Any

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
# 3. Event Planning Input Schemas
# ==============================================================================


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

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("guest_count", mode="before")
    @classmethod
    def validate_strict_guest_count(cls, value: Any) -> int:
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

    @field_validator("city")
    @classmethod
    def validate_city_non_empty(cls, value: str) -> str:
        """Ensure city string is not blank."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("City name cannot be empty or whitespace")
        return stripped


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
