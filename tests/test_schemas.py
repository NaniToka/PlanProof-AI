"""Automated unit tests for EventPlanRequest and feature response schemas."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    CityTier,
    CrisisRecoveryPlan,
    ErrorDetail,
    EventBudgetBreakdown,
    EventPhase,
    EventPlanRequest,
    EventType,
    FamilyCouncilCompromise,
    FamilyCouncilResponse,
    LanguageCode,
    MessageTarget,
    PersonalizedIdea,
    PersonaReview,
    PlanningMilestone,
    PreMortemRisk,
    RunSheetItem,
    StandardErrorResponse,
    VendorPlanItem,
    WhatsAppMessageDraft,
)

# ==============================================================================
# 1. EventPlanRequest Tests
# ==============================================================================


def test_valid_event_requests() -> None:
    """Verify valid requests for all supported event types."""
    for event_type in EventType:
        req = EventPlanRequest(
            event_type=event_type,
            guest_count=250,
            total_budget_inr=1500000,
            city_tier=CityTier.METRO,
            city="Bengaluru",
            theme_notes="Eco-friendly traditional floral setup",
            language=LanguageCode.EN,
        )
        assert req.event_type == event_type
        assert req.guest_count == 250
        assert req.total_budget_inr == 1500000
        assert req.city == "Bengaluru"


def test_guest_count_boundary_limits() -> None:
    """Verify guest count minimum (1) and maximum (2000)."""
    req_min = EventPlanRequest(
        event_type=EventType.BIRTHDAY,
        guest_count=1,
        total_budget_inr=50000,
        city_tier=CityTier.TIER2,
        city="Coimbatore",
    )
    assert req_min.guest_count == 1

    req_max = EventPlanRequest(
        event_type=EventType.COMMUNITY_EVENT,
        guest_count=2000,
        total_budget_inr=5000000,
        city_tier=CityTier.METRO,
        city="Mumbai",
    )
    assert req_max.guest_count == 2000


def test_guest_count_out_of_bounds_rejected() -> None:
    """Verify guest counts < 1 or > 2000 raise ValidationError."""
    with pytest.raises(ValidationError) as exc_low:
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=0,
            total_budget_inr=1000000,
            city_tier=CityTier.METRO,
            city="Delhi",
        )
    assert "between 1 and 2,000" in str(exc_low.value)

    with pytest.raises(ValidationError) as exc_high:
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=2500,
            total_budget_inr=1000000,
            city_tier=CityTier.METRO,
            city="Delhi",
        )
    assert "between 1 and 2,000" in str(exc_high.value)


def test_strict_int_validation_rejects_bool_and_decimal() -> None:
    """Verify boolean and decimal values are strictly rejected for integer fields."""
    # Reject boolean for guest_count
    with pytest.raises(ValidationError) as exc_bool_guest:
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=True,  # type: ignore[arg-type]
            total_budget_inr=1000000,
            city_tier=CityTier.METRO,
            city="Delhi",
        )
    assert "must be an integer, not a boolean" in str(exc_bool_guest.value)

    # Reject boolean for total_budget_inr
    with pytest.raises(ValidationError) as exc_bool_budget:
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=150,
            total_budget_inr=False,  # type: ignore[arg-type]
            city_tier=CityTier.METRO,
            city="Delhi",
        )
    assert "must be an integer, not a boolean" in str(exc_bool_budget.value)

    # Reject float for budget
    with pytest.raises(ValidationError) as exc_float:
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=150,
            total_budget_inr=50000.75,  # type: ignore[arg-type]
            city_tier=CityTier.METRO,
            city="Delhi",
        )
    assert "not a decimal" in str(exc_float.value)


def test_budget_range_boundaries() -> None:
    """Verify budget limits: ₹10,000 to ₹50,000,000 inclusive."""
    # ₹10,000 allowed
    req_min = EventPlanRequest(
        event_type=EventType.BIRTHDAY,
        guest_count=15,
        total_budget_inr=10000,
        city_tier=CityTier.TIER3,
        city="Warangal",
    )
    assert req_min.total_budget_inr == 10000

    # ₹50,000,000 allowed
    req_max = EventPlanRequest(
        event_type=EventType.WEDDING,
        guest_count=1200,
        total_budget_inr=50000000,
        city_tier=CityTier.METRO,
        city="Mumbai",
    )
    assert req_max.total_budget_inr == 50000000

    # Below 10,000 rejected
    with pytest.raises(ValidationError) as exc_low:
        EventPlanRequest(
            event_type=EventType.BIRTHDAY,
            guest_count=15,
            total_budget_inr=9999,
            city_tier=CityTier.TIER3,
            city="Warangal",
        )
    assert "between ₹10,000 and ₹50,000,000" in str(exc_low.value)

    # Above 50,000,000 rejected
    with pytest.raises(ValidationError) as exc_high:
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=500,
            total_budget_inr=50000001,
            city_tier=CityTier.METRO,
            city="Mumbai",
        )
    assert "between ₹10,000 and ₹50,000,000" in str(exc_high.value)


def test_city_validation() -> None:
    """Verify city name whitespace trimming and empty rejection."""
    # Strips whitespace
    req = EventPlanRequest(
        event_type=EventType.WEDDING,
        guest_count=200,
        total_budget_inr=1000000,
        city_tier=CityTier.METRO,
        city="   Chennai   ",
    )
    assert req.city == "Chennai"

    # Rejects empty city
    with pytest.raises(ValidationError):
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=200,
            total_budget_inr=1000000,
            city_tier=CityTier.METRO,
            city="   ",
        )


def test_excessive_length_rejected() -> None:
    """Verify city > 100 or theme_notes > 1000 chars are rejected."""
    with pytest.raises(ValidationError):
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=200,
            total_budget_inr=1000000,
            city_tier=CityTier.METRO,
            city="A" * 105,
        )

    with pytest.raises(ValidationError):
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=200,
            total_budget_inr=1000000,
            city_tier=CityTier.METRO,
            city="Pune",
            theme_notes="X" * 1005,
        )


def test_extra_fields_forbidden() -> None:
    """Verify unexpected fields are rejected rather than silently ignored."""
    with pytest.raises(ValidationError) as exc:
        EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=200,
            total_budget_inr=1000000,
            city_tier=CityTier.METRO,
            city="Pune",
            unauthorized_field="malicious_payload",  # type: ignore[call-arg]
        )
    assert "Extra inputs are not permitted" in str(exc.value)


# ==============================================================================
# 2. Response Schemas Tests
# ==============================================================================


def test_event_budget_breakdown_validation() -> None:
    """Verify budget allocations sum exactly to the stated total."""
    # Valid sum
    valid_budget = EventBudgetBreakdown(
        venue=260000,
        catering=300000,
        decor=110000,
        photo_video=90000,
        attire_beauty=100000,
        entertainment=50000,
        logistics=30000,
        buffer=60000,
        total_budget_inr=1000000,
    )
    assert valid_budget.total_budget_inr == 1000000

    # Invalid sum (sum = 990,000 != 1,000,000)
    with pytest.raises(ValidationError) as exc:
        EventBudgetBreakdown(
            venue=250000,  # 10k short
            catering=300000,
            decor=110000,
            photo_video=90000,
            attire_beauty=100000,
            entertainment=50000,
            logistics=30000,
            buffer=60000,
            total_budget_inr=1000000,
        )
    assert "does not match the stated total budget" in str(exc.value)

    # Negative allocation rejected
    with pytest.raises(ValidationError):
        EventBudgetBreakdown(
            venue=-100,
            catering=300000,
            decor=110000,
            photo_video=90000,
            attire_beauty=100000,
            entertainment=50000,
            logistics=30000,
            buffer=60000,
            total_budget_inr=1000000,
        )


def test_timeline_run_sheet_validation() -> None:
    """Verify run-sheet validates time ordering."""
    # Valid run-sheet item
    item = RunSheetItem(
        start_time="09:00",
        end_time="10:30",
        activity_name="Welcome Drink & Seating",
        responsible_party="Catering Lead",
        description="Serve tender coconut water and filter coffee to arriving guests",
    )
    assert item.start_time == "09:00"

    # End before start rejected
    with pytest.raises(ValidationError) as exc:
        RunSheetItem(
            start_time="14:00",
            end_time="12:00",
            activity_name="Invalid Sequence",
            responsible_party="MC",
            description="Testing inverted sequence",
        )
    assert "cannot be earlier than start time" in str(exc.value)


def test_pre_mortem_risk_validation() -> None:
    """Verify probability must be between 0.0 and 1.0."""
    risk = PreMortemRisk(
        risk_description="Unseasonal monsoon shower during lawn ceremony",
        probability=0.35,
        cost_impact_pct_of_budget=3.0,
        mitigation="Keep waterproof indoor hall on 1-hour standby notice",
    )
    assert risk.probability == 0.35

    with pytest.raises(ValidationError):
        PreMortemRisk(
            risk_description="Bad probability",
            probability=1.5,
            cost_impact_pct_of_budget=2.0,
            mitigation="None",
        )


def test_family_council_response_validation() -> None:
    """Verify complete 4-persona family council review and compromise."""
    council = FamilyCouncilResponse(
        budget_holder=PersonaReview(
            persona_name="Pragmatic Treasurer",
            concerns=["Buffet dessert counter might cause catering overrun"],
            suggested_changes=["Cap desserts to 3 items and negotiate flat rate"],
        ),
        elder_relative=PersonaReview(
            persona_name="Traditional Elder",
            concerns=["Need dedicated seated area with ramp access for senior family members"],
            suggested_changes=["Reserve front 4 rows and add acoustic sound dampening"],
        ),
        picky_friend=PersonaReview(
            persona_name="Experience Architect",
            concerns=["Stage backdrop looks standard and repetitive in photos"],
            suggested_changes=["Add custom warm LED neon sign and botanical greenery wall"],
        ),
        parent_with_kids=PersonaReview(
            persona_name="Family Host with Kids",
            concerns=["Children will get restless during long 2-hour speeches"],
            suggested_changes=["Include a kid-friendly mocktail booth and activity table"],
        ),
        compromise=FamilyCouncilCompromise(
            agreed_plan=(
                "Adopted front row reserved seating, added photo wall within buffer, "
                "and trimmed dessert counter"
            ),
            remaining_objections={"budget_holder": ["Will monitor extra lighting costs"]},
        ),
    )
    assert council.budget_holder.persona_name == "Pragmatic Treasurer"
    assert len(council.elder_relative.concerns) >= 1


def test_crisis_recovery_plan_and_whatsapp_draft() -> None:
    """Verify crisis recovery plan with plain-text copyable WhatsApp drafts."""
    draft = WhatsAppMessageDraft(
        target=MessageTarget.GUESTS,
        recipient_label="Broadcast: All Guests",
        message_text=(
            "Namaste! Due to brief showers, our evening reception has moved to the "
            "indoor Grand Ballroom at the same venue. Looking forward to welcoming you!"
        ),
    )
    plan = CrisisRecoveryPlan(
        detected_crisis_type="rain",
        severity=2,
        timeline_changes=["Shift program start by 20 minutes"],
        explanation="Outdoor lawn saturated; indoor hall fully air-conditioned and ready",
        recommended_actions=["Direct valet drivers to Gate 2 entrance"],
        whatsapp_message_drafts=[draft],
    )
    assert plan.severity == 2
    assert plan.whatsapp_message_drafts[0].target == MessageTarget.GUESTS


def test_standard_error_response_serialization() -> None:
    """Verify StandardErrorResponse structure matches {'error': {'code': ..., 'message': ...}}."""
    err = StandardErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Request input validation failed",
            details=[{"field": "total_budget_inr", "reason": "Below minimum"}],
        )
    )
    data = err.model_dump()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Request input validation failed"
    assert isinstance(data["error"]["details"], list)


def test_supported_language_codes() -> None:
    """Verify all 8 supported Indian language codes in EventPlanRequest."""
    for lang in LanguageCode:
        req = EventPlanRequest(
            event_type=EventType.WEDDING,
            guest_count=100,
            total_budget_inr=500_000,
            city_tier=CityTier.METRO,
            city="Hyderabad",
            language=lang,
        )
        assert req.language == lang


def test_family_council_missing_personas_rejected() -> None:
    """Verify FamilyCouncilResponse fails validation if any of the 4 personas is missing."""
    p = PersonaReview(
        persona_name="Reviewer",
        concerns=["Concern 1"],
        suggested_changes=["Change 1"],
    )
    comp = FamilyCouncilCompromise(agreed_plan="Consensus plan")

    with pytest.raises(ValidationError):
        FamilyCouncilResponse(  # type: ignore[call-arg]
            budget_holder=p,
            elder_relative=p,
            # missing picky_friend and parent_with_kids
            compromise=comp,
        )


def test_planning_milestone_validation() -> None:
    """Verify PlanningMilestone rejects negative weeks_before or empty milestone_name."""
    milestone = PlanningMilestone(
        milestone_name="Book Wedding Venue",
        phase=EventPhase.PLANNING,
        weeks_before=20,
        description="Finalize contract and pay booking advance",
    )
    assert milestone.weeks_before == 20

    with pytest.raises(ValidationError):
        PlanningMilestone(
            milestone_name="",  # Empty title rejected
            phase=EventPhase.PLANNING,
            description="Empty milestone",
        )

    with pytest.raises(ValidationError):
        PlanningMilestone(
            milestone_name="Bad Milestone",
            phase=EventPhase.PLANNING,
            weeks_before=-5,  # Negative weeks rejected
            description="Invalid timeline",
        )


def test_vendor_plan_item_validation() -> None:
    """Verify VendorPlanItem rejects negative lead time or out-of-bounds advance percentage."""
    item = VendorPlanItem(
        vendor_type="caterer",
        lead_time_weeks=12,
        typical_advance_pct=25.0,
        allocated_budget_inr=300_000,
    )
    assert item.lead_time_weeks == 12

    with pytest.raises(ValidationError):
        VendorPlanItem(
            vendor_type="caterer",
            lead_time_weeks=-1,  # Negative lead time
            typical_advance_pct=25.0,
        )

    with pytest.raises(ValidationError):
        VendorPlanItem(
            vendor_type="caterer",
            lead_time_weeks=10,
            typical_advance_pct=125.0,  # Over 100% advance
        )


def test_personalized_idea_validation() -> None:
    """Verify PersonalizedIdea rejects negative estimated cost or empty title."""
    idea = PersonalizedIdea(
        title="Live Filter Coffee Counter",
        explanation="Traditional South Indian hospitality experience",
        implementation_details="Source local artisanal roaster from Chikmagalur",
        estimated_cost_inr=15_000,
    )
    assert idea.estimated_cost_inr == 15_000

    with pytest.raises(ValidationError):
        PersonalizedIdea(
            title="",  # Empty title
            explanation="Invalid",
            implementation_details="Invalid",
        )

    with pytest.raises(ValidationError):
        PersonalizedIdea(
            title="Invalid Idea",
            explanation="Invalid",
            implementation_details="Invalid",
            estimated_cost_inr=-5_000,  # Negative cost
        )


def test_crisis_recovery_plan_invalid_severity() -> None:
    """Verify CrisisRecoveryPlan rejects severity < 1 or > 3."""
    with pytest.raises(ValidationError):
        CrisisRecoveryPlan(
            detected_crisis_type="rain",
            severity=0,  # Below 1
            explanation="Invalid severity",
            recommended_actions=["Move indoors"],
        )

    with pytest.raises(ValidationError):
        CrisisRecoveryPlan(
            detected_crisis_type="rain",
            severity=4,  # Above 3
            explanation="Invalid severity",
            recommended_actions=["Move indoors"],
        )
