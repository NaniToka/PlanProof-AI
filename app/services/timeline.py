"""Deterministic event timeline and milestone scheduling engine for PlanProof AI.

Critical Invariant:
Date arithmetic, lead times, and deadline ordering are computed strictly using Python
calendar-date arithmetic. Gemini or LLMs must NEVER decide date calculations or orderings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.schemas import (
    EventMilestone,
    EventTimelineScheduleResponse,
    EventType,
    MilestoneCategory,
    MilestonePriority,
    MilestoneStatus,
    get_current_ist_date,
)


@dataclass(frozen=True)
class MilestoneTemplateItem:
    """Template definition for a milestone relative to an event date."""

    milestone_id: str
    title: str
    description: str
    category: MilestoneCategory
    days_before_event: int
    priority: MilestonePriority


# ==============================================================================
# 1. Event Type Milestone Templates
# ==============================================================================


WEDDING_TIMELINE_TEMPLATE: tuple[MilestoneTemplateItem, ...] = (
    MilestoneTemplateItem(
        milestone_id="M-WED-01",
        title="Set wedding budget & initial guest estimate",
        description="Establish total budget allocations in INR and draft the preliminary family guest headcount.",
        category=MilestoneCategory.LOGISTICS,
        days_before_event=180,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-WED-02",
        title="Shortlist and book wedding venue / mandap",
        description="Inspect banquet halls or outdoor lawns, verify booking advances, and reserve auspicious dates.",
        category=MilestoneCategory.VENUE,
        days_before_event=150,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-WED-03",
        title="Book core vendors (caterer, photographer & decorator)",
        description="Confirm caterer menu, lock in candid photographer/videographer, and select floral/mandap decor team.",
        category=MilestoneCategory.CATERING,
        days_before_event=120,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-WED-04",
        title="Design and dispatch wedding invitations",
        description="Finalize card design and distribution list; send physical wedding cards and digital save-the-dates.",
        category=MilestoneCategory.INVITATIONS,
        days_before_event=60,
        priority=MilestonePriority.MEDIUM,
    ),
    MilestoneTemplateItem(
        milestone_id="M-WED-05",
        title="Finalize stage, floral decor & mandap setup",
        description="Approve 3D layout, entrance arch, mandap backdrop, lighting plan, and backup generator arrangement.",
        category=MilestoneCategory.DECOR,
        days_before_event=45,
        priority=MilestonePriority.MEDIUM,
    ),
    MilestoneTemplateItem(
        milestone_id="M-WED-06",
        title="Confirm guest transport, rooms & logistics",
        description="Reserve hotel room blocks for outstation guests and coordinate airport/station pick-up transport.",
        category=MilestoneCategory.LOGISTICS,
        days_before_event=30,
        priority=MilestonePriority.MEDIUM,
    ),
    MilestoneTemplateItem(
        milestone_id="M-WED-07",
        title="Lock in final catering guest count & menu tasting",
        description="Review dietary restrictions, conduct food tasting, and confirm guaranteed per-plate count.",
        category=MilestoneCategory.CATERING,
        days_before_event=14,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-WED-08",
        title="Review accessibility, backup power & weather buffers",
        description="Walk through elderly guest access, sound permissions, water stations, and rain-cover contingency plan.",
        category=MilestoneCategory.LOGISTICS,
        days_before_event=7,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-WED-09",
        title="Complete final rehearsal, vendor contacts & day-of checklist",
        description="Verify remaining cash/NEFT balances for vendors, brief the family council, and print run-sheets.",
        category=MilestoneCategory.FINAL_CHECKS,
        days_before_event=2,
        priority=MilestonePriority.HIGH,
    ),
)


BIRTHDAY_TIMELINE_TEMPLATE: tuple[MilestoneTemplateItem, ...] = (
    MilestoneTemplateItem(
        milestone_id="M-BDY-01",
        title="Define birthday theme, budget & guest list",
        description="Select party theme, set total spending limit, and prepare guest list with children and adults counts.",
        category=MilestoneCategory.LOGISTICS,
        days_before_event=30,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-BDY-02",
        title="Reserve party hall or outdoor venue",
        description="Book local community hall, restaurant party space, or outdoor play area; confirm duration and amenities.",
        category=MilestoneCategory.VENUE,
        days_before_event=21,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-BDY-03",
        title="Send digital invitations & track RSVPs",
        description="Create digital WhatsApp invitation cards, share location map, and monitor confirmation replies.",
        category=MilestoneCategory.INVITATIONS,
        days_before_event=14,
        priority=MilestonePriority.MEDIUM,
    ),
    MilestoneTemplateItem(
        milestone_id="M-BDY-04",
        title="Order custom cake, snacks & catering menu",
        description="Book themed birthday cake baker, arrange finger snacks, beverages, and child-friendly buffet food.",
        category=MilestoneCategory.CATERING,
        days_before_event=10,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-BDY-05",
        title="Arrange balloon decor, music playlist & games",
        description="Procure theme balloon arch, party props, photo booth frame, sound speaker, and game host materials.",
        category=MilestoneCategory.DECOR,
        days_before_event=7,
        priority=MilestonePriority.MEDIUM,
    ),
    MilestoneTemplateItem(
        milestone_id="M-BDY-06",
        title="Confirm final guest headcount with caterer",
        description="Recheck RSVPs, lock in food quantities and cake delivery timing with vendors.",
        category=MilestoneCategory.CATERING,
        days_before_event=3,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-BDY-07",
        title="Pack return gifts and complete final checklist",
        description="Assemble personalized return gift bags, charge cameras/speakers, and confirm venue access hour.",
        category=MilestoneCategory.FINAL_CHECKS,
        days_before_event=1,
        priority=MilestonePriority.HIGH,
    ),
)


COMMUNITY_EVENT_TIMELINE_TEMPLATE: tuple[MilestoneTemplateItem, ...] = (
    MilestoneTemplateItem(
        milestone_id="M-COM-01",
        title="Define community event scope, committee & budget",
        description="Form organizing committee, assign sub-leads, and establish overall fund allocations.",
        category=MilestoneCategory.LOGISTICS,
        days_before_event=60,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-COM-02",
        title="Secure community ground, stage & municipal permits",
        description="Apply for local authority/police sound permissions, society NOCs, and reserve open grounds or auditorium.",
        category=MilestoneCategory.VENUE,
        days_before_event=45,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-COM-03",
        title="Book sound system, generator & public address gear",
        description="Contract PA equipment vendor, stage microphones, lighting, and heavy-duty diesel generator backup.",
        category=MilestoneCategory.LOGISTICS,
        days_before_event=30,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-COM-04",
        title="Announce event and distribute community notices",
        description="Post flyers on community noticeboards, broadcast WhatsApp group announcements, and display banner posters.",
        category=MilestoneCategory.INVITATIONS,
        days_before_event=21,
        priority=MilestonePriority.MEDIUM,
    ),
    MilestoneTemplateItem(
        milestone_id="M-COM-05",
        title="Coordinate volunteer teams and seating layout",
        description="Allocate volunteers for registration, parking management, elderly seating, and stage coordination.",
        category=MilestoneCategory.LOGISTICS,
        days_before_event=14,
        priority=MilestonePriority.MEDIUM,
    ),
    MilestoneTemplateItem(
        milestone_id="M-COM-06",
        title="Arrange drinking water, community meals & waste disposal",
        description="Order filtered water cans, disposable eco-friendly bins, community prasad or dinner catering setup.",
        category=MilestoneCategory.CATERING,
        days_before_event=7,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-COM-07",
        title="Review crowd safety, first aid & fire clearances",
        description="Inspect emergency exit paths, first-aid station kit, fire extinguishers, and volunteer badge passes.",
        category=MilestoneCategory.FINAL_CHECKS,
        days_before_event=3,
        priority=MilestonePriority.HIGH,
    ),
    MilestoneTemplateItem(
        milestone_id="M-COM-08",
        title="Conduct stage soundcheck and volunteer briefing",
        description="Test microphones and lighting, run final stage cue sheet, and complete evening setup walk-through.",
        category=MilestoneCategory.FINAL_CHECKS,
        days_before_event=1,
        priority=MilestonePriority.HIGH,
    ),
)


TIMELINE_TEMPLATES: dict[EventType, tuple[MilestoneTemplateItem, ...]] = {
    EventType.WEDDING: WEDDING_TIMELINE_TEMPLATE,
    EventType.BIRTHDAY: BIRTHDAY_TIMELINE_TEMPLATE,
    EventType.COMMUNITY_EVENT: COMMUNITY_EVENT_TIMELINE_TEMPLATE,
}


def get_template_for_event_type(event_type: EventType | str) -> tuple[MilestoneTemplateItem, ...]:
    """Retrieve the milestone template tuple for a given event type."""
    try:
        resolved = event_type if isinstance(event_type, EventType) else EventType(event_type)
    except ValueError:
        resolved = EventType.WEDDING
    return TIMELINE_TEMPLATES.get(resolved, WEDDING_TIMELINE_TEMPLATE)


# ==============================================================================
# 2. Deterministic Timeline Generator
# ==============================================================================


def generate_deterministic_timeline(
    event_id: str,
    event_type: EventType | str,
    event_date: date | None,
    milestone_statuses: dict[str, MilestoneStatus] | None = None,
    reference_date: date | None = None,
) -> EventTimelineScheduleResponse:
    """Generate a chronologically ordered, deterministic milestone schedule for an event.

    Args:
        event_id: Unique event profile identifier.
        event_type: Event type category.
        event_date: Event scheduled calendar date.
        milestone_statuses: Optional mapping of milestone_id to custom completion status.
        reference_date: Optional simulated 'today' for deterministic date testing (defaults to IST current date).

    Returns:
        Validated EventTimelineScheduleResponse.
    """
    ref_date = reference_date or get_current_ist_date()
    now_utc = datetime.now(timezone.utc)
    statuses = milestone_statuses or {}

    # If event date is missing, return empty milestone list with clear warning
    if event_date is None:
        return EventTimelineScheduleResponse(
            event_id=event_id,
            event_date=None,
            generated_at=now_utc,
            milestones=[],
            warnings=[
                "Event date is not set on this profile. Add an event_date via "
                f"PATCH /api/v1/events/{event_id} to generate a dated milestone schedule."
            ],
        )

    template_items = get_template_for_event_type(event_type)
    milestones: list[EventMilestone] = []

    for item in template_items:
        due_date = event_date - timedelta(days=item.days_before_event)
        raw_status = statuses.get(item.milestone_id, MilestoneStatus.PENDING)
        status = (
            raw_status
            if isinstance(raw_status, MilestoneStatus)
            else MilestoneStatus(raw_status)
        )
        # Completed milestones are never overdue
        is_overdue = (due_date < ref_date) and (status != MilestoneStatus.COMPLETED)

        milestones.append(
            EventMilestone(
                milestone_id=item.milestone_id,
                title=item.title,
                description=item.description,
                category=item.category,
                due_date=due_date,
                days_before_event=item.days_before_event,
                priority=item.priority,
                status=status,
                is_overdue=is_overdue,
            )
        )

    # Sort chronologically by due_date ascending (earliest first), breaking ties by milestone_id
    sorted_milestones = sorted(milestones, key=lambda m: (m.due_date, m.milestone_id))

    warnings: list[str] = []
    # 1. Overdue warning
    overdue_count = sum(1 for m in sorted_milestones if m.is_overdue)
    if overdue_count > 0:
        warnings.append(
            f"{overdue_count} milestone(s) are overdue based on the scheduled event date ({event_date}) "
            f"and current date ({ref_date}). Prioritize pending high-priority tasks immediately."
        )

    # 2. Compressed preparation window warning
    days_until_event = (event_date - ref_date).days
    max_template_lead = max(item.days_before_event for item in template_items)
    ev_type_val = event_type.value if isinstance(event_type, EventType) else str(event_type)
    if 0 <= days_until_event < max_template_lead:
        warnings.append(
            f"Event is scheduled in {days_until_event} day(s), which is shorter than the standard "
            f"{max_template_lead}-day planning window for a {ev_type_val}. Some earlier milestones are pre-due."
        )

    return EventTimelineScheduleResponse(
        event_id=event_id,
        event_date=event_date,
        generated_at=now_utc,
        milestones=sorted_milestones,
        warnings=warnings,
    )


# Descriptive alias to distinguish from fallback_service.generate_deterministic_timeline
generate_event_timeline_schedule = generate_deterministic_timeline

