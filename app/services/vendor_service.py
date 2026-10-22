"""Event-specific vendor checklist and coordination engine for PlanProof AI.

Critical Invariants:
1. This is a planning and tracking workflow, NOT a vendor marketplace.
2. Real vendor businesses, bookings, availability, phone numbers, or confirmed reservations
   must NEVER be invented or automatically populated.
3. Every checklist item starts with booking_status='not_started' and vendor_name=None.
4. Due dates are computed strictly via deterministic calendar arithmetic when an event_date
   exists. If event_date is missing, due_date is None (never fabricated).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.schemas import (
    EventType,
    EventVendorChecklistItem,
    VendorBookingStatus,
    VendorChecklistCategory,
    VendorChecklistPriority,
    VendorChecklistStatus,
    VendorChecklistSummary,
)


@dataclass(frozen=True)
class VendorTemplateItem:
    """Template definition for a vendor coordination checklist item."""

    id: str
    category: VendorChecklistCategory
    title: str
    description: str
    days_before_event: int
    priority: VendorChecklistPriority


# ==============================================================================
# 1. Event-Specific Vendor Coordination Templates
# ==============================================================================


WEDDING_VENDOR_TEMPLATE: tuple[VendorTemplateItem, ...] = (
    VendorTemplateItem(
        id="VCL-WED-01",
        category=VendorChecklistCategory.VENUE_PERMISSIONS,
        title="Reserve wedding banquet hall / lawn & mandap premises",
        description="Inspect venue capacity, negotiate dining & mandap zones, verify advance terms, and secure municipal sound permissions.",
        days_before_event=150,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-WED-02",
        category=VendorChecklistCategory.CATERING_REFRESHMENTS,
        title="Contract wedding caterer and finalize multi-meal menus",
        description="Sample food tastings, lock in regional live counters, guaranteed guest plate count, and service staff ratios.",
        days_before_event=120,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-WED-03",
        category=VendorChecklistCategory.PHOTOGRAPHY_VIDEOGRAPHY,
        title="Book wedding photographer and cinematography crew",
        description="Lock in candid photographers, traditional videographers, drone operator permissions, and album delivery timelines.",
        days_before_event=90,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-WED-04",
        category=VendorChecklistCategory.ATTIRE_BEAUTY,
        title="Finalize bridal/groom attire fittings & bridal makeup artist",
        description="Schedule lehenga/sherwani tailoring sessions and secure bridal makeup artist for sangeet and wedding morning.",
        days_before_event=75,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-WED-05",
        category=VendorChecklistCategory.DECORATION_SETUP,
        title="Approve stage decor, mandap florals & lighting design",
        description="Review 3D floral sketches, mandap backdrop, guest table centerpieces, entrance arch, and generator power loads.",
        days_before_event=60,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-WED-06",
        category=VendorChecklistCategory.INVITATIONS_COORDINATION,
        title="Order wedding invitation cards & manage digital dispatch",
        description="Print formal family wedding invitations, set up RSVP tracking list, and send digital save-the-date cards.",
        days_before_event=60,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-WED-07",
        category=VendorChecklistCategory.ENTERTAINMENT_EQUIPMENT,
        title="Book DJ, sangeet audio equipment & live performers",
        description="Contract sound console, stage microphones, DJ playlist, and traditional dhol/shehnai welcome artists.",
        days_before_event=45,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-WED-08",
        category=VendorChecklistCategory.TRANSPORT_LOGISTICS,
        title="Coordinate guest hotel room blocks & airport transit",
        description="Reserve outstation guest accommodation rooms and arrange local airport/railway station pick-up cabs.",
        days_before_event=30,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-WED-09",
        category=VendorChecklistCategory.CLEANUP_POST_EVENT,
        title="Schedule mandap teardown, floral disposal & venue handover",
        description="Arrange post-wedding waste clearance, floral compost collection, venue deposit settlement, and item return.",
        days_before_event=1,
        priority=VendorChecklistPriority.HIGH,
    ),
)


BIRTHDAY_VENDOR_TEMPLATE: tuple[VendorTemplateItem, ...] = (
    VendorTemplateItem(
        id="VCL-BDY-01",
        category=VendorChecklistCategory.VENUE_PERMISSIONS,
        title="Book party hall, restaurant space or society clubhouse",
        description="Reserve party venue for target hours, confirm music policy, refrigeration for cake, and setup time window.",
        days_before_event=21,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-BDY-02",
        category=VendorChecklistCategory.INVITATIONS_COORDINATION,
        title="Design digital birthday invitations and track parent RSVPs",
        description="Create themed invitation cards, share location map on WhatsApp, and track kid & adult guest headcount.",
        days_before_event=14,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-BDY-03",
        category=VendorChecklistCategory.PHOTOGRAPHY_VIDEOGRAPHY,
        title="Arrange event photographer for cake cutting & family candids",
        description="Confirm photographer arrival time, cake cutting highlight coverage, and digital raw photo handoff schedule.",
        days_before_event=14,
        priority=VendorChecklistPriority.LOW,
    ),
    VendorTemplateItem(
        id="VCL-BDY-04",
        category=VendorChecklistCategory.CATERING_REFRESHMENTS,
        title="Order custom themed birthday cake and party food buffet",
        description="Book bakery for custom tier cake, arrange kids finger foods, beverage station, and dietary-friendly snacks.",
        days_before_event=12,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-BDY-05",
        category=VendorChecklistCategory.ENTERTAINMENT_EQUIPMENT,
        title="Contract party game host, mascot entertainer or magician",
        description="Book interactive entertainer, confirm game props/prizes, sound speaker, and musical playlist.",
        days_before_event=10,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-BDY-06",
        category=VendorChecklistCategory.DECORATION_SETUP,
        title="Coordinate theme balloon arch, backdrop & table decor",
        description="Select color palette, balloon garland styling, personalized name banner, and photo booth cutouts.",
        days_before_event=7,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-BDY-07",
        category=VendorChecklistCategory.TRANSPORT_LOGISTICS,
        title="Assemble personalized return gift hampers & favor bags",
        description="Procure age-appropriate return gifts, assemble goodie bags with name tags, and transport to venue.",
        days_before_event=3,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-BDY-08",
        category=VendorChecklistCategory.CLEANUP_POST_EVENT,
        title="Manage party space trash collection & decor teardown",
        description="Pack personal gifts, disassemble balloon backdrop, clear food packaging, and settle venue security deposit.",
        days_before_event=1,
        priority=VendorChecklistPriority.HIGH,
    ),
)


COMMUNITY_VENDOR_TEMPLATE: tuple[VendorTemplateItem, ...] = (
    VendorTemplateItem(
        id="VCL-COM-01",
        category=VendorChecklistCategory.VENUE_PERMISSIONS,
        title="Secure community ground/auditorium & municipal/police permits",
        description="File local authority sound permissions, police NOC, society ground reservation, and fire safety compliance.",
        days_before_event=45,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-COM-02",
        category=VendorChecklistCategory.ENTERTAINMENT_EQUIPMENT,
        title="Rent heavy-duty PA sound system, mics & backup generator",
        description="Contract sound vendor for podium microphones, loudspeaker array, stage lighting, and diesel generator backup.",
        days_before_event=30,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-COM-03",
        category=VendorChecklistCategory.INVITATIONS_COORDINATION,
        title="Issue community circulars, banner displays & digital alerts",
        description="Print noticeboard flyers, distribute neighborhood WhatsApp broadcasts, and erect entrance announcement banner.",
        days_before_event=21,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-COM-04",
        category=VendorChecklistCategory.DECORATION_SETUP,
        title="Erect stage canopy, seating shamiana & registration booth",
        description="Setup weatherproof stage tent, rows of folding chairs, registration counter tables, and directional signage.",
        days_before_event=14,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-COM-05",
        category=VendorChecklistCategory.TRANSPORT_LOGISTICS,
        title="Brief volunteer teams, parking stewards & elderly access routes",
        description="Assign volunteer badges, designate traffic/parking marshals, and verify wheelchair/elderly ramp accessibility.",
        days_before_event=14,
        priority=VendorChecklistPriority.MEDIUM,
    ),
    VendorTemplateItem(
        id="VCL-COM-06",
        category=VendorChecklistCategory.CATERING_REFRESHMENTS,
        title="Order community drinking water cans, prasad & meal boxes",
        description="Arrange certified mineral water dispensers, disposable compostable cups, and bulk meal distribution counters.",
        days_before_event=10,
        priority=VendorChecklistPriority.HIGH,
    ),
    VendorTemplateItem(
        id="VCL-COM-07",
        category=VendorChecklistCategory.PHOTOGRAPHY_VIDEOGRAPHY,
        title="Assign official event photographer & community archive team",
        description="Brief volunteer/pro photographer on VIP felicitation, stage speeches, crowd candids, and newsletter release.",
        days_before_event=7,
        priority=VendorChecklistPriority.LOW,
    ),
    VendorTemplateItem(
        id="VCL-COM-08",
        category=VendorChecklistCategory.CLEANUP_POST_EVENT,
        title="Deploy eco waste segregation bins & grounds restoration team",
        description="Position dry/wet trash bins, supervise volunteer cleanup squad, return rented audio gear, and inspect grounds.",
        days_before_event=1,
        priority=VendorChecklistPriority.HIGH,
    ),
)


VENDOR_CHECKLIST_TEMPLATES: dict[EventType, tuple[VendorTemplateItem, ...]] = {
    EventType.WEDDING: WEDDING_VENDOR_TEMPLATE,
    EventType.BIRTHDAY: BIRTHDAY_VENDOR_TEMPLATE,
    EventType.COMMUNITY_EVENT: COMMUNITY_VENDOR_TEMPLATE,
}


def get_vendor_template_for_event_type(
    event_type: EventType | str,
) -> tuple[VendorTemplateItem, ...]:
    """Retrieve the vendor coordination checklist template for a given event type.

    Raises:
        ValueError: If event_type is not a recognized EventType.
    """
    if isinstance(event_type, EventType):
        resolved = event_type
    else:
        try:
            resolved = EventType(event_type)
        except ValueError as exc:
            raise ValueError(f"Unsupported event type for vendor checklist: '{event_type}'") from exc

    template = VENDOR_CHECKLIST_TEMPLATES.get(resolved)
    if template is None:
        raise ValueError(f"No vendor checklist template configured for event type: '{resolved}'")
    return template


# ==============================================================================
# 2. Checklist Generation and Recalculation Helpers
# ==============================================================================


def generate_event_vendor_checklist(
    event_id: str,
    event_type: EventType | str,
    event_date: date | None,
    created_at: datetime | None = None,
) -> list[EventVendorChecklistItem]:
    """Generate initial event-specific vendor checklist items using deterministic templates.

    Rules:
    - Never automatically marks vendors as booked (booking_status=not_started).
    - Never fabricates vendor names (vendor_name=None).
    - If event_date is missing, due_date is None.
    - If event_date is present, due_date = event_date - timedelta(days=days_before_event).
    """
    template_items = get_vendor_template_for_event_type(event_type)
    now = created_at or datetime.now(timezone.utc)
    items: list[EventVendorChecklistItem] = []

    for item in template_items:
        due_date = (
            event_date - timedelta(days=item.days_before_event)
            if event_date is not None
            else None
        )
        items.append(
            EventVendorChecklistItem(
                id=item.id,
                category=item.category,
                title=item.title,
                description=item.description,
                status=VendorChecklistStatus.PENDING,
                due_date=due_date,
                days_before_event=item.days_before_event,
                priority=item.priority,
                notes=None,
                vendor_name=None,
                booking_status=VendorBookingStatus.NOT_STARTED,
                created_at=now,
                updated_at=now,
            )
        )

    return items


def calculate_vendor_checklist_summary(
    items: list[EventVendorChecklistItem],
) -> VendorChecklistSummary:
    """Compute aggregated progress and booking status metrics for checklist items."""
    total_items = len(items)
    pending = sum(1 for i in items if i.status == VendorChecklistStatus.PENDING)
    in_progress = sum(1 for i in items if i.status == VendorChecklistStatus.IN_PROGRESS)
    completed = sum(1 for i in items if i.status == VendorChecklistStatus.COMPLETED)
    skipped = sum(1 for i in items if i.status == VendorChecklistStatus.SKIPPED)

    booking_counts: dict[str, int] = {
        b_status.value: sum(1 for i in items if i.booking_status == b_status)
        for b_status in VendorBookingStatus
    }

    return VendorChecklistSummary(
        total_items=total_items,
        pending=pending,
        in_progress=in_progress,
        completed=completed,
        skipped=skipped,
        booking_statuses=booking_counts,
    )


def recalculate_checklist_due_dates(
    items: list[EventVendorChecklistItem],
    new_event_date: date | None,
) -> list[EventVendorChecklistItem]:
    """Recalculate due dates across existing checklist items when event_date changes.

    Preserves user-entered notes, vendor_name, status, booking_status, and priority.
    """
    updated_items: list[EventVendorChecklistItem] = []
    now = datetime.now(timezone.utc)

    for item in items:
        if new_event_date is not None and item.days_before_event is not None:
            new_due_date = new_event_date - timedelta(days=item.days_before_event)
        else:
            new_due_date = None

        updated_items.append(
            EventVendorChecklistItem(
                id=item.id,
                category=item.category,
                title=item.title,
                description=item.description,
                status=item.status,
                due_date=new_due_date,
                days_before_event=item.days_before_event,
                priority=item.priority,
                notes=item.notes,
                vendor_name=item.vendor_name,
                booking_status=item.booking_status,
                created_at=item.created_at,
                updated_at=now,
            )
        )

    return updated_items
