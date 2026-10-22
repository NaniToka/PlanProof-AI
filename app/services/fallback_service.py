"""Deterministic fallback service for PlanProof AI.

Provides rule-based, deterministic alternatives for features that have a
meaningful domain fallback when Gemini AI is unconfigured or temporarily unavailable.

Supported feature fallbacks:
- Event timeline & run-sheet generation (rule-based milestone schedules)
- Pre-mortem risk identification (calibrated to event type, tier, and headcount)
- Crisis recovery action playbook (calibrated to crisis category and severity)
- Family council deliberation summary
"""

from __future__ import annotations

from typing import Any

from app.schemas import (
    CityTier,
    CrisisRecoveryPlan,
    EventIdeasResponse,
    EventPhase,
    EventPlanRequest,
    EventTimelineResponse,
    EventType,
    FamilyCouncilCompromise,
    FamilyCouncilResponse,
    IdeaSource,
    MessageTarget,
    PersonaReview,
    PlanningMilestone,
    PreMortemRisk,
    RunSheetItem,
    WhatsAppMessageDraft,
)


def generate_deterministic_timeline(
    request_data: EventPlanRequest | None = None,
) -> EventTimelineResponse:
    """Generate a calibrated, deterministic timeline based on event parameters."""
    event_type = request_data.event_type if request_data else EventType.WEDDING
    city = request_data.city if request_data else "Event City"
    guests = request_data.guest_count if request_data else 300

    if event_type == EventType.WEDDING:
        milestones = [
            PlanningMilestone(
                milestone_name="Venue & Auspicious Date Finalization",
                phase=EventPhase.PLANNING,
                weeks_before=20,
                description=f"Confirm banquet/lawn contract in {city} with capacity for {guests} guests.",
                completed=True,
            ),
            PlanningMilestone(
                milestone_name="Catering Menu & Tasting",
                phase=EventPhase.PLANNING,
                weeks_before=14,
                description="Finalize live counter menus, dietary requirements, and staff ratios.",
                completed=False,
            ),
            PlanningMilestone(
                milestone_name="Decor, Stage & Floral Contracting",
                phase=EventPhase.PLANNING,
                weeks_before=8,
                description="Finalize stage backdrop, mandap florals, and guest table arrangements.",
                completed=False,
            ),
            PlanningMilestone(
                milestone_name="Photo & Video Production Brief",
                phase=EventPhase.PLANNING,
                weeks_before=4,
                description="Share family photo shot list and schedule drone flight approvals.",
                completed=False,
            ),
            PlanningMilestone(
                milestone_name="Final Vendor Walkthrough",
                phase=EventPhase.DAY_BEFORE,
                weeks_before=0,
                description="Conduct full on-site sound, lighting, and power backup testing.",
                completed=False,
            ),
        ]
        run_sheet = [
            RunSheetItem(
                start_time="09:00",
                end_time="11:30",
                activity_name="Morning Rituals & Breakfast",
                responsible_party="Family Hospitality Team",
                description="Traditional ceremonial preparation and breakfast service.",
            ),
            RunSheetItem(
                start_time="16:00",
                end_time="17:30",
                activity_name="Baraat & Welcoming Procession",
                responsible_party="Groom's Lead & Venue Security",
                description="Entry procession and ceremonial welcoming garland exchange.",
            ),
            RunSheetItem(
                start_time="18:00",
                end_time="20:00",
                activity_name="Main Ceremony & Vows",
                responsible_party="Ceremony Officiant & Family",
                description="Sacred ceremony rituals followed by stage photographs.",
            ),
            RunSheetItem(
                start_time="20:00",
                end_time="23:00",
                activity_name="Dinner Buffet & Social Celebration",
                responsible_party="Catering Lead & Event DJ",
                description="Full dinner buffet open; family musical performances and couple felicitation.",
            ),
        ]
    elif event_type == EventType.BIRTHDAY:
        milestones = [
            PlanningMilestone(
                milestone_name="Venue Reservation & Theme Selection",
                phase=EventPhase.PLANNING,
                weeks_before=4,
                description=f"Reserve event hall in {city} and order custom themed invitations.",
                completed=True,
            ),
            PlanningMilestone(
                milestone_name="Cake & Activities Booking",
                phase=EventPhase.PLANNING,
                weeks_before=2,
                description="Order custom specialty cake and book interactive entertainer or DJ.",
                completed=False,
            ),
            PlanningMilestone(
                milestone_name="Final Catering Confirmation",
                phase=EventPhase.PLANNING,
                weeks_before=1,
                description=f"Confirm food & beverage count for {guests} attendees with venue.",
                completed=False,
            ),
        ]
        run_sheet = [
            RunSheetItem(
                start_time="17:00",
                end_time="18:00",
                activity_name="Guest Welcome & Activity Stations",
                responsible_party="Event Host",
                description="Welcome drinks, snack pass-around, and themed games.",
            ),
            RunSheetItem(
                start_time="18:00",
                end_time="18:45",
                activity_name="Entertainment Program",
                responsible_party="Party Entertainer",
                description="Interactive games, group activities, and music.",
            ),
            RunSheetItem(
                start_time="18:45",
                end_time="19:15",
                activity_name="Cake Cutting Ceremony",
                responsible_party="Lead Family Organizers",
                description="Celebratory cake cutting and group photography.",
            ),
            RunSheetItem(
                start_time="19:15",
                end_time="21:00",
                activity_name="Dinner Buffet & Favor Distribution",
                responsible_party="Catering Lead",
                description="Dinner service opens; party favor bags distributed upon exit.",
            ),
        ]
    else:  # COMMUNITY_EVENT
        milestones = [
            PlanningMilestone(
                milestone_name="Permits & Venue Booking",
                phase=EventPhase.PLANNING,
                weeks_before=8,
                description=f"Secure community ground/hall in {city} and acquire local permits.",
                completed=True,
            ),
            PlanningMilestone(
                milestone_name="Sound, Staging & Logistics Contracting",
                phase=EventPhase.PLANNING,
                weeks_before=4,
                description="Contract stage rigging, PA system, and volunteer coordinator.",
                completed=False,
            ),
            PlanningMilestone(
                milestone_name="Community Registration & Logistics Review",
                phase=EventPhase.PLANNING,
                weeks_before=1,
                description=f"Verify crowd management and emergency medical aid for {guests} participants.",
                completed=False,
            ),
        ]
        run_sheet = [
            RunSheetItem(
                start_time="09:00",
                end_time="10:00",
                activity_name="Registration & Morning Welcome",
                responsible_party="Volunteer Welcome Desk",
                description="Attendee badge check-in and seating assistance.",
            ),
            RunSheetItem(
                start_time="10:00",
                end_time="13:00",
                activity_name="Main Program & Cultural Presentations",
                responsible_party="Program Director",
                description="Opening addresses, community cultural showcase, and guest talks.",
            ),
            RunSheetItem(
                start_time="13:00",
                end_time="15:00",
                activity_name="Community Lunch & Networking",
                responsible_party="Logistics Lead",
                description="Buffet dining and community interaction booths.",
            ),
        ]

    return EventTimelineResponse(planning_milestones=milestones, run_sheet=run_sheet)


def generate_deterministic_risks(
    request_data: EventPlanRequest | None = None,
) -> list[PreMortemRisk]:
    """Generate calibrated deterministic pre-mortem risks based on event parameters."""
    guests = request_data.guest_count if request_data else 300
    tier = request_data.city_tier if request_data else CityTier.METRO
    event_type = request_data.event_type if request_data else EventType.WEDDING

    risks: list[PreMortemRisk] = [
        PreMortemRisk(
            risk_description="Peak traffic and parking congestion near the venue",
            probability=0.45 if tier == CityTier.METRO else 0.25,
            cost_impact_pct_of_budget=1.5,
            mitigation=(
                "Contract professional valet service with designated offsite parking overflow "
                "and publish Google Maps parking guide."
            ),
        ),
        PreMortemRisk(
            risk_description="Unseasonal weather disruption to open-air event segments",
            probability=0.30,
            cost_impact_pct_of_budget=5.0,
            mitigation=(
                "Secure weatherproofing contingency with venue: hold adjacent covered hall "
                "or waterproof canopy option on 48-hour release."
            ),
        ),
        PreMortemRisk(
            risk_description="Catering replenishment bottleneck during peak dining rush",
            probability=0.40 if guests > 400 else 0.20,
            cost_impact_pct_of_budget=2.0,
            mitigation=(
                "Mandate 1:25 service staff-to-guest ratio and duplicate high-traffic buffet counters "
                "to ensure continuous live replenishment."
            ),
        ),
        PreMortemRisk(
            risk_description="AV, lighting, or primary power interruption during ceremony",
            probability=0.20,
            cost_impact_pct_of_budget=1.0,
            mitigation=(
                "Require dual silent diesel backup generators with automatic transfer switches (ATS) "
                "certified before event kickoff."
            ),
        ),
    ]

    if event_type == EventType.WEDDING:
        risks.append(
            PreMortemRisk(
                risk_description="Ceremony schedule overrun delaying banquet service past curfew",
                probability=0.50,
                cost_impact_pct_of_budget=0.5,
                mitigation=(
                    "Build a 45-minute buffer into the run-sheet before reception start; "
                    "align with panditji on strict timeline checkpoints."
                ),
            )
        )

    return risks


def generate_deterministic_crisis_recovery(
    crisis_type: str = "rain",
    severity: int = 2,
) -> CrisisRecoveryPlan:
    """Generate a calibrated deterministic crisis recovery plan for event disruptions."""
    clean_type = crisis_type.strip().lower()

    if "rain" in clean_type or "weather" in clean_type:
        return CrisisRecoveryPlan(
            detected_crisis_type=clean_type,
            severity=severity,
            timeline_changes=[
                "Shift lawn activities indoors to secondary hall immediately",
                "Extend indoor beverage service by 20 minutes while staging is reconfigured",
            ],
            explanation=(
                f"Severe weather alert detected (severity {severity}). Outdoor setups are at risk "
                "of water damage and guest discomfort."
            ),
            recommended_actions=[
                "Direct venue operations to roll out waterproof German canopy over stage.",
                "Reroute guest flow to covered walkways with temporary floor runners.",
                "Verify all electrical distribution boxes are elevated and insulated.",
            ],
            whatsapp_message_drafts=[
                WhatsAppMessageDraft(
                    target=MessageTarget.GUESTS,
                    recipient_label="All Attending Guests",
                    message_text=(
                        "Event Update: Due to weather, today's festivities have smoothly transitioned "
                        "into the Grand Indoor Ballroom. Valet and reception welcome desks remain open."
                    ),
                ),
                WhatsAppMessageDraft(
                    target=MessageTarget.VENDOR,
                    recipient_label="Decor and Staging Team",
                    message_text=(
                        "Urgent Operations Notice: Move outdoor sound consoles and floral arrangements "
                        "under indoor cover immediately. Activate waterproof canopy."
                    ),
                ),
            ],
        )

    # General / Vendor / Power Disruption Default
    return CrisisRecoveryPlan(
        detected_crisis_type=clean_type,
        severity=severity,
        timeline_changes=[
            "Pause main stage program for 15 minutes to adjust technical systems",
            "Open side beverage counters to keep guests engaged",
        ],
        explanation=(
            f"Operational disruption '{clean_type}' encountered at severity {severity}. "
            "Activating standard continuity procedures."
        ),
        recommended_actions=[
            "Notify on-site coordinator and verify primary contractor service level agreements.",
            "Deploy contracted backup equipment / alternative vendor personnel.",
            "Maintain calm hospitality presence across guest contact zones.",
        ],
        whatsapp_message_drafts=[
            WhatsAppMessageDraft(
                target=MessageTarget.VENDOR,
                recipient_label="Backup Service Vendor",
                message_text=(
                    f"Urgent operational request: Activating emergency backup coverage for '{clean_type}'. "
                    "Please confirm dispatch of lead technician."
                ),
            ),
            WhatsAppMessageDraft(
                target=MessageTarget.FAMILY,
                recipient_label="Core Family Committee",
                message_text=(
                    f"Status Update: We are managing a minor '{clean_type}' adjustment. "
                    "Backup protocol in effect; schedule will resume shortly."
                ),
            ),
        ],
    )


def generate_deterministic_family_council(
    request_data: EventPlanRequest | None = None,
) -> FamilyCouncilResponse:
    """Generate a calibrated deterministic family council compromise."""
    guests = request_data.guest_count if request_data else 300
    city = request_data.city if request_data else "Event City"

    return FamilyCouncilResponse(
        budget_holder=PersonaReview(
            persona_name="Budget Holder (Pragmatic Organizer)",
            concerns=[
                f"Total event expenditure in {city} requires disciplined milestone payment tracking.",
                "Emergency buffer reserve must be strictly maintained at 6-8% of total budget.",
            ],
            suggested_changes=[
                "Structure all vendor contracts with 30% advance and 20% post-delivery retention.",
                "Lock in catering plate guarantees 10% below peak RSVP expectations.",
            ],
        ),
        elder_relative=PersonaReview(
            persona_name="Elder Relative (Cultural Guardian)",
            concerns=[
                "Ceremonial rituals must strictly align with traditional auspicious muhurat hours.",
                "Adequate comfortable, accessible seating required for senior family members.",
            ],
            suggested_changes=[
                "Reserve dedicated quiet lounge near stage with temperature control.",
                "Protect 90 minutes of dedicated ceremony time free of loud amplification.",
            ],
        ),
        picky_friend=PersonaReview(
            persona_name="Picky Friend (Aesthetic & Social Lead)",
            concerns=[
                "Lighting and staging must look crisp for social media and candid photography.",
                "Music curation should balance traditional melodies with contemporary high-energy sets.",
            ],
            suggested_changes=[
                "Add diffused warm lighting to reception perimeter and install dedicated photo booth.",
                "Schedule dynamic DJ set right after dinner commences.",
            ],
        ),
        parent_with_kids=PersonaReview(
            persona_name="Parent with Young Children",
            concerns=[
                "Late dinner schedules cause tantrums and fatigue for younger attendees.",
                "Crowded dining aisles create safety hazards for strollers and small children.",
            ],
            suggested_changes=[
                "Open early kids dining counter with mild finger foods at 18:30.",
                "Designate quiet green room for family rest and diaper changing.",
            ],
        ),
        compromise=FamilyCouncilCompromise(
            agreed_plan=(
                f"Consensus achieved for {guests} guests in {city}: Ceremony protected with senior lounge; "
                "early kids food station established; aesthetic lighting funded via vendor renegotiation; "
                "6% emergency buffer preserved."
            ),
            remaining_objections={
                "budget_holder": [
                    "Valet shuttle extension requires ₹12,000 reallocation from decor buffer."
                ]
            },
        ),
    )


# ==============================================================================
# 5. Deterministic Event Ideas
# ==============================================================================


def generate_deterministic_event_ideas(
    request_data: Any = None,
) -> EventIdeasResponse:
    """Generate calibrated, deterministic event recommendations based on event profile."""
    from app.services.recommendation_service import (
        generate_deterministic_event_ideas as _gen_ideas,
    )

    return _gen_ideas(event_or_req=request_data or {}, source=IdeaSource.RULES)
