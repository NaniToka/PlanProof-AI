"""Event profile service and in-memory repository for PlanProof AI.

Handles:
- Ephemeral in-memory event profile storage with capacity management.
- Creation, retrieval, pagination, and partial update (PATCH) of event profiles.
- Automatic integration with the deterministic budget engine (Hamilton-Hare method).
- Safe logging preserving user privacy (no customer notes or PII logged).
- Strict protection of server-generated fields (event_id, created_at, updated_at).

Note on Storage:
    The in-memory store is purely ephemeral for development, testing, and live demonstrations.
    All event data is lost when the server process terminates or restarts.
    It does not write to disks or external databases.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.config import AIMode, Settings, get_settings
from app.data_loader import DatasetRepository
from app.schemas import (
    CANONICAL_BUDGET_CATEGORIES,
    AIResultEnvelope,
    AIResultSource,
    AIResultStatus,
    AITask,
    BudgetRebalanceResponse,
    CouncilSource,
    EventBudgetPlanResponse,
    EventCreateRequest,
    EventFamilyCouncilResponse,
    EventIdeasResponse,
    EventMilestone,
    EventProfile,
    EventRisksResponse,
    EventTimelineScheduleResponse,
    EventUpdateRequest,
    EventVendorChecklistItem,
    EventVendorChecklistResponse,
    IdeaCategory,
    IdeaSource,
    MilestoneStatus,
    RiskCategory,
    RiskSource,
    VendorChecklistItemUpdateRequest,
    get_current_ist_date,
    validate_event_date,
    CrisisEvaluationRequest,
    EventCrisisRecoveryResponse,
    CrisisRecoveryRecord,
    RecoveryActionStatus,
    RecoveryProgressSummary,
    RecoveryRecordCreateRequest,
    RecoveryRecordUpdateRequest,
    RecoveryStatus,
    TrackedActionInput,
    TrackedActionUpdateRequest,
    TrackedRecoveryAction,
    EventReadinessResponse,
)
from app.services.readiness_service import ReadinessService
from app.services.budget import (
    calculate_initial_budget,
    compute_budget_warnings,
    generate_budget_explanation,
    rebalance_budget,
)
from app.services.timeline import (
    generate_event_timeline_schedule,
    get_template_for_event_type,
)
from app.services.recommendation_service import (
    build_event_ideas_prompt,
)
from app.services.council_service import (
    build_family_council_prompt,
    generate_event_family_council,
)
from app.services.risk_service import (
    analyze_event_risks,
    build_event_risks_prompt,
)
from app.services.vendor_service import (
    calculate_vendor_checklist_summary,
    generate_event_vendor_checklist,
    recalculate_checklist_due_dates,
)
from app.services.crisis_service import (
    evaluate_event_crisis,
)

from app.repositories import BaseEventRepository, InMemoryEventRepository

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Ephemeral In-Memory Event Store (Backward-Compatible Repository Adapter)
# ==============================================================================


class EventStore(InMemoryEventRepository):
    """Thread-safe, ephemeral in-memory storage for event profiles.

    Caution:
        Data stored here is ephemeral and is wiped when the process restarts.
        Never describe or use this as permanent or production storage.
    """
    pass


# ==============================================================================
# 2. Event Profile Domain Service
# ==============================================================================


class EventService:
    """Domain service managing core event profile workflows and budget calculations."""

    def __init__(
        self,
        store: BaseEventRepository | None = None,
        dataset_repo: DatasetRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize event service with repository and optional dataset dependencies."""
        self.store: BaseEventRepository = store or EventStore()
        self.dataset_repo = dataset_repo
        self.settings = settings or get_settings()

    async def create_event(
        self, request: EventCreateRequest, user_id: UUID | None = None
    ) -> EventProfile:
        """Create a new event profile, calculate its initial budget, and store it.

        Args:
            request: Validated event creation request data.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            The created EventProfile populated with server-generated ID, timestamps,
            and deterministic 8-category budget allocation.
        """
        now = datetime.now(timezone.utc)
        event_id = f"EV-{uuid4().hex[:12].upper()}"

        # Deterministic 8-category budget calculation via Hamilton-Hare method
        splits = self.dataset_repo.budget_splits if self.dataset_repo else None
        budget_outcome = calculate_initial_budget(
            event_type=request.event_type,
            city_tier=request.city_tier,
            total_budget_inr=request.total_budget_inr,
            splits_dataset=splits,
        )

        vendor_checklist = generate_event_vendor_checklist(
            event_id=event_id,
            event_type=request.event_type,
            event_date=request.event_date,
            created_at=now,
        )

        profile = EventProfile(
            event_id=event_id,
            user_id=user_id,
            event_type=request.event_type,
            event_name=request.event_name,
            city=request.city,
            city_tier=request.city_tier,
            event_date=request.event_date,
            guest_count=request.guest_count,
            total_budget_inr=request.total_budget_inr,
            language=request.language,
            theme_notes=request.theme_notes,
            is_in_progress=request.is_in_progress,
            budget=budget_outcome.allocations,
            vendor_checklist=vendor_checklist,
            created_at=now,
            updated_at=now,
        )

        await self.store.create(profile, user_id=user_id)
        # Safe logging: Never log customer theme notes, PII, or free text
        logger.info(
            "Created event profile %s (type=%s, tier=%s, guests=%d)",
            event_id,
            profile.event_type.value,
            profile.city_tier.value,
            profile.guest_count,
        )
        return profile

    async def get_event(
        self, event_id: str, user_id: UUID | None = None
    ) -> EventProfile | None:
        """Retrieve an event profile by event_id, scoped to user_id if provided."""
        return await self.store.get(event_id, user_id=user_id)

    async def update_event(
        self,
        event_id: str,
        request: EventUpdateRequest,
        user_id: UUID | None = None,
    ) -> EventProfile | None:
        """Apply partial updates to an existing event profile and recompute budget if needed.

        Args:
            event_id: Unique event identifier.
            request: Fields to update.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            Updated EventProfile, or None if the event does not exist.
        """
        existing = await self.store.get(event_id, user_id=user_id)
        if existing is None:
            return None

        update_data = request.model_dump(exclude_unset=True)
        if not update_data:
            return existing

        # Validate date if date or in-progress flag changed
        new_date = update_data.get("event_date", existing.event_date)
        new_in_progress = update_data.get("is_in_progress", existing.is_in_progress)
        if "event_date" in update_data:
            validate_event_date(new_date, allow_past=new_in_progress)

        # Check if budget recalculation is required
        recompute_budget = any(
            k in update_data for k in ("total_budget_inr", "city_tier", "event_type")
        )

        target_event_type = update_data.get("event_type", existing.event_type)
        target_city_tier = update_data.get("city_tier", existing.city_tier)
        target_budget_inr = update_data.get("total_budget_inr", existing.total_budget_inr)

        if recompute_budget:
            splits = self.dataset_repo.budget_splits if self.dataset_repo else None
            budget_outcome = calculate_initial_budget(
                event_type=target_event_type,
                city_tier=target_city_tier,
                total_budget_inr=target_budget_inr,
                splits_dataset=splits,
            )
            new_budget = budget_outcome.allocations
        else:
            new_budget = existing.budget

        # Recalculate vendor checklist due dates if event_date changed
        if new_date != existing.event_date:
            updated_checklist = recalculate_checklist_due_dates(
                existing.vendor_checklist, new_date
            )
        else:
            updated_checklist = list(existing.vendor_checklist)

        now = datetime.now(timezone.utc)

        # Build updated profile preserving server-generated fields and owner identity
        updated_profile = EventProfile(
            event_id=existing.event_id,  # Immutable
            user_id=existing.user_id,  # Immutable
            event_type=target_event_type,
            event_name=update_data.get("event_name", existing.event_name),
            city=update_data.get("city", existing.city),
            city_tier=target_city_tier,
            event_date=new_date,
            guest_count=update_data.get("guest_count", existing.guest_count),
            total_budget_inr=target_budget_inr,
            language=update_data.get("language", existing.language),
            theme_notes=update_data.get("theme_notes", existing.theme_notes),
            is_in_progress=new_in_progress,
            budget=new_budget,
            milestone_statuses=dict(existing.milestone_statuses),
            vendor_checklist=updated_checklist,
            created_at=existing.created_at,  # Immutable
            updated_at=now,  # Updated timestamp
        )

        await self.store.update(event_id, updated_profile, user_id=user_id)
        logger.info("Updated event profile %s", event_id)
        return updated_profile

    async def delete_event_profile(
        self, event_id: str, user_id: UUID | None = None
    ) -> bool:
        """Delete an event profile and its associated data, scoped to user_id."""
        deleted = await self.store.delete(event_id, user_id=user_id)
        if deleted:
            logger.info("Deleted event profile %s", event_id)
        return deleted

    async def list_events(
        self, skip: int = 0, limit: int = 50, user_id: UUID | None = None
    ) -> tuple[list[EventProfile], int]:
        """Return a paginated list of active event profiles and total count for user."""
        return await self.store.list(skip=skip, limit=limit, user_id=user_id)

    async def get_event_budget_plan(
        self, event_id: str, user_id: UUID | None = None
    ) -> EventBudgetPlanResponse | None:
        """Retrieve the deterministic budget plan for a saved event profile.

        Args:
            event_id: Unique event identifier.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            EventBudgetPlanResponse if event exists, None otherwise.
        """
        profile = await self.store.get(event_id, user_id=user_id)
        if profile is None:
            return None

        # If profile doesn't have budget (defensive check), calculate it
        if profile.budget is None:
            splits = self.dataset_repo.budget_splits if self.dataset_repo else None
            calc_resp = calculate_initial_budget(
                event_type=profile.event_type,
                city_tier=profile.city_tier,
                total_budget_inr=profile.total_budget_inr,
                splits_dataset=splits,
            )
            allocations = calc_resp.allocations
        else:
            allocations = profile.budget

        # Compute exact percentages from actual integer allocations
        percentages: dict[str, float] = {
            cat: round((getattr(allocations, cat) / profile.total_budget_inr) * 100.0, 2)
            for cat in CANONICAL_BUDGET_CATEGORIES
        }

        # Deterministic constraint warnings
        warnings = compute_budget_warnings(
            total_budget_inr=profile.total_budget_inr,
            guest_count=profile.guest_count,
            event_type=profile.event_type,
            allocations=allocations,
        )

        # Deterministic explanatory narrative
        explanation = generate_budget_explanation(
            total_budget_inr=profile.total_budget_inr,
            event_type=profile.event_type,
            city_tier=profile.city_tier,
            allocations=allocations,
            percentages=percentages,
        )

        return EventBudgetPlanResponse(
            event_id=profile.event_id,
            total_budget_inr=profile.total_budget_inr,
            currency="INR",
            allocations=allocations,
            allocation_percentages=percentages,
            remaining_budget_inr=0,
            warnings=warnings,
            explanation=explanation,
        )

    async def rebalance_event_budget(
        self,
        event_id: str,
        new_total_budget_inr: int,
        strict_protect: bool = False,
        user_id: UUID | None = None,
    ) -> BudgetRebalanceResponse | None:
        """Rebalance an existing event profile's budget using priority-based category trimming.

        Args:
            event_id: Unique event identifier.
            new_total_budget_inr: Target new budget in INR.
            strict_protect: If True, disallow cuts to catering and buffer reserve.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            BudgetRebalanceResponse if event exists, None otherwise.
        """
        profile = await self.store.get(event_id, user_id=user_id)
        if profile is None:
            return None

        rebalance_resp = rebalance_budget(
            current_allocations=profile.budget,
            new_total_budget_inr=new_total_budget_inr,
            strict_protect=strict_protect,
        )

        # Update profile with new budget and timestamp
        now = datetime.now(timezone.utc)
        updated_profile = EventProfile(
            event_id=profile.event_id,
            user_id=profile.user_id,
            event_type=profile.event_type,
            event_name=profile.event_name,
            city=profile.city,
            city_tier=profile.city_tier,
            event_date=profile.event_date,
            guest_count=profile.guest_count,
            total_budget_inr=new_total_budget_inr,
            language=profile.language,
            theme_notes=profile.theme_notes,
            is_in_progress=profile.is_in_progress,
            budget=rebalance_resp.allocations,
            milestone_statuses=dict(profile.milestone_statuses),
            vendor_checklist=list(profile.vendor_checklist),
            created_at=profile.created_at,
            updated_at=now,
        )
        await self.store.update(event_id, updated_profile, user_id=user_id)
        logger.info(
            "Rebalanced event profile %s budget to INR %d",
            event_id,
            new_total_budget_inr,
        )
        return rebalance_resp

    async def get_event_timeline(
        self,
        event_id: str,
        reference_date: date | None = None,
        user_id: UUID | None = None,
    ) -> EventTimelineScheduleResponse | None:
        """Generate and retrieve the deterministic timeline for a saved event profile.

        Args:
            event_id: Unique event identifier.
            reference_date: Optional simulated 'today' for testing.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            EventTimelineScheduleResponse if event exists, None otherwise.
        """
        profile = await self.store.get(event_id, user_id=user_id)
        if profile is None:
            return None

        return generate_event_timeline_schedule(
            event_id=profile.event_id,
            event_type=profile.event_type,
            event_date=profile.event_date,
            milestone_statuses=profile.milestone_statuses,
            reference_date=reference_date,
        )

    async def update_milestone_status(
        self,
        event_id: str,
        milestone_id: str,
        status: MilestoneStatus,
        reference_date: date | None = None,
        user_id: UUID | None = None,
    ) -> EventMilestone | None:
        """Update completion status of a timeline milestone in ephemeral storage.

        Args:
            event_id: Unique event identifier.
            milestone_id: Milestone identifier (must belong to event type template).
            status: New status (pending or completed).
            reference_date: Optional simulated reference date for testing.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            Updated EventMilestone, or None if event not found.

        Raises:
            ValueError: If event_date is missing on profile.
            KeyError: If milestone_id does not exist in template for event type.
        """
        profile = await self.store.get(event_id, user_id=user_id)
        if profile is None:
            return None

        if profile.event_date is None:
            raise ValueError(
                f"Cannot update milestone status for event '{event_id}' because event_date is not set. "
                f"Set an event_date first via PATCH /api/v1/events/{event_id}."
            )

        template_items = get_template_for_event_type(profile.event_type)
        matching_item = next(
            (item for item in template_items if item.milestone_id == milestone_id),
            None,
        )
        if matching_item is None:
            raise KeyError(
                f"Milestone '{milestone_id}' is not a valid milestone for {profile.event_type.value}."
            )

        # Update the milestone status mapping
        updated_statuses = dict(profile.milestone_statuses)
        updated_statuses[milestone_id] = status

        now = datetime.now(timezone.utc)
        updated_profile = EventProfile(
            event_id=profile.event_id,
            user_id=profile.user_id,
            event_type=profile.event_type,
            event_name=profile.event_name,
            city=profile.city,
            city_tier=profile.city_tier,
            event_date=profile.event_date,
            guest_count=profile.guest_count,
            total_budget_inr=profile.total_budget_inr,
            language=profile.language,
            theme_notes=profile.theme_notes,
            is_in_progress=profile.is_in_progress,
            budget=profile.budget,
            milestone_statuses=updated_statuses,
            vendor_checklist=list(profile.vendor_checklist),
            created_at=profile.created_at,
            updated_at=now,
        )
        await self.store.update(event_id, updated_profile, user_id=user_id)

        # Build and return the updated milestone object
        ref_date = reference_date or get_current_ist_date()
        due_date = profile.event_date - timedelta(days=matching_item.days_before_event)
        is_overdue = (due_date < ref_date) and (status != MilestoneStatus.COMPLETED)

        logger.info(
            "Updated milestone %s status to %s for event %s",
            milestone_id,
            status.value,
            event_id,
        )

        return EventMilestone(
            milestone_id=matching_item.milestone_id,
            title=matching_item.title,
            description=matching_item.description,
            category=matching_item.category,
            due_date=due_date,
            days_before_event=matching_item.days_before_event,
            priority=matching_item.priority,
            status=status,
            is_overdue=is_overdue,
        )

    async def get_event_vendor_checklist(
        self,
        event_id: str,
        user_id: UUID | None = None,
    ) -> EventVendorChecklistResponse | None:
        """Retrieve or lazily initialize the vendor checklist for a saved event.

        Args:
            event_id: Unique event identifier.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            EventVendorChecklistResponse if event exists, None otherwise.
        """
        profile = await self.store.get(event_id, user_id=user_id)
        if profile is None:
            return None

        # Lazily generate checklist if not already present on profile
        if not profile.vendor_checklist:
            checklist = generate_event_vendor_checklist(
                event_id=profile.event_id,
                event_type=profile.event_type,
                event_date=profile.event_date,
            )
            now = datetime.now(timezone.utc)
            updated_profile = EventProfile(
                event_id=profile.event_id,
                user_id=profile.user_id,
                event_type=profile.event_type,
                event_name=profile.event_name,
                city=profile.city,
                city_tier=profile.city_tier,
                event_date=profile.event_date,
                guest_count=profile.guest_count,
                total_budget_inr=profile.total_budget_inr,
                language=profile.language,
                theme_notes=profile.theme_notes,
                is_in_progress=profile.is_in_progress,
                budget=profile.budget,
                milestone_statuses=profile.milestone_statuses,
                vendor_checklist=checklist,
                created_at=profile.created_at,
                updated_at=now,
            )
            await self.store.update(event_id, updated_profile, user_id=user_id)
            profile = updated_profile

        summary = calculate_vendor_checklist_summary(profile.vendor_checklist)
        warnings: list[str] = []
        if profile.event_date is None:
            warnings.append(
                "Event date is not set on this profile. Add an event_date via "
                f"PATCH /api/v1/events/{event_id} to derive calendar deadlines for checklist tasks."
            )

        now_utc = datetime.now(timezone.utc)
        return EventVendorChecklistResponse(
            event_id=profile.event_id,
            event_type=profile.event_type,
            event_date=profile.event_date,
            generated_at=now_utc,
            summary=summary,
            items=profile.vendor_checklist,
            warnings=warnings,
        )

    async def update_vendor_checklist_item(
        self,
        event_id: str,
        item_id: str,
        request: VendorChecklistItemUpdateRequest,
        user_id: UUID | None = None,
    ) -> EventVendorChecklistItem | None:
        """Apply updates to a specific vendor checklist item in ephemeral storage.

        Args:
            event_id: Unique event identifier.
            item_id: Checklist item identifier.
            request: Validated fields to update.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            Updated EventVendorChecklistItem, or None if event not found.

        Raises:
            KeyError: If item_id does not exist in the event's checklist.
        """
        profile = await self.store.get(event_id, user_id=user_id)
        if profile is None:
            return None

        # Lazily initialize checklist if empty
        if not profile.vendor_checklist:
            checklist = generate_event_vendor_checklist(
                event_id=profile.event_id,
                event_type=profile.event_type,
                event_date=profile.event_date,
            )
            profile = EventProfile(
                event_id=profile.event_id,
                user_id=profile.user_id,
                event_type=profile.event_type,
                event_name=profile.event_name,
                city=profile.city,
                city_tier=profile.city_tier,
                event_date=profile.event_date,
                guest_count=profile.guest_count,
                total_budget_inr=profile.total_budget_inr,
                language=profile.language,
                theme_notes=profile.theme_notes,
                is_in_progress=profile.is_in_progress,
                budget=profile.budget,
                milestone_statuses=profile.milestone_statuses,
                vendor_checklist=checklist,
                created_at=profile.created_at,
                updated_at=datetime.now(timezone.utc),
            )
            await self.store.update(event_id, profile, user_id=user_id)

        matching_item = next(
            (item for item in profile.vendor_checklist if item.id == item_id),
            None,
        )
        if matching_item is None:
            raise KeyError(
                f"Vendor checklist item '{item_id}' not found for event '{event_id}'."
            )

        update_data = request.model_dump(exclude_unset=True)
        if not update_data:
            return matching_item

        now = datetime.now(timezone.utc)
        new_status = update_data.get("status", matching_item.status)
        new_priority = update_data.get("priority", matching_item.priority)
        new_booking_status = update_data.get(
            "booking_status", matching_item.booking_status
        )
        new_notes = update_data.get("notes", matching_item.notes)
        new_vendor_name = update_data.get("vendor_name", matching_item.vendor_name)

        updated_item = EventVendorChecklistItem(
            id=matching_item.id,
            category=matching_item.category,
            title=matching_item.title,
            description=matching_item.description,
            status=new_status,
            due_date=matching_item.due_date,
            days_before_event=matching_item.days_before_event,
            priority=new_priority,
            notes=new_notes,
            vendor_name=new_vendor_name,
            booking_status=new_booking_status,
            created_at=matching_item.created_at,
            updated_at=now,
        )

        updated_checklist = [
            updated_item if i.id == item_id else i for i in profile.vendor_checklist
        ]

        updated_profile = EventProfile(
            event_id=profile.event_id,
            user_id=profile.user_id,
            event_type=profile.event_type,
            event_name=profile.event_name,
            city=profile.city,
            city_tier=profile.city_tier,
            event_date=profile.event_date,
            guest_count=profile.guest_count,
            total_budget_inr=profile.total_budget_inr,
            language=profile.language,
            theme_notes=profile.theme_notes,
            is_in_progress=profile.is_in_progress,
            budget=profile.budget,
            milestone_statuses=profile.milestone_statuses,
            vendor_checklist=updated_checklist,
            created_at=profile.created_at,
            updated_at=now,
        )
        await self.store.update(event_id, updated_profile, user_id=user_id)

        # Privacy-safe logging: Never log user-entered notes or vendor contact names
        logger.info(
            "Updated vendor checklist item %s (status=%s, booking=%s) for event %s",
            item_id,
            updated_item.status.value,
            updated_item.booking_status.value,
            event_id,
        )

        return updated_item

    async def get_event_ideas(
        self,
        event_id: str,
        orchestrator: Any,
        category: IdeaCategory | None = None,
        limit: int = 10,
        user_id: UUID | None = None,
    ) -> AIResultEnvelope[EventIdeasResponse] | None:
        """Generate personalized event recommendations via AI orchestration with deterministic fallback.

        Args:
            event_id: Target event profile identifier.
            orchestrator: Application AI orchestrator handling mode and fallbacks.
            category: Optional category filter.
            limit: Maximum count of recommendations to return.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            AIResultEnvelope containing EventIdeasResponse, or None if event not found.
        """
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        prompt, system_instruction = build_event_ideas_prompt(profile)
        envelope: AIResultEnvelope[EventIdeasResponse] = await orchestrator.orchestrate(
            task=AITask.PERSONALIZED_IDEAS,
            response_schema=EventIdeasResponse,
            prompt=prompt,
            system_instruction=system_instruction,
            request_data=profile,
        )

        if envelope.data is not None:
            # Attribute item source correctly based on envelope source
            target_source = IdeaSource.RULES
            if envelope.source == AIResultSource.GEMINI:
                target_source = IdeaSource.GEMINI
            elif envelope.source == AIResultSource.DEMO:
                target_source = IdeaSource.DEMO

            for item in envelope.data.ideas:
                item.source = target_source

            # Category filter
            if category is not None:
                envelope.data.ideas = [
                    i for i in envelope.data.ideas if i.category == category
                ]

            # Bounded limit
            if limit and limit > 0:
                envelope.data.ideas = envelope.data.ideas[:limit]

            envelope.data.total_ideas = len(envelope.data.ideas)

        return envelope

    async def get_event_risks(
        self,
        event_id: str,
        orchestrator: Any | None = None,
        reference_date: date | None = None,
        user_id: UUID | None = None,
    ) -> AIResultEnvelope[EventRisksResponse] | None:
        """Analyze pre-mortem risks for a saved event using deterministic rules.

        Args:
            event_id: Target event profile identifier.
            orchestrator: Optional AI orchestrator for demo fixtures or Gemini enrichment.
            reference_date: Optional simulated reference date.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            AIResultEnvelope containing EventRisksResponse, or None if event not found.
        """
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        # 1. Deterministic baseline analysis
        active_mode = getattr(orchestrator, "mode", None) if orchestrator else None
        source_val = RiskSource.DEMO if active_mode == AIMode.DEMO else RiskSource.RULES
        risks_res = analyze_event_risks(
            profile=profile,
            reference_date=reference_date,
            source=source_val,
        )

        # 2. If no orchestrator or mode is demo/fallback, construct envelope directly
        if orchestrator is None or active_mode == AIMode.DEMO:
            envelope_source = AIResultSource.DEMO if active_mode == AIMode.DEMO else AIResultSource.DETERMINISTIC
            return AIResultEnvelope[EventRisksResponse](
                status=AIResultStatus.SUCCESS,
                source=envelope_source,
                data=risks_res,
                message="Pre-mortem risk analysis completed successfully.",
                warnings=risks_res.missing_data_warnings,
            )

        # 3. If mode is gemini
        if active_mode == AIMode.GEMINI:
            if not getattr(orchestrator.gemini_service, "is_configured", False):
                return AIResultEnvelope[EventRisksResponse](
                    status=AIResultStatus.UNAVAILABLE,
                    source=AIResultSource.GEMINI,
                    data=None,
                    message="Gemini AI is required in 'gemini' mode, but GEMINI_API_KEY is not configured.",
                    warnings=["Gemini API key is unconfigured. Fallback is disallowed in 'gemini' mode."],
                )
            prompt, system_instruction = build_event_risks_prompt(profile, risks_res.risks)
            envelope: AIResultEnvelope[EventRisksResponse] = await orchestrator.orchestrate(
                task=AITask.EVENT_RISKS,
                response_schema=EventRisksResponse,
                prompt=prompt,
                system_instruction=system_instruction,
                request_data=profile,
                fallback=lambda _req: risks_res,
            )
            if envelope.data is not None:
                for r in envelope.data.risks:
                    r.source = RiskSource.GEMINI
            return envelope

        # 4. Mode is auto: attempt Gemini enrichment if configured, otherwise return deterministic results
        if getattr(orchestrator.gemini_service, "is_configured", False):
            prompt, system_instruction = build_event_risks_prompt(profile, risks_res.risks)
            envelope = await orchestrator.orchestrate(
                task=AITask.EVENT_RISKS,
                response_schema=EventRisksResponse,
                prompt=prompt,
                system_instruction=system_instruction,
                request_data=profile,
                fallback=lambda _req: risks_res,
            )
            if envelope.data is not None and envelope.source == AIResultSource.GEMINI:
                for r in envelope.data.risks:
                    r.source = RiskSource.GEMINI
            return envelope

        # Default auto offline fallback
        return AIResultEnvelope[EventRisksResponse](
            status=AIResultStatus.FALLBACK,
            source=AIResultSource.DETERMINISTIC,
            data=risks_res,
            message="Deterministic pre-mortem risk analysis completed.",
            warnings=risks_res.missing_data_warnings,
        )

    async def get_event_family_council(
        self,
        event_id: str,
        orchestrator: AIOrchestrator | None = None,
        reference_date: date | None = None,
        user_id: UUID | None = None,
    ) -> AIResultEnvelope[EventFamilyCouncilResponse] | None:
        """Review an event plan across four distinct family council perspectives with trade-offs.

        Args:
            event_id: Target event profile identifier.
            orchestrator: Optional AI orchestrator for demo fixtures or Gemini enrichment.
            reference_date: Optional simulated reference date.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            AIResultEnvelope containing EventFamilyCouncilResponse, or None if event not found.
        """
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        # 1. Deterministic baseline family council deliberation
        active_mode = getattr(orchestrator, "mode", None) if orchestrator else None
        source_val = CouncilSource.DEMO if active_mode == AIMode.DEMO else CouncilSource.RULES

        # Gather pre-mortem risks to feed into council
        risks_res = analyze_event_risks(profile=profile, reference_date=reference_date)
        council_res = generate_event_family_council(
            profile=profile,
            risks=risks_res,
            reference_date=reference_date,
            source=source_val,
        )

        # 2. If no orchestrator or mode is demo/fallback, construct envelope directly
        if orchestrator is None or active_mode == AIMode.DEMO:
            envelope_source = AIResultSource.DEMO if active_mode == AIMode.DEMO else AIResultSource.DETERMINISTIC
            return AIResultEnvelope[EventFamilyCouncilResponse](
                status=AIResultStatus.SUCCESS,
                source=envelope_source,
                data=council_res,
                message="Family council review completed successfully.",
                warnings=council_res.missing_data_warnings,
            )

        # 3. If mode is gemini
        if active_mode == AIMode.GEMINI:
            if not getattr(orchestrator.gemini_service, "is_configured", False):
                return AIResultEnvelope[EventFamilyCouncilResponse](
                    status=AIResultStatus.UNAVAILABLE,
                    source=AIResultSource.GEMINI,
                    data=None,
                    message="Gemini AI is required in 'gemini' mode, but GEMINI_API_KEY is not configured.",
                    warnings=["Gemini API key is unconfigured. Fallback is disallowed in 'gemini' mode."],
                )
            prompt, system_instruction = build_family_council_prompt(profile, council_res.personas)
            envelope: AIResultEnvelope[EventFamilyCouncilResponse] = await orchestrator.orchestrate(
                task=AITask.FAMILY_COUNCIL,
                response_schema=EventFamilyCouncilResponse,
                prompt=prompt,
                system_instruction=system_instruction,
                request_data=profile,
                fallback=lambda _req: council_res,
            )
            if envelope.data is not None:
                for p in envelope.data.personas:
                    p.source = CouncilSource.GEMINI
            return envelope

        # 4. Mode is auto: attempt Gemini enrichment if configured, otherwise return deterministic results
        if getattr(orchestrator.gemini_service, "is_configured", False):
            prompt, system_instruction = build_family_council_prompt(profile, council_res.personas)
            envelope = await orchestrator.orchestrate(
                task=AITask.FAMILY_COUNCIL,
                response_schema=EventFamilyCouncilResponse,
                prompt=prompt,
                system_instruction=system_instruction,
                request_data=profile,
                fallback=lambda _req: council_res,
            )
            if envelope.data is not None and envelope.source == AIResultSource.GEMINI:
                for p in envelope.data.personas:
                    p.source = CouncilSource.GEMINI
            return envelope

        # Default auto offline fallback
        return AIResultEnvelope[EventFamilyCouncilResponse](
            status=AIResultStatus.FALLBACK,
            source=AIResultSource.DETERMINISTIC,
            data=council_res,
            message="Deterministic family council deliberation completed.",
            warnings=council_res.missing_data_warnings,
        )

    async def evaluate_crisis(
        self,
        event_id: str,
        request: CrisisEvaluationRequest,
        dataset_repo: DatasetRepository,
        orchestrator: AIOrchestrator | None = None,
        user_id: UUID | None = None,
    ) -> AIResultEnvelope[EventCrisisRecoveryResponse] | None:
        """Evaluate an event crisis and produce a recovery plan without mutating event resources.

        Args:
            event_id: Target event profile identifier.
            request: Crisis evaluation parameters (type, severity, description, area, phase).
            dataset_repo: In-memory dataset repository for scenario matching.
            orchestrator: Optional AI orchestrator for demo fixtures or Gemini enrichment.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            AIResultEnvelope containing EventCrisisRecoveryResponse, or None if event not found.
        """
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        return await evaluate_event_crisis(
            profile=profile,
            dataset_repo=dataset_repo,
            request=request,
            orchestrator=orchestrator,
        )

    async def save_recovery_record(
        self,
        event_id: str,
        request: RecoveryRecordCreateRequest,
        user_id: UUID | None = None,
    ) -> CrisisRecoveryRecord | None:
        """Save a validated recovery record from a generated plan and track selected actions.

        Args:
            event_id: Owning event profile identifier.
            request: Validated recovery creation payload with recovery_plan and optional actions.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            Saved CrisisRecoveryRecord, or None if the owning event profile is not found.
        """
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        now = datetime.now(timezone.utc)
        recovery_id = f"REC-{uuid4().hex[:8].upper()}"

        # Build tracked actions list with stable identifiers
        actions: list[TrackedRecoveryAction] = []
        if request.actions is not None:
            # User provided a custom or filtered list of actions
            for idx, act_input in enumerate(request.actions, start=1):
                act_id = act_input.action_id or f"ACT-{uuid4().hex[:8].upper()}"
                actions.append(
                    TrackedRecoveryAction(
                        action_id=act_id,
                        recovery_id=recovery_id,
                        title=act_input.title,
                        description=act_input.description,
                        priority=act_input.priority,
                        status=act_input.status,
                        notes=act_input.notes,
                        created_at=now,
                        updated_at=now,
                    )
                )
        else:
            # Default: extract all recommended actions from recovery plan
            counter = 1
            for item in request.recovery_plan.immediate_actions:
                actions.append(
                    TrackedRecoveryAction(
                        action_id=f"ACT-{counter:02d}",
                        recovery_id=recovery_id,
                        title=item.title,
                        description=item.action,
                        priority=item.priority,
                        status=RecoveryActionStatus.PENDING,
                        notes=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                counter += 1

            for item in request.recovery_plan.next_step_actions:
                actions.append(
                    TrackedRecoveryAction(
                        action_id=f"ACT-{counter:02d}",
                        recovery_id=recovery_id,
                        title=item.title,
                        description=item.action,
                        priority=item.priority,
                        status=RecoveryActionStatus.PENDING,
                        notes=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                counter += 1

        # Avoid marking a crisis resolved automatically merely because a recovery plan was generated
        initial_status = request.status
        if initial_status == RecoveryStatus.RESOLVED and any(
            a.status != RecoveryActionStatus.COMPLETED for a in actions
        ):
            initial_status = RecoveryStatus.OPEN

        record = CrisisRecoveryRecord(
            recovery_id=recovery_id,
            event_id=event_id,
            crisis_type=request.crisis_type,
            severity=request.severity,
            description=request.description,
            recovery_plan=request.recovery_plan,
            source=request.source,
            status=initial_status,
            actions=actions,
            created_at=now,
            updated_at=now,
        )

        recalculate_recovery_progress(record, explicit_status=initial_status)

        # Update event profile without mutating budget, timeline, or vendor checklist
        new_records = list(profile.recovery_records)
        new_records.append(record)

        updated_profile = profile.model_copy(
            update={
                "recovery_records": new_records,
                "updated_at": now,
            }
        )
        await self.store.update(event_id, updated_profile, user_id=user_id)

        logger.info(
            "Saved recovery record %s for event %s (actions=%d, source=%s)",
            recovery_id,
            event_id,
            len(actions),
            request.source,
        )
        return record

    async def list_recovery_records(
        self,
        event_id: str,
        skip: int = 0,
        limit: int = 50,
        user_id: UUID | None = None,
    ) -> list[CrisisRecoveryRecord] | None:
        """List historical recovery records for an event, sorted newest first."""
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        # Sort newest first by created_at
        sorted_records = sorted(
            profile.recovery_records,
            key=lambda r: r.created_at,
            reverse=True,
        )
        return sorted_records[skip : skip + limit]

    async def get_recovery_record(
        self,
        event_id: str,
        recovery_id: str,
        user_id: UUID | None = None,
    ) -> CrisisRecoveryRecord | None:
        """Retrieve a specific recovery record belonging to the owning event."""
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        for rec in profile.recovery_records:
            if rec.recovery_id == recovery_id:
                return rec
        return None

    async def update_recovery_record(
        self,
        event_id: str,
        recovery_id: str,
        request: RecoveryRecordUpdateRequest,
        user_id: UUID | None = None,
    ) -> CrisisRecoveryRecord | None:
        """Update supported recovery record fields (such as status and description)."""
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        target_idx = -1
        for idx, rec in enumerate(profile.recovery_records):
            if rec.recovery_id == recovery_id:
                target_idx = idx
                break

        if target_idx == -1:
            return None

        record = profile.recovery_records[target_idx]
        now = datetime.now(timezone.utc)

        new_desc = request.description if request.description is not None else record.description
        new_status = request.status if request.status is not None else record.status

        # Create updated record
        updated_rec = record.model_copy(
            update={
                "description": new_desc,
                "status": new_status,
                "updated_at": now,
            }
        )

        # Recalculate progress and retain or derive status
        recalculate_recovery_progress(updated_rec, explicit_status=new_status)

        new_records = list(profile.recovery_records)
        new_records[target_idx] = updated_rec

        updated_profile = profile.model_copy(
            update={
                "recovery_records": new_records,
                "updated_at": now,
            }
        )
        await self.store.update(event_id, updated_profile, user_id=user_id)

        logger.info(
            "Updated recovery record %s for event %s (status=%s)",
            recovery_id,
            event_id,
            updated_rec.status.value,
        )
        return updated_rec

    async def update_recovery_action(
        self,
        event_id: str,
        recovery_id: str,
        action_id: str,
        request: TrackedActionUpdateRequest,
        user_id: UUID | None = None,
    ) -> TrackedRecoveryAction | None:
        """Update an action item's status and notes, recalculating parent progress counts."""
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        target_rec_idx = -1
        for idx, rec in enumerate(profile.recovery_records):
            if rec.recovery_id == recovery_id:
                target_rec_idx = idx
                break

        if target_rec_idx == -1:
            return None

        record = profile.recovery_records[target_rec_idx]

        target_act_idx = -1
        for idx, act in enumerate(record.actions):
            if act.action_id == action_id:
                target_act_idx = idx
                break

        if target_act_idx == -1:
            return None

        action = record.actions[target_act_idx]
        now = datetime.now(timezone.utc)

        new_status = request.status if request.status is not None else action.status
        new_notes = request.notes if request.notes is not None else action.notes

        updated_action = action.model_copy(
            update={
                "status": new_status,
                "notes": new_notes,
                "updated_at": now,
            }
        )

        new_actions = list(record.actions)
        new_actions[target_act_idx] = updated_action

        # Update record with new actions and recalculate progress and derived overall status
        updated_rec = record.model_copy(
            update={
                "actions": new_actions,
                "updated_at": now,
            }
        )
        recalculate_recovery_progress(updated_rec)

        # Attach recalculated progress summary to the returned action
        updated_action.progress = updated_rec.progress

        new_records = list(profile.recovery_records)
        new_records[target_rec_idx] = updated_rec

        updated_profile = profile.model_copy(
            update={
                "recovery_records": new_records,
                "updated_at": now,
            }
        )
        await self.store.update(event_id, updated_profile, user_id=user_id)

        logger.info(
            "Updated action %s in recovery %s for event %s (action_status=%s, recovery_status=%s)",
            action_id,
            recovery_id,
            event_id,
            updated_action.status.value,
            updated_rec.status.value,
        )
        return updated_action

    async def get_event_readiness(
        self,
        event_id: str,
        reference_date: date | None = None,
        user_id: UUID | None = None,
    ) -> EventReadinessResponse | None:
        """Assess event planning readiness deterministically across all domains.

        Args:
            event_id: Target event profile identifier.
            reference_date: Optional simulated reference date for timeline calculations.
            user_id: Optional authenticated user UUID or guest session identifier.

        Returns:
            EventReadinessResponse if event profile exists, None otherwise.
        """
        profile = await self.get_event(event_id, user_id=user_id)
        if profile is None:
            return None

        return ReadinessService.calculate_readiness(
            profile=profile,
            reference_date=reference_date,
        )


def recalculate_recovery_progress(
    record: CrisisRecoveryRecord,
    explicit_status: RecoveryStatus | None = None,
) -> None:
    """Recalculate action progress counts, completion percentage, and derive overall recovery status.

    Documented rules:
    - total_actions = len(record.actions)
    - pending_actions = count of actions where status is PENDING
    - in_progress_actions = count of actions where status is IN_PROGRESS
    - completed_actions = count of actions where status is COMPLETED
    - completion_percentage = round((completed / total) * 100.0, 1) if total > 0 else 0.0

    Overall Status Rules:
    - If explicit_status is specified, the record status is updated to explicit_status.
    - Otherwise, status is automatically derived:
      - If total_actions > 0 and completed_actions == total_actions: status is RESOLVED.
      - If total_actions > 0 and (completed_actions > 0 or in_progress_actions > 0): status is IN_PROGRESS.
      - If total_actions > 0 and all actions are pending: status is OPEN.
      - If total_actions == 0: status is unchanged.
    - Automatic resolution is NEVER applied while any action remains incomplete (pending or in_progress).
    """
    total = len(record.actions)
    pending = sum(1 for a in record.actions if a.status == RecoveryActionStatus.PENDING)
    in_progress = sum(1 for a in record.actions if a.status == RecoveryActionStatus.IN_PROGRESS)
    completed = sum(1 for a in record.actions if a.status == RecoveryActionStatus.COMPLETED)
    pct = round((completed / total) * 100.0, 1) if total > 0 else 0.0

    record.progress = RecoveryProgressSummary(
        total_actions=total,
        pending_actions=pending,
        in_progress_actions=in_progress,
        completed_actions=completed,
        completion_percentage=pct,
    )
    record.total_actions = total
    record.completed_actions = completed

    if explicit_status is not None:
        record.status = explicit_status
    elif total > 0:
        if completed == total:
            record.status = RecoveryStatus.RESOLVED
        elif completed > 0 or in_progress > 0:
            record.status = RecoveryStatus.IN_PROGRESS
        else:
            record.status = RecoveryStatus.OPEN






