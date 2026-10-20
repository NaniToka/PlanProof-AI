"""Pydantic schemas and models for PlanProof AI."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CrisisScenario(BaseModel):
    """Schema representing a single crisis recovery scenario record."""

    id: str = Field(..., description="Unique scenario identifier (e.g. CR0000001)")
    event_type: str = Field(..., description="Event type: wedding, birthday, community_event")
    city_tier: str = Field(..., description="City tier: metro, tier2, tier3")
    guest_count: int = Field(..., description="Total guest count, must be positive")
    phase: str = Field(..., description="Phase: planning, day_before, event_day")
    crisis_type: str = Field(..., description="Standardized category of the crisis")
    severity: int = Field(..., description="Severity level from 1 (minor) to 3 (critical)")
    description: str = Field(..., description="Description of the crisis scenario")
    recommended_fix: str = Field(..., description="Actionable immediate recovery step")
    cost_impact_pct_of_budget: float = Field(
        ..., description="Estimated percentage cost impact on total budget"
    )
    message_target: str = Field(..., description="Target audience: family, vendor, guests")
    synthetic: bool = Field(True, description="Flag indicating synthetic assumption")

    model_config = ConfigDict(str_strip_whitespace=True)

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
        """Validate that guest count is strictly positive."""
        if value <= 0:
            raise ValueError(f"Guest count must be positive (> 0), got: {value}")
        return value

    @field_validator("description", "recommended_fix")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        """Validate that text fields are not blank."""
        if not value.strip():
            raise ValueError("Field cannot be empty or blank")
        return value


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


class DataStatusResponse(BaseModel):
    """Safe status metadata for loaded datasets without exposing raw records."""

    status: str = Field(..., description="Data repository status: healthy, degraded, error")
    dataset_loaded: bool = Field(..., description="Whether crisis dataset loaded")
    row_count: int = Field(..., description="Total crisis scenarios loaded")
    available_crisis_types: list[str] = Field(
        default_factory=list, description="Unique crisis types available"
    )
    available_event_types: list[str] = Field(
        default_factory=list, description="Unique event types available"
    )
    available_city_tiers: list[str] = Field(
        default_factory=list, description="Unique city tiers available"
    )
    severity_range: SeverityRange = Field(..., description="Observed severity bounds")
    budget_splits_loaded: bool = Field(..., description="Whether budget splits loaded")
    vendor_checklists_loaded: bool = Field(..., description="Whether vendor checklists loaded")
