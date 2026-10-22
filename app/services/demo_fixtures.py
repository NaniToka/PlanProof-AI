"""Safe, deterministic sample demonstration fixtures for PlanProof AI.

Contains synthetic, fictional event details and illustrative examples for:
- Wedding planning checklist and timeline run-sheet
- Birthday planning checklist and timeline run-sheet
- Event pre-mortem risk assessment
- Crisis recovery action plan and WhatsApp communication drafts
- Four-perspective family council deliberation and compromise

Rules:
- Strictly deterministic with zero randomness or external network dependencies.
- Uses fictional placeholders and synthetic assumptions; never real vendors,
  current live pricing, or verified confirmations.
- Clearly labelled as illustrative demo content.
"""

from __future__ import annotations

from typing import Any

from app.schemas import (
    CrisisRecoveryPlan,
    EventIdeasResponse,
    EventPhase,
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

# ==============================================================================
# 1. Demo Timelines
# ==============================================================================


def get_demo_wedding_timeline() -> EventTimelineResponse:
    """Return a deterministic, illustrative wedding timeline with checklist and run-sheet."""
    milestones = [
        PlanningMilestone(
            milestone_name="Venue Selection & Date Finalization",
            phase=EventPhase.PLANNING,
            weeks_before=24,
            description=(
                "[Illustrative Demo] Shortlist 3 fictional banquet/lawn properties; "
                "verify seating capacity for 350 guests and parking arrangements."
            ),
            completed=True,
        ),
        PlanningMilestone(
            milestone_name="Catering Menu Tasting",
            phase=EventPhase.PLANNING,
            weeks_before=16,
            description=(
                "[Illustrative Demo] Sample vegetarian live counters, regional specialties, "
                "and finalize separate Jain/Halal food preparation logistics."
            ),
            completed=False,
        ),
        PlanningMilestone(
            milestone_name="Decor & Mandap Finalization",
            phase=EventPhase.PLANNING,
            weeks_before=8,
            description=(
                "[Illustrative Demo] Confirm mandap floral staging, canopy weatherproofing, "
                "and stage spotlight layouts with lead decorator."
            ),
            completed=False,
        ),
        PlanningMilestone(
            milestone_name="Family Rehearsal & Sound Checks",
            phase=EventPhase.DAY_BEFORE,
            weeks_before=0,
            description=(
                "[Illustrative Demo] Walk through sangeet choreography entry cues and "
                "test wireless microphones with DJ and family MC."
            ),
            completed=False,
        ),
    ]

    run_sheet = [
        RunSheetItem(
            start_time="09:00",
            end_time="11:00",
            activity_name="Haldi Ceremony & Morning Breakfast",
            responsible_party="Family Elders & Hospitality Lead",
            description=(
                "[Illustrative Demo] Turmeric rituals in courtyard, followed by traditional "
                "breakfast and welcome refreshments."
            ),
        ),
        RunSheetItem(
            start_time="16:30",
            end_time="18:00",
            activity_name="Baraat Procession & Milni Welcome",
            responsible_party="Groom's Family Lead & Brass Band",
            description=(
                "[Illustrative Demo] Musical procession from entrance gate; formal garland "
                "greeting (Milni) by bride's family."
            ),
        ),
        RunSheetItem(
            start_time="18:30",
            end_time="20:30",
            activity_name="Varmala & Sacred Pheras",
            responsible_party="Panditji & Stage Coordinator",
            description=(
                "[Illustrative Demo] Stage garland exchange followed by traditional mandap "
                "ceremony and sacred fire vows."
            ),
        ),
        RunSheetItem(
            start_time="20:30",
            end_time="23:00",
            activity_name="Dinner Buffet & Sangeet Celebrations",
            responsible_party="Banquet Manager & Event DJ",
            description=(
                "[Illustrative Demo] Main buffet dinner stations open; couple felicitation "
                "and family musical performances."
            ),
        ),
    ]

    return EventTimelineResponse(planning_milestones=milestones, run_sheet=run_sheet)


def get_demo_birthday_timeline() -> EventTimelineResponse:
    """Return a deterministic, illustrative birthday timeline with checklist and run-sheet."""
    milestones = [
        PlanningMilestone(
            milestone_name="Theme & Hall Booking",
            phase=EventPhase.PLANNING,
            weeks_before=4,
            description=(
                "[Illustrative Demo] Reserve community clubhouse banquet space and confirm "
                "superhero adventure decorative theme."
            ),
            completed=True,
        ),
        PlanningMilestone(
            milestone_name="Cake & Children's Entertainer",
            phase=EventPhase.PLANNING,
            weeks_before=2,
            description=(
                "[Illustrative Demo] Book custom two-tier chocolate cake and confirm "
                "interactive magician and balloon artist."
            ),
            completed=False,
        ),
        PlanningMilestone(
            milestone_name="Party Favors & Headcount Confirmation",
            phase=EventPhase.PLANNING,
            weeks_before=1,
            description=(
                "[Illustrative Demo] Assemble themed return gift packs and confirm final "
                "count with caterer."
            ),
            completed=False,
        ),
    ]

    run_sheet = [
        RunSheetItem(
            start_time="17:00",
            end_time="17:30",
            activity_name="Arrival & Welcome Icebreakers",
            responsible_party="Party Host & Tattoo Artist",
            description=(
                "[Illustrative Demo] Welcome drinks, temporary tattoo booth, and kid-friendly "
                "icebreaker games."
            ),
        ),
        RunSheetItem(
            start_time="17:30",
            end_time="18:30",
            activity_name="Interactive Magic & Game Show",
            responsible_party="Guest Entertainer",
            description=(
                "[Illustrative Demo] 45-minute magic show followed by musical statues "
                "and team trivia."
            ),
        ),
        RunSheetItem(
            start_time="18:30",
            end_time="19:00",
            activity_name="Cake Cutting & Celebratory Song",
            responsible_party="Parents & Family",
            description=(
                "[Illustrative Demo] Candle lighting, birthday song chorus, and family photos "
                "at photo booth."
            ),
        ),
        RunSheetItem(
            start_time="19:00",
            end_time="20:30",
            activity_name="Kid-Friendly Buffet & Return Gifts",
            responsible_party="Hospitality Coordinator",
            description=(
                "[Illustrative Demo] Slider and pasta stations open; goodie bags distributed "
                "as guests depart."
            ),
        ),
    ]

    return EventTimelineResponse(planning_milestones=milestones, run_sheet=run_sheet)


def get_demo_timeline(event_type: EventType | str = EventType.WEDDING) -> EventTimelineResponse:
    """Select the appropriate demo timeline fixture based on event type."""
    ev_str = event_type.value if isinstance(event_type, EventType) else str(event_type).lower()
    if "birthday" in ev_str:
        return get_demo_birthday_timeline()
    return get_demo_wedding_timeline()


# ==============================================================================
# 2. Demo Pre-Mortem Risks
# ==============================================================================


def get_demo_event_risks(
    event_type: EventType | str = EventType.WEDDING,
) -> list[PreMortemRisk]:
    """Return a deterministic list of illustrative pre-mortem risks and mitigations."""
    return [
        PreMortemRisk(
            risk_description=(
                "[Illustrative Demo] Unseasonal evening rain or storm damaging open lawn setup"
            ),
            probability=0.25,
            cost_impact_pct_of_budget=5.5,
            mitigation=(
                "[Illustrative Demo] Secure an on-call waterproof German hangar option and keep "
                "adjacent indoor ballroom on 24-hour backup hold."
            ),
        ),
        PreMortemRisk(
            risk_description=(
                "[Illustrative Demo] Peak traffic bottleneck causing 45-minute guest arrival delay"
            ),
            probability=0.40,
            cost_impact_pct_of_budget=1.2,
            mitigation=(
                "[Illustrative Demo] Coordinate dedicated shared shuttles from major transit hubs; "
                "dispatch live traffic updates via WhatsApp broadcast."
            ),
        ),
        PreMortemRisk(
            risk_description=(
                "[Illustrative Demo] Municipal noise curfew enforcement halting outdoor DJ sound at 10 PM"
            ),
            probability=0.50,
            cost_impact_pct_of_budget=0.0,
            mitigation=(
                "[Illustrative Demo] Schedule high-volume musical performances before 21:45; "
                "transition after-party indoors to an acoustic-insulated banquet room."
            ),
        ),
        PreMortemRisk(
            risk_description=(
                "[Illustrative Demo] High-demand catering live counter queue overload"
            ),
            probability=0.35,
            cost_impact_pct_of_budget=2.0,
            mitigation=(
                "[Illustrative Demo] Duplicate popular counters (chaat, dosa, desserts) on both "
                "sides of the dining area to bisect queue lengths."
            ),
        ),
    ]


# ==============================================================================
# 3. Demo Crisis Recovery Plan
# ==============================================================================


def get_demo_crisis_recovery() -> CrisisRecoveryPlan:
    """Return a deterministic, illustrative crisis recovery plan for vendor disruption."""
    return CrisisRecoveryPlan(
        detected_crisis_type="vendor_cancellation",
        severity=2,
        timeline_changes=[
            "[Illustrative Demo] Push main dinner buffet opening back 30 minutes from 20:00 to 20:30",
            "[Illustrative Demo] Extend mocktail service and roving appetizers to maintain guest comfort",
        ],
        explanation=(
            "[Illustrative Demo] Contracted primary dessert vendor experienced transport vehicle breakdown "
            "3 hours prior to dinner service."
        ),
        recommended_actions=[
            "[Illustrative Demo] Activate emergency backup sweet caterer to supply 350 portions of warm jalebi and rabdi.",
            "[Illustrative Demo] Request banquet head chef to expand fresh fruit and kulfi live station.",
            "[Illustrative Demo] Inform family hospitality lead quietly; avoid public announcements that create worry.",
        ],
        whatsapp_message_drafts=[
            WhatsAppMessageDraft(
                target=MessageTarget.VENDOR,
                recipient_label="Backup Sweet Caterer (Illustrative)",
                message_text=(
                    "[Illustrative Demo] Urgent: Activating emergency backup sweet supply option. "
                    "Need 350 portions of jalebi/kulfi delivered to Royal Lawn by 19:45. Please confirm dispatch."
                ),
            ),
            WhatsAppMessageDraft(
                target=MessageTarget.FAMILY,
                recipient_label="Core Family Committee",
                message_text=(
                    "[Illustrative Demo] Quick Update: Minor delay with dessert transport. Backup vendor activated "
                    "seamlessly. Starters and live counters extended. Everything under control!"
                ),
            ),
        ],
    )


# ==============================================================================
# 4. Demo Family Council Deliberation
# ==============================================================================


def get_demo_family_council() -> FamilyCouncilResponse:
    """Return a deterministic, illustrative four-persona family council review and compromise."""
    return FamilyCouncilResponse(
        budget_holder=PersonaReview(
            persona_name="Budget Holder (Pragmatic Uncle)",
            concerns=[
                "[Illustrative Demo] Upfront 50% vendor advances create heavy early cash strain.",
                "[Illustrative Demo] Imported floral decor quotes exceed reasonable contingency margins.",
            ],
            suggested_changes=[
                "[Illustrative Demo] Renegotiate to 30% booking advance, 50% week-of-event, 20% on completion.",
                "[Illustrative Demo] Substitute local seasonal marigold and jasmine arrangements to save ₹45,000.",
            ],
        ),
        elder_relative=PersonaReview(
            persona_name="Elder Relative (Dadi / Nani)",
            concerns=[
                "[Illustrative Demo] Muhurat rituals scheduled too close to evening sangeet.",
                "[Illustrative Demo] Lack of quiet, cushioned seating near the mandap for elderly guests.",
            ],
            suggested_changes=[
                "[Illustrative Demo] Preserve 90 uninterrupted minutes for the sacred ceremony before music starts.",
                "[Illustrative Demo] Designate a dedicated front-row seating lounge with fans and warm beverages.",
            ],
        ),
        picky_friend=PersonaReview(
            persona_name="Picky Friend (Aesthetic Lead)",
            concerns=[
                "[Illustrative Demo] Stage backdrop lighting appears harsh in test photography.",
                "[Illustrative Demo] Standard venue marquee looks dated without contemporary accents.",
            ],
            suggested_changes=[
                "[Illustrative Demo] Add warm fairy-light canopy overhead and install a dedicated aesthetic photobooth nook.",
            ],
        ),
        parent_with_kids=PersonaReview(
            persona_name="Parent with Young Children",
            concerns=[
                "[Illustrative Demo] Dinner at 21:00 is too late for toddlers and younger children.",
                "[Illustrative Demo] No designated quiet area for stroller rest or diaper changing.",
            ],
            suggested_changes=[
                "[Illustrative Demo] Open an early kids snack buffet (finger food, milk, juices) at 18:30.",
                "[Illustrative Demo] Reserve an air-conditioned green room for parents with infant cots.",
            ],
        ),
        compromise=FamilyCouncilCompromise(
            agreed_plan=(
                "[Illustrative Demo] Balanced Consensus: Muhurat ceremony given priority at 18:30 with cushioned "
                "elderly lounge; kids mini-buffet opens at 18:30; decor costs trimmed by ₹45,000 using local seasonal "
                "florals, enabling addition of fairy-light canopy within budget; vendor payment structured at 30-50-20."
            ),
            remaining_objections={
                "budget_holder": [
                    "[Illustrative Demo] Extra air-conditioned green room rental adds ₹8,000 to logistics buffer."
                ]
            },
        ),
    )


# ==============================================================================
# 5. Demo Event Ideas
# ==============================================================================


def get_demo_event_ideas(event_or_req: Any = None) -> EventIdeasResponse:
    """Return deterministic, illustrative demonstration event ideas.

    All recommendations are explicitly attributed to demo provenance.
    """
    from app.services.recommendation_service import generate_deterministic_event_ideas

    return generate_deterministic_event_ideas(
        event_or_req=event_or_req or {},
        source=IdeaSource.DEMO,
    )
