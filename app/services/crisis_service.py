"""Crisis recovery service for PlanProof AI.

Handles:
- Deterministic crisis scenario matching against validated crisis_scenarios.csv.
- Fallback recovery generation when no dataset scenario matches.
- Safety-first immediate triage and emergency escalation guidance.
- Deterministic budget impact arithmetic and contingency buffer comparison.
- Milestone and vendor checklist cross-referencing without automated mutations.
- Stakeholder communication draft generation with clear placeholder tokens.
- Optional Gemini AI orchestration enrichment.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import AIMode
from app.data_loader import DatasetRepository
from app.schemas import (
    AIResultEnvelope,
    AIResultSource,
    AIResultStatus,
    AITask,
    CityTier,
    CrisisActionItem,
    CrisisBudgetImpact,
    CrisisCommunicationDraft,
    CrisisEvaluationRequest,
    CrisisScenario,
    CrisisTypeMetadata,
    EventCrisisRecoveryResponse,
    EventPhase,
    EventProfile,
    EventType,
    MatchedCrisisScenario,
    MessageTarget,
)
from app.services.ai_orchestrator import AIOrchestrator
from app.services.timeline import generate_event_timeline_schedule

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. Standard Supported Crisis Types
# ==============================================================================

SUPPORTED_CRISIS_TYPES: list[CrisisTypeMetadata] = [
    CrisisTypeMetadata(
        crisis_type="rain",
        title="Rain & Severe Weather",
        affected_area="weather",
        typical_severity=3,
        description="Unseasonal rain, high winds, or storm impacting open lawns or outdoor setups.",
    ),
    CrisisTypeMetadata(
        crisis_type="power_cut",
        title="Power Outage & Grid Failure",
        affected_area="power",
        typical_severity=3,
        description="Electrical grid failure impacting lighting, sound systems, HVAC, or stage feeds.",
    ),
    CrisisTypeMetadata(
        crisis_type="caterer_cancel",
        title="Caterer Cancellation",
        affected_area="catering",
        typical_severity=3,
        description="Primary food & beverage vendor cancels or withdraws shortly before or during the event.",
    ),
    CrisisTypeMetadata(
        crisis_type="caterer_late",
        title="Caterer Delay / Late Arrival",
        affected_area="catering",
        typical_severity=2,
        description="Food preparation, delivery, or buffet setup delayed past scheduled run-sheet times.",
    ),
    CrisisTypeMetadata(
        crisis_type="venue_double_booked",
        title="Venue Double Booking / Dispute",
        affected_area="venue",
        typical_severity=3,
        description="Hall overlap, slot dispute, or venue management scheduling conflict.",
    ),
    CrisisTypeMetadata(
        crisis_type="photographer_noshow",
        title="Photographer No-Show",
        affected_area="photography",
        typical_severity=3,
        description="Contracted photo or video crew fails to report to the venue for primary ceremonies.",
    ),
    CrisisTypeMetadata(
        crisis_type="sound_failure",
        title="Sound System / AV Failure",
        affected_area="sound",
        typical_severity=2,
        description="Audio console, microphone, speaker, or amplifier failure during ceremonies or entertainment.",
    ),
    CrisisTypeMetadata(
        crisis_type="decorator_delay",
        title="Decorator / Mandap Delay",
        affected_area="decor",
        typical_severity=2,
        description="Stage rigging, floral installations, or mandap setup incomplete before guest arrival.",
    ),
    CrisisTypeMetadata(
        crisis_type="guest_surge",
        title="Unexpected Guest Surge",
        affected_area="guest_attendance",
        typical_severity=2,
        description="Attendee turnout exceeds confirmed seating, catering, and venue capacity limits.",
    ),
    CrisisTypeMetadata(
        crisis_type="guest_dropout",
        title="Unexpected Guest Dropout",
        affected_area="guest_attendance",
        typical_severity=1,
        description="Significant drop in attendance causing unused catering plates and excess hall space.",
    ),
    CrisisTypeMetadata(
        crisis_type="budget_overrun",
        title="Budget Overrun",
        affected_area="budget",
        typical_severity=2,
        description="Vendor cost escalations, extra services, or unexpected fees exceeding total budget.",
    ),
    CrisisTypeMetadata(
        crisis_type="key_guest_cancel",
        title="Key VIP / Chief Guest Cancellation",
        affected_area="hospitality",
        typical_severity=1,
        description="Chief guest, dignitary, or key family elder unable to attend scheduled ceremony.",
    ),
]

CRISIS_TYPE_MAP: dict[str, CrisisTypeMetadata] = {
    c.crisis_type: c for c in SUPPORTED_CRISIS_TYPES
}

CRISIS_TYPE_ALIASES: dict[str, str] = {
    "weather": "rain",
    "monsoon": "rain",
    "storm": "rain",
    "power": "power_cut",
    "electricity": "power_cut",
    "blackout": "power_cut",
    "caterer": "caterer_late",
    "catering": "caterer_late",
    "food": "caterer_late",
    "venue": "venue_double_booked",
    "double_booking": "venue_double_booked",
    "hall_conflict": "venue_double_booked",
    "photo": "photographer_noshow",
    "photography": "photographer_noshow",
    "camera": "photographer_noshow",
    "sound": "sound_failure",
    "audio": "sound_failure",
    "mic": "sound_failure",
    "av": "sound_failure",
    "decor": "decorator_delay",
    "decoration": "decorator_delay",
    "mandap": "decorator_delay",
    "flowers": "decorator_delay",
    "surge": "guest_surge",
    "crowd": "guest_surge",
    "overcrowding": "guest_surge",
    "dropout": "guest_dropout",
    "low_attendance": "guest_dropout",
    "overrun": "budget_overrun",
    "overspend": "budget_overrun",
    "cost": "budget_overrun",
    "vip": "key_guest_cancel",
    "speaker": "key_guest_cancel",
}


def normalize_crisis_type(raw_type: str) -> str:
    """Normalize user input to a canonical crisis type."""
    cleaned = raw_type.strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned in CRISIS_TYPE_MAP:
        return cleaned
    return CRISIS_TYPE_ALIASES.get(cleaned, cleaned)


# ==============================================================================
# 2. Deterministic Scenario Matching
# ==============================================================================


def match_crisis_scenario(
    scenarios: list[CrisisScenario],
    crisis_type: str,
    event_type: EventType,
    severity: int,
    guest_count: int,
    phase: EventPhase | None = None,
) -> MatchedCrisisScenario:
    """Match a crisis scenario from the validated CSV dataset using deterministic scoring.

    If no suitable match is found in the dataset, returns a clearly labeled fallback.
    Never invents a dataset record or claims a synthetic fixture originated in the CSV.
    """
    canonical_type = normalize_crisis_type(crisis_type)

    # 1. Filter candidates strictly by canonical crisis_type
    candidates = [s for s in scenarios if s.crisis_type == canonical_type]

    if not candidates:
        # Fallback when crisis dataset has no records for this type
        logger.warning(
            "No CSV scenarios matched for crisis_type='%s'. Generating labeled fallback.",
            canonical_type,
        )
        meta = CRISIS_TYPE_MAP.get(
            canonical_type,
            CrisisTypeMetadata(
                crisis_type=canonical_type,
                title=canonical_type.replace("_", " ").title(),
                affected_area="general",
                typical_severity=severity,
                description=f"Operational disruption related to {canonical_type}.",
            ),
        )
        return MatchedCrisisScenario(
            scenario_id="FALLBACK-NON-CSV",
            is_dataset_match=False,
            crisis_type=canonical_type,
            severity=severity,
            event_type=event_type,
            phase=phase or EventPhase.EVENT_DAY,
            description=f"{meta.title} encountered during {event_type.value.replace('_', ' ')}.",
            recommended_fix="Convene key organizers, activate on-site backup resources, and triage priority tasks.",
            cost_impact_pct_of_budget=4.0 if severity == 2 else (8.0 if severity == 3 else 1.5),
            message_target=MessageTarget.VENDOR if "vendor" in canonical_type else MessageTarget.FAMILY,
            synthetic=True,
        )

    # 2. Score candidate matches deterministically
    best_candidate: CrisisScenario | None = None
    best_score = -float("inf")

    target_phase = phase or EventPhase.EVENT_DAY

    for cand in candidates:
        score = 0.0
        # Exact event type match
        if cand.event_type == event_type:
            score += 100.0
        # Exact severity match
        if cand.severity == severity:
            score += 50.0
        # Exact phase match
        if cand.phase == target_phase:
            score += 20.0
        # Guest count proximity tiebreaker
        guest_diff = abs(cand.guest_count - guest_count)
        score -= guest_diff / 50.0

        if score > best_score:
            best_score = score
            best_candidate = cand

    matched = best_candidate or candidates[0]

    return MatchedCrisisScenario(
        scenario_id=matched.id,
        is_dataset_match=True,
        crisis_type=matched.crisis_type,
        severity=matched.severity,
        event_type=matched.event_type,
        phase=matched.phase,
        description=matched.description,
        recommended_fix=matched.recommended_fix,
        cost_impact_pct_of_budget=matched.cost_impact_pct_of_budget,
        message_target=matched.message_target,
        synthetic=matched.synthetic,
    )


# ==============================================================================
# 3. Budget Impact Calculation
# ==============================================================================


AFFECTED_BUDGET_CATEGORIES: dict[str, list[str]] = {
    "caterer_cancel": ["catering", "contingency"],
    "caterer_late": ["catering", "contingency"],
    "decorator_delay": ["decor", "contingency"],
    "photographer_noshow": ["photo_video", "contingency"],
    "power_cut": ["production", "logistics", "contingency"],
    "sound_failure": ["production", "entertainment", "contingency"],
    "rain": ["venue", "decor", "production", "contingency"],
    "venue_double_booked": ["venue", "contingency"],
    "guest_surge": ["catering", "venue", "contingency"],
    "guest_dropout": ["catering", "venue"],
    "budget_overrun": ["catering", "decor", "entertainment", "attire_beauty"],
    "key_guest_cancel": ["miscellaneous", "hospitality"],
}


def calculate_crisis_budget_impact(
    profile: EventProfile,
    matched_scenario: MatchedCrisisScenario,
    crisis_type: str,
) -> CrisisBudgetImpact:
    """Calculate authoritative arithmetic budget impact without altering event records."""
    canonical_type = normalize_crisis_type(crisis_type)
    pct = matched_scenario.cost_impact_pct_of_budget
    total_budget = profile.total_budget_inr

    # Estimated impact in INR rounded to nearest rupee
    estimated_impact = round((pct / 100.0) * total_budget)

    # Existing contingency buffer from profile budget if available
    existing_buffer = (
        profile.budget.buffer
        if profile.budget and profile.budget.buffer is not None
        else round(total_budget * 0.05)
    )

    affected_cats = AFFECTED_BUDGET_CATEGORIES.get(canonical_type, ["contingency"])

    if estimated_impact <= 0:
        buffer_sufficient = True
        advice = (
            f"Headcount savings or non-expenditure adjustment detected ({pct:.1f}% impact). "
            f"Estimated budget adjustment is ₹{abs(estimated_impact):,} in favor of savings. "
            "Protect negotiated minimum guarantees with suppliers."
        )
    elif existing_buffer >= estimated_impact:
        buffer_sufficient = True
        remaining = existing_buffer - estimated_impact
        advice = (
            f"The existing emergency buffer of ₹{existing_buffer:,} is sufficient to absorb "
            f"the estimated crisis impact of ₹{estimated_impact:,} ({pct:.1f}% of total budget). "
            f"Estimated remaining contingency cushion: ₹{remaining:,}. No primary budget cuts required."
        )
    else:
        buffer_sufficient = False
        deficit = estimated_impact - existing_buffer
        top_cats = ", ".join(c.replace("_", " ").title() for c in affected_cats[:2])
        advice = (
            f"The estimated financial impact of ₹{estimated_impact:,} ({pct:.1f}% of budget) "
            f"exceeds the contingency buffer of ₹{existing_buffer:,} by ₹{deficit:,}. "
            f"Recommend rebalancing flexible discretionary allocations in {top_cats} "
            "to absorb the variance without reducing essential guest hospitality."
        )

    return CrisisBudgetImpact(
        cost_impact_pct=pct,
        estimated_rupee_impact=estimated_impact,
        affected_categories=affected_cats,
        existing_buffer_inr=existing_buffer,
        buffer_sufficient=buffer_sufficient,
        advice=advice,
    )


# ==============================================================================
# 4. Action Items & Safety Prioritization
# ==============================================================================


def generate_crisis_action_items(
    crisis_type: str,
    severity: int,
    profile: EventProfile,
    matched_scenario: MatchedCrisisScenario,
    affected_area: str,
    user_description: str | None = None,
) -> tuple[list[CrisisActionItem], list[CrisisActionItem], list[str], str, list[str]]:
    """Generate prioritized immediate actions, next steps, alternatives, escalation, and warnings."""
    canonical_type = normalize_crisis_type(crisis_type)
    immediate: list[CrisisActionItem] = []
    next_steps: list[CrisisActionItem] = []
    alternatives: list[str] = []
    warnings: list[str] = []

    # 1. SAFETY-FIRST: Physical or electrical hazards take absolute priority 1
    if canonical_type in ("power_cut", "rain") or severity == 3:
        if canonical_type == "rain":
            immediate.append(
                CrisisActionItem(
                    priority=1,
                    category="immediate_safety",
                    title="Immediate Electrical Isolation & Guest Cover",
                    action=(
                        "Instruct facility electrician to immediately isolate and shut off outdoor high-voltage "
                        "lighting, ground amplifiers, and stage cable junctions to prevent electrocution. "
                        "Direct all guests into covered walkways and indoor halls. If structural damage or "
                        "injuries occur, immediately dial National Emergency (112) or Ambulance (108)."
                    ),
                    responsible_party="On-Site Safety Officer & Electrician",
                    timeframe="Immediate (0-5 mins)",
                )
            )
        elif canonical_type == "power_cut":
            immediate.append(
                CrisisActionItem(
                    priority=1,
                    category="immediate_safety",
                    title="Emergency Stairwell Lighting & Elevator Check",
                    action=(
                        "Activate auxiliary battery lighting along all stairwells, exit corridors, and restrooms. "
                        "Station marshals to inspect elevators immediately to ensure no guests are trapped. "
                        "Verify that venue automatic diesel generator transfer switch (ATS) has triggered."
                    ),
                    responsible_party="Facility Duty Manager & Floor Marshals",
                    timeframe="Immediate (0-5 mins)",
                )
            )
        else:
            immediate.append(
                CrisisActionItem(
                    priority=1,
                    category="immediate_safety",
                    title="Guest Safety & Area Triage",
                    action=(
                        "Verify physical safety across the affected venue zone. Establish a calm, lighted perimeter "
                        "and ensure emergency exits remain unobstructed. If medical or fire assistance is needed, "
                        "contact local emergency authorities immediately (112 / 108 / 101)."
                    ),
                    responsible_party="Lead Event Host & Floor Coordinator",
                    timeframe="Immediate (0-10 mins)",
                )
            )

    # 2. Operational Continuity Immediate Actions
    if canonical_type == "caterer_cancel":
        immediate.append(
            CrisisActionItem(
                priority=1,
                category="operational_continuity",
                title="Activate Backup Kitchen & In-House Venue Catering",
                action=(
                    "Engage the venue's in-house kitchen and activate the pre-identified emergency backup caterer. "
                    "Request immediate dispatch of fast-prep hot live stations (biryani, roti/dal, chaat, sweets)."
                ),
                responsible_party="Catering Coordinator & Host",
                timeframe="Within 15 mins",
            )
        )
        immediate.append(
            CrisisActionItem(
                priority=2,
                category="guest_hospitality",
                title="Extend Welcome Refreshments & Mocktails",
                action=(
                    "Order the beverage and snack counters to continuously circulate appetizers, cold drinks, "
                    "and fresh fruit skewers to keep guests comfortable and unaware of kitchen delays."
                ),
                responsible_party="Banquet Captain",
                timeframe="Immediate (0-15 mins)",
            )
        )
        next_steps.append(
            CrisisActionItem(
                priority=2,
                category="contract_management",
                title="Document Non-Performance & Secure Booking Deposit",
                action=(
                    "Document the contractor's written cancellation for contractual dispute resolution. "
                    "Reallocate available payment funds to the emergency supplier."
                ),
                responsible_party="Financial Host / Legal Lead",
                timeframe="Next 2-4 hours",
            )
        )
        alternatives.extend(
            [
                "Partner with 2 nearby reputable restaurants for rapid family-style bulk delivery.",
                "Streamline menu to high-speed live counter offerings rather than a 40-dish spread.",
                "Deploy food truck or gourmet street-food live stations for energetic festive vibe.",
            ]
        )

    elif canonical_type == "caterer_late":
        immediate.append(
            CrisisActionItem(
                priority=1,
                category="operational_continuity",
                title="Verify In-Transit ETA & Stage Appetizers First",
                action=(
                    "Call the vendor dispatch manager to get real-time GPS location and arrival window. "
                    "Instruct team to unbox and serve appetizers, welcome drinks, and salads immediately upon arrival."
                ),
                responsible_party="Catering Lead Coordinator",
                timeframe="Immediate (0-15 mins)",
            )
        )
        next_steps.append(
            CrisisActionItem(
                priority=2,
                category="timeline_management",
                title="Shift Run-Sheet Dinner Window by 30-45 Minutes",
                action=(
                    "Extend evening musical performances, photo sessions, or family felicitations "
                    "to naturally bridge the gap before the main dinner buffet opens."
                ),
                responsible_party="Master of Ceremonies (MC) & DJ",
                timeframe="Within 30 mins",
            )
        )
        alternatives.extend(
            [
                "Open dessert and fruit counters early alongside tea/coffee service.",
                "Serve finger food directly to tables during stage rituals.",
            ]
        )

    elif canonical_type == "rain":
        immediate.append(
            CrisisActionItem(
                priority=1,
                category="operational_continuity",
                title="Execute Indoor Hall Transition Protocol",
                action=(
                    "Shift ritual mandap/stage and primary seating from lawn to the designated indoor banquet hall. "
                    "Roll out non-slip rubber runners across entrance corridors."
                ),
                responsible_party="Venue Banquet Operations Lead",
                timeframe="Within 20 mins",
            )
        )
        next_steps.append(
            CrisisActionItem(
                priority=2,
                category="decor_logistics",
                title="Relocate Weatherproof Floral Displays",
                action=(
                    "Move key floral centerpieces and photo backdrops inside to frame the new indoor stage. "
                    "Cover outdoor sound consoles with heavy-duty waterproof tarpaulins."
                ),
                responsible_party="Decor Supervisor",
                timeframe="Within 45 mins",
            )
        )
        alternatives.extend(
            [
                "Erect pre-contracted German waterproof hangar canopy over stage area.",
                "Condense ceremony to intimate indoor space and host reception buffet in covered courtyard.",
                "Provide umbrellas and valet covered drop-off at entrance gates.",
            ]
        )

    elif canonical_type == "power_cut":
        immediate.append(
            CrisisActionItem(
                priority=1,
                category="operational_continuity",
                title="Switch Main Audio & Stage Lighting to Silent Generator",
                action=(
                    "Connect stage lighting, DJ/audio console, and mandap illumination to the dedicated silent "
                    "backup diesel generator. Test voltage before ramping up sound levels."
                ),
                responsible_party="Sound Engineer & Venue Electrician",
                timeframe="Within 10 mins",
            )
        )
        next_steps.append(
            CrisisActionItem(
                priority=2,
                category="ceremony_flow",
                title="Maintain Program Continuity with Daylight / Acoustic Segment",
                action=(
                    "If electrical switch takes longer than 15 minutes, transition to acoustic instrumental music, "
                    "unplugged folk singing, or daylight photography segments."
                ),
                responsible_party="Event MC & Artists",
                timeframe="Within 20 mins",
            )
        )
        alternatives.extend(
            [
                "Call local equipment rental provider for immediate dispatch of portable 25 kVA generator.",
                "Deploy decorative battery-powered fairy lights and brass candelabras for ambient warmth.",
            ]
        )

    elif canonical_type == "photographer_noshow":
        immediate.append(
            CrisisActionItem(
                priority=1,
                category="operational_continuity",
                title="Dispatch On-Call Backup Photographer",
                action=(
                    "Contact the secondary studio photographer on emergency hold and confirm immediate dispatch. "
                    "Assign a skilled family member or second shooter with 4K gear to capture vital rituals right now."
                ),
                responsible_party="Media & Communications Coordinator",
                timeframe="Immediate (0-15 mins)",
            )
        )
        next_steps.append(
            CrisisActionItem(
                priority=2,
                category="reception_flow",
                title="Reschedule Formal Portraits to Reception Slot",
                action=(
                    "Postpone elaborate stage portraits to the evening dinner reception window when the replacement "
                    "crew is fully stationed and calibrated."
                ),
                responsible_party="Stage Host & MC",
                timeframe="Within 1 hour",
            )
        )
        alternatives.extend(
            [
                "Commission reputable photo studio located within a 5 km radius of venue.",
                "Set up an instant Polaroid / guest photo booth station to maintain interactive visual memories.",
                "Schedule a complimentary post-event portrait session for couple / family.",
            ]
        )

    elif canonical_type == "venue_double_booked":
        immediate.append(
            CrisisActionItem(
                priority=1,
                category="operational_continuity",
                title="Escalate with General Manager with Signed Contract",
                action=(
                    "Meet venue General Manager immediately. Present stamped booking receipt and advance transaction "
                    "records. Insist on immediate allocation of the premium ballroom or adjacent banquet tier."
                ),
                responsible_party="Primary Contract Signatory & Legal Host",
                timeframe="Immediate (0-15 mins)",
            )
        )
        next_steps.append(
            CrisisActionItem(
                priority=2,
                category="guest_management",
                title="Deploy Welcome Ushers at Property Entrance",
                action=(
                    "Station 3 ushers with branded welcome signage at driveway gates to guide arriving guests "
                    "directly to the confirmed hall without confusion."
                ),
                responsible_party="Hospitality Reception Team",
                timeframe="Immediate (0-20 mins)",
            )
        )
        alternatives.extend(
            [
                "Accept venue's upgraded rooftop or terrace hall with complimentary decor enhancements.",
                "Activate pre-held sister property hall belonging to the same hospitality group.",
            ]
        )

    else:  # General disruptions (sound, decor, surge, dropout, overrun, vip)
        immediate.append(
            CrisisActionItem(
                priority=1,
                category="operational_continuity",
                title="Assess Disruption & Coordinate Lead Specialist",
                action=(
                    f"Initiate on-site remediation for {canonical_type.replace('_', ' ')}. "
                    f"Guideline from verified recovery baseline: {matched_scenario.recommended_fix}."
                ),
                responsible_party="Lead Event Host & Category Vendor Lead",
                timeframe="Within 15 mins",
            )
        )
        next_steps.append(
            CrisisActionItem(
                priority=2,
                category="timeline_management",
                title="Realign Schedule & Manage Guest Touchpoints",
                action=(
                    "Adjust run-sheet checkpoints and ensure hospitality teams keep attendee comfort seamless."
                ),
                responsible_party="Event MC & Floor Captain",
                timeframe="Within 45 mins",
            )
        )
        alternatives.extend(
            [
                "Deploy backup supplier inventory currently on standby.",
                "Rebalance run-sheet milestones to preserve core ceremonial highlights.",
            ]
        )

    # Escalation Guidance
    escalation_guidance = (
        "1. For life safety, fire, or severe medical emergencies, dial 112 (National Emergency), "
        "108 (Ambulance), or 101 (Fire) immediately without delay.\n"
        "2. Direct all vendor inquiries and operational updates through the Lead Event Host. "
        "Do not allow uncoordinated announcements to guests.\n"
        "3. Venue On-Site Duty Desk: Report to the Banquet Manager Office on the Ground Floor."
    )

    # Operational Warnings & Assumptions
    warnings.append(
        "Deterministic recovery plan is advisory. PlanProof AI does not execute real bookings, "
        "cancel vendor agreements, or debit accounts automatically."
    )
    if not profile.event_date:
        warnings.append(
            "Event date is unscheduled. Timeline adjustments assume an active event-day timeline."
        )
    if not profile.budget:
        warnings.append(
            "Event budget breakdown is unallocated. Cost impact reflects percentage of total budget."
        )

    return immediate, next_steps, alternatives, escalation_guidance, warnings


# ==============================================================================
# 5. Stakeholder Communication Drafts
# ==============================================================================


def generate_crisis_communication_drafts(
    crisis_type: str,
    severity: int,
    profile: EventProfile,
    source: str = "deterministic",
) -> list[CrisisCommunicationDraft]:
    """Generate concise, polite, copyable communication drafts for multiple stakeholders.

    Uses standard bracketed placeholders for missing details.
    Does NOT claim recipients have been contacted or real bookings executed.
    """
    canonical_type = normalize_crisis_type(crisis_type)
    event_title = profile.event_name or f"{profile.event_type.value.replace('_', ' ').title()} Celebration"
    event_date_str = str(profile.event_date) if profile.event_date else "[Event Scheduled Date]"
    venue_name = profile.city or "[Event Venue Name]"

    drafts: list[CrisisCommunicationDraft] = []

    # 1. Vendor Escalation Draft
    vendor_text = (
        f"URGENT OPERATIONAL NOTICE — {event_title}\n"
        f"Event Date: {event_date_str} | Location: {venue_name}\n\n"
        f"Dear [Vendor Contact Name],\n"
        f"We are issuing an urgent operational notification regarding our celebration: "
        f"we have encountered a '{canonical_type.replace('_', ' ').title()}' disruption (Severity Level {severity}).\n\n"
        f"Required Immediate Action: [Specific action required, e.g. dispatch lead technician / release standby inventory / confirm arrival ETA].\n"
        f"Please contact our primary event coordinator immediately upon reading this message.\n\n"
        f"Coordinator: [Host Name] | Phone: [Host Phone Number]\n"
        f"Reporting Station: [Venue Help Desk / Main Entrance]\n\n"
        f"Please reply with your immediate status and estimated response time. Thank you."
    )
    drafts.append(
        CrisisCommunicationDraft(
            recipient_role="vendor",
            recipient_label="Primary Vendor / Backup Service Contractor",
            subject_or_header=f"URGENT: Operational Notice — {event_title}",
            message_text=vendor_text,
            source=source,
            placeholders=[
                "[Vendor Contact Name]",
                "[Specific action required, e.g. dispatch lead technician / release standby inventory / confirm arrival ETA]",
                "[Host Name]",
                "[Host Phone Number]",
                "[Venue Help Desk / Main Entrance]",
            ],
        )
    )

    # 2. Guest Comfort & Update Draft
    guest_text = (
        f"Dear Family and Friends,\n\n"
        f"Thank you for being part of our {event_title}! To ensure everyone's seamless comfort and enjoyment, "
        f"our schedule has been gently updated:\n\n"
        f"• Program Update: [e.g. Celebrations have transitioned into the Grand Indoor Ballroom / Evening buffet service opens at 8:30 PM].\n"
        f"• Welcome Refreshments: Roving appetizers and beverages are active in the [Hospitality Lounge / Courtyard].\n\n"
        f"Our team at the [Reception Welcome Desk] is here to assist you with any questions. "
        f"We look forward to an unforgettable celebration with all of you!\n\n"
        f"With warm regards,\n"
        f"[Host Family Name / Event Team]"
    )
    drafts.append(
        CrisisCommunicationDraft(
            recipient_role="guests",
            recipient_label="All Attending Guests (Broadcast / WhatsApp)",
            subject_or_header=f"Celebration Update — {event_title}",
            message_text=guest_text,
            source=source,
            placeholders=[
                "[e.g. Celebrations have transitioned into the Grand Indoor Ballroom / Evening buffet service opens at 8:30 PM]",
                "[Hospitality Lounge / Courtyard]",
                "[Reception Welcome Desk]",
                "[Host Family Name / Event Team]",
            ],
        )
    )

    # 3. Core Family & Host Committee Draft
    family_text = (
        f"CORE FAMILY COORDINATION ALERT — PLEASE READ\n\n"
        f"Quick update for the organizing committee: We are currently addressing a {canonical_type.replace('_', ' ')} situation.\n"
        f"Our backup contingency protocol is active and operational steps are underway.\n\n"
        f"How family members can assist right now:\n"
        f"1. Stay calm and welcoming near [Hospitality Area / Guest Seating]. Keep guest conversations cheerful.\n"
        f"2. Please direct any supplier questions exclusively to [Designated Lead Coordinator].\n"
        f"3. Do not make public announcements or negotiate pricing with vendors individually.\n\n"
        f"Lead Point of Contact: [Lead Family Coordinator Name] ([Phone Number])\n"
        f"Let's stay united and enjoy this beautiful celebration!"
    )
    drafts.append(
        CrisisCommunicationDraft(
            recipient_role="family",
            recipient_label="Core Family Committee & Key Organizers",
            subject_or_header="Family Coordination — Alignment & Next Steps",
            message_text=family_text,
            source=source,
            placeholders=[
                "[Hospitality Area / Guest Seating]",
                "[Designated Lead Coordinator]",
                "[Lead Family Coordinator Name]",
                "[Phone Number]",
            ],
        )
    )

    # 4. Event Operations Crew & On-Site Managers Draft
    crew_text = (
        f"CREW OPERATIONAL DISPATCH — SEVERITY {severity}\n"
        f"Event: {event_title} | Time: [Current Time]\n"
        f"Disruption Type: {canonical_type.replace('_', ' ').upper()}\n\n"
        f"Operational Directives:\n"
        f"1. Safety: Verify all guest contact points in [Sector / Hall Area] remain safe and clear.\n"
        f"2. Execution: [Immediate Operational Task, e.g. Reconfigure indoor sound / Release standby food warmers].\n"
        f"3. Comms: Report task completion to [Operations Control Desk / Head Usher] via Radio Channel [Channel #] or WhatsApp.\n\n"
        f"Floor Captain: [Captain Name] ([Captain Phone])"
    )
    drafts.append(
        CrisisCommunicationDraft(
            recipient_role="organizers",
            recipient_label="Event Floor Managers & Technical Crew",
            subject_or_header="Operations Dispatch — Priority Response",
            message_text=crew_text,
            source=source,
            placeholders=[
                "[Current Time]",
                "[Sector / Hall Area]",
                "[Immediate Operational Task, e.g. Reconfigure indoor sound / Release standby food warmers]",
                "[Operations Control Desk / Head Usher]",
                "[Channel #]",
                "[Captain Name]",
                "[Captain Phone]",
            ],
        )
    )

    return drafts


# ==============================================================================
# 6. Timeline and Vendor Checklist Cross-Referencing
# ==============================================================================


def find_relevant_milestone_and_vendor_ids(
    profile: EventProfile,
    crisis_type: str,
) -> tuple[list[str], list[str], list[str]]:
    """Identify relevant timeline milestones and vendor checklist tasks without mutating event records."""
    canonical_type = normalize_crisis_type(crisis_type)
    milestone_ids: list[str] = []
    vendor_ids: list[str] = []
    timeline_notes: list[str] = []

    # 1. Timeline Milestones
    schedule = generate_event_timeline_schedule(
        event_id=profile.event_id,
        event_type=profile.event_type,
        event_date=profile.event_date,
        milestone_statuses=profile.milestone_statuses,
    )
    for ms in schedule.milestones:
        ms_name_lower = ms.title.lower()
        if (
            ("cater" in ms_name_lower and "cater" in canonical_type)
            or ("venue" in ms_name_lower and ("venue" in canonical_type or "rain" in canonical_type))
            or ("decor" in ms_name_lower and "decor" in canonical_type)
            or ("photo" in ms_name_lower and "photo" in canonical_type)
            or ("sound" in ms_name_lower and ("sound" in canonical_type or "power" in canonical_type))
            or (("weather" in canonical_type or "rain" in canonical_type) and "venue" in ms_name_lower)
        ):
            milestone_ids.append(ms.milestone_id)
            timeline_notes.append(
                f"Milestone '{ms.title}' ({ms.milestone_id}) is directly affected; suggest reviewing target due date."
            )

    if not milestone_ids:
        from app.services.timeline import get_template_for_event_type
        template_items = get_template_for_event_type(profile.event_type)
        for t_item in template_items:
            t_name_lower = t_item.title.lower()
            if (
                ("cater" in t_name_lower and "cater" in canonical_type)
                or ("venue" in t_name_lower and ("venue" in canonical_type or "rain" in canonical_type))
                or ("decor" in t_name_lower and "decor" in canonical_type)
                or ("photo" in t_name_lower and "photo" in canonical_type)
                or ("sound" in t_name_lower and ("sound" in canonical_type or "power" in canonical_type))
            ):
                milestone_ids.append(t_item.milestone_id)
                timeline_notes.append(
                    f"Template milestone '{t_item.title}' ({t_item.milestone_id}) is directly affected."
                )

    # 2. Vendor Checklist Items
    for item in profile.vendor_checklist:
        cat_val = item.category.value if hasattr(item.category, "value") else str(item.category)
        cat_lower = cat_val.lower()
        title_lower = item.title.lower() if item.title else ""
        if (
            (cat_lower in ("catering", "food") and "cater" in canonical_type)
            or (cat_lower in ("venue_permissions", "venue") and ("venue" in canonical_type or "rain" in canonical_type))
            or (cat_lower == "decor" and "decor" in canonical_type)
            or (cat_lower in ("photo_video", "photography") and "photo" in canonical_type)
            or (cat_lower in ("sound", "production", "logistics") and ("sound" in canonical_type or "power" in canonical_type))
            or ("cater" in title_lower and "cater" in canonical_type)
            or ("hall" in title_lower and "venue" in canonical_type)
            or ("photo" in title_lower and "photo" in canonical_type)
        ):
            vendor_ids.append(item.id)

    if not timeline_notes:
        timeline_notes.append(
            f"Review run-sheet execution schedule to insert 20-30 minute buffer around {canonical_type.replace('_', ' ')}."
        )

    return milestone_ids[:5], vendor_ids[:5], timeline_notes


# ==============================================================================
# 7. Crisis Recovery Orchestration & Evaluation
# ==============================================================================


def build_crisis_recovery_prompt(
    profile: EventProfile,
    matched: MatchedCrisisScenario,
    baseline: EventCrisisRecoveryResponse,
) -> tuple[str, str]:
    """Build prompt and system instructions for optional Gemini AI enrichment."""
    system_instruction = (
        "You are the Crisis Recovery Specialist for PlanProof AI. "
        "Enrich and polish the provided crisis response plan for Indian celebrations. "
        "Strict rules:\n"
        "1. Never contradict validated dataset records or invent fake vendor availability/bookings.\n"
        "2. Preserve the matched scenario ID, severity, and calculated rupee budget impact.\n"
        "3. Prioritize immediate guest safety and emergency service escalation.\n"
        "4. Return strictly valid JSON conforming to EventCrisisRecoveryResponse schema."
    )

    prompt = (
        f"Event Context:\n"
        f"- ID: {profile.event_id}\n"
        f"- Type: {profile.event_type.value}\n"
        f"- Name: {profile.event_name or 'Celebration'}\n"
        f"- City: {profile.city or 'Tier ' + profile.city_tier.value}\n"
        f"- Guests: {profile.guest_count}\n"
        f"- Total Budget: ₹{profile.total_budget_inr:,}\n\n"
        f"Crisis Disruption:\n"
        f"- Scenario ID: {matched.scenario_id}\n"
        f"- Category: {matched.crisis_type}\n"
        f"- Severity: {matched.severity}\n"
        f"- Cost Impact: {matched.cost_impact_pct_of_budget}%\n"
        f"- Baseline Recommendation: {matched.recommended_fix}\n\n"
        f"Baseline Recovery Data:\n"
        f"{baseline.model_dump_json(indent=2)}\n\n"
        f"Enrich the immediate actions, practical alternatives, and communication drafts with "
        f"respectful Indian hospitality tone. Keep placeholder brackets intact."
    )
    return prompt, system_instruction


async def evaluate_event_crisis(
    profile: EventProfile,
    dataset_repo: DatasetRepository,
    request: CrisisEvaluationRequest,
    orchestrator: AIOrchestrator | None = None,
) -> AIResultEnvelope[EventCrisisRecoveryResponse]:
    """Evaluate an event crisis and produce a structured, actionable recovery plan.

    Grounded in:
    - data/crisis_scenarios.csv via dataset_repo
    - Authoritative budget engine arithmetic
    - Timeline milestones and vendor checklist cross-references
    - Deterministic baseline with optional Gemini AI enrichment
    """
    # 1. Match scenario from CSV dataset or generate calibrated fallback
    scenarios = dataset_repo.scenarios if dataset_repo and dataset_repo.is_loaded else []
    matched = match_crisis_scenario(
        scenarios=scenarios,
        crisis_type=request.crisis_type,
        event_type=profile.event_type,
        severity=request.severity,
        guest_count=profile.guest_count,
        phase=request.event_phase,
    )

    # 2. Determine affected area
    meta = CRISIS_TYPE_MAP.get(matched.crisis_type)
    affected_area = request.affected_area or (meta.affected_area if meta else "operations")

    # 3. Calculate budget impact deterministically
    budget_impact = calculate_crisis_budget_impact(
        profile=profile,
        matched_scenario=matched,
        crisis_type=request.crisis_type,
    )

    # 4. Generate action items, safety triage, alternatives, and escalation guidance
    immediate_actions, next_actions, alternatives, escalation, warnings = generate_crisis_action_items(
        crisis_type=request.crisis_type,
        severity=request.severity,
        profile=profile,
        matched_scenario=matched,
        affected_area=affected_area,
        user_description=request.description,
    )

    # 5. Link relevant milestones and vendor checklist items
    ms_ids, vendor_ids, timeline_notes = find_relevant_milestone_and_vendor_ids(
        profile=profile,
        crisis_type=request.crisis_type,
    )

    # 6. Generate communication drafts
    active_mode = getattr(orchestrator, "mode", None) if orchestrator else None
    draft_source = "demo" if active_mode == AIMode.DEMO else "deterministic"
    drafts = generate_crisis_communication_drafts(
        crisis_type=request.crisis_type,
        severity=request.severity,
        profile=profile,
        source=draft_source,
    )

    # 7. Assemble deterministic baseline response
    summary = (
        f"{request.description or matched.description} (Severity {request.severity}/3). "
        f"Affecting {affected_area.replace('_', ' ').title()}. "
        f"Dataset Match: {'CSV ' + matched.scenario_id if matched.is_dataset_match else 'Calibrated Fallback'}."
    )

    baseline_response = EventCrisisRecoveryResponse(
        event_id=profile.event_id,
        event_type=profile.event_type,
        event_name=profile.event_name,
        event_phase=request.event_phase,
        matched_scenario=matched,
        crisis_summary=summary,
        severity=request.severity,
        affected_area=affected_area,
        immediate_actions=immediate_actions,
        next_step_actions=next_actions,
        alternatives=alternatives,
        budget_impact=budget_impact,
        timeline_implications=timeline_notes,
        relevant_milestone_ids=ms_ids,
        relevant_vendor_checklist_ids=vendor_ids,
        escalation_guidance=escalation,
        warnings=warnings,
        communication_drafts=drafts,
    )

    # 8. Check AI Orchestrator mode (demo, gemini, or auto)
    if orchestrator is None or active_mode == AIMode.DEMO:
        envelope_source = (
            AIResultSource.DEMO if active_mode == AIMode.DEMO else AIResultSource.DETERMINISTIC
        )
        return AIResultEnvelope[EventCrisisRecoveryResponse](
            status=AIResultStatus.SUCCESS,
            source=envelope_source,
            data=baseline_response,
            message=f"Crisis recovery plan generated ({'demo fixture' if envelope_source == AIResultSource.DEMO else 'deterministic rules'}).",
            warnings=warnings,
        )

    # 9. Gemini AI mode
    if active_mode == AIMode.GEMINI:
        if not getattr(orchestrator.gemini_service, "is_configured", False):
            return AIResultEnvelope[EventCrisisRecoveryResponse](
                status=AIResultStatus.UNAVAILABLE,
                source=AIResultSource.GEMINI,
                data=None,
                message="Gemini AI is required in 'gemini' mode, but GEMINI_API_KEY is not configured.",
                warnings=["Gemini API key is unconfigured. Fallback is disallowed in 'gemini' mode."],
            )

        prompt, sys_inst = build_crisis_recovery_prompt(profile, matched, baseline_response)
        envelope: AIResultEnvelope[EventCrisisRecoveryResponse] = await orchestrator.orchestrate(
            task=AITask.CRISIS_RECOVERY,
            response_schema=EventCrisisRecoveryResponse,
            prompt=prompt,
            system_instruction=sys_inst,
            request_data=profile,
        )
        # Guarantee dataset match integrity if Gemini responds
        if envelope.data:
            envelope.data.matched_scenario = matched
            envelope.data.budget_impact = budget_impact
        return envelope

    # 10. Auto mode with Gemini configured
    if getattr(orchestrator.gemini_service, "is_configured", False):
        prompt, sys_inst = build_crisis_recovery_prompt(profile, matched, baseline_response)
        envelope = await orchestrator.orchestrate(
            task=AITask.CRISIS_RECOVERY,
            response_schema=EventCrisisRecoveryResponse,
            prompt=prompt,
            system_instruction=sys_inst,
            request_data=profile,
        )
        if envelope.data:
            envelope.data.matched_scenario = matched
            envelope.data.budget_impact = budget_impact
        return envelope

    # Default auto offline fallback
    return AIResultEnvelope[EventCrisisRecoveryResponse](
        status=AIResultStatus.SUCCESS,
        source=AIResultSource.DETERMINISTIC,
        data=baseline_response,
        message="Crisis recovery plan generated deterministically.",
        warnings=warnings,
    )
