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
from uuid import uuid4

from app.config import Settings, get_settings
from app.data_loader import DatasetRepository
from app.schemas import (
    CANONICAL_BUDGET_CATEGORIES,
    BudgetRebalanceResponse,
    EventBudgetPlanResponse,
    EventCreateRequest,
    EventMilestone,
    EventProfile,
    EventTimelineScheduleResponse,
    EventUpdateRequest,
    MilestoneStatus,
    get_current_ist_date,
    validate_event_date,
)
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

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Ephemeral In-Memory Event Store
# ==============================================================================


class EventStore:
    """Thread-safe, ephemeral in-memory storage for event profiles.

    Caution:
        Data stored here is ephemeral and is wiped when the process restarts.
        Never describe or use this as permanent or production storage.
    """

    def __init__(self, max_capacity: int = 1000) -> None:
        """Initialize the store with maximum capacity to prevent unbounded memory growth."""
        self._events: dict[str, EventProfile] = {}
        self._max_capacity = max_capacity
        self._lock = asyncio.Lock()

    async def create(self, profile: EventProfile) -> EventProfile:
        """Insert a new event profile into the store."""
        async with self._lock:
            # Enforce bounded capacity via FIFO eviction if threshold reached
            if len(self._events) >= self._max_capacity:
                oldest_key = next(iter(self._events))
                del self._events[oldest_key]
                logger.warning(
                    "EventStore capacity reached (%d); evicted oldest event %s",
                    self._max_capacity,
                    oldest_key,
                )

            self._events[profile.event_id] = profile
            return profile

    async def get(self, event_id: str) -> EventProfile | None:
        """Retrieve an event profile by unique event_id, or None if not found."""
        async with self._lock:
            return self._events.get(event_id)

    async def update(self, event_id: str, profile: EventProfile) -> EventProfile | None:
        """Update an existing event profile in the store."""
        async with self._lock:
            if event_id not in self._events:
                return None
            self._events[event_id] = profile
            return profile

    async def list(self, skip: int = 0, limit: int = 50) -> tuple[list[EventProfile], int]:
        """Return a paginated slice of stored events and the total count."""
        async with self._lock:
            total = len(self._events)
            all_events = list(self._events.values())
            # Return most recently updated first
            sorted_events = sorted(all_events, key=lambda e: e.updated_at, reverse=True)
            page = sorted_events[skip : skip + limit]
            return page, total

    async def delete(self, event_id: str) -> bool:
        """Delete an event profile from the store. Returns True if removed."""
        async with self._lock:
            return self._events.pop(event_id, None) is not None

    async def clear(self) -> None:
        """Remove all stored events. Primarily used for test isolation."""
        async with self._lock:
            self._events.clear()

    async def count(self) -> int:
        """Return the current number of events stored."""
        async with self._lock:
            return len(self._events)


# ==============================================================================
# 2. Event Profile Domain Service
# ==============================================================================


class EventService:
    """Domain service managing core event profile workflows and budget calculations."""

    def __init__(
        self,
        store: EventStore | None = None,
        dataset_repo: DatasetRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize event service with repository and optional dataset dependencies."""
        self.store = store or EventStore()
        self.dataset_repo = dataset_repo
        self.settings = settings or get_settings()

    async def create_event(self, request: EventCreateRequest) -> EventProfile:
        """Create a new event profile, calculate its initial budget, and store it.

        Args:
            request: Validated event creation request data.

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

        profile = EventProfile(
            event_id=event_id,
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
            created_at=now,
            updated_at=now,
        )

        await self.store.create(profile)
        # Safe logging: Never log customer theme notes, PII, or free text
        logger.info(
            "Created event profile %s (type=%s, tier=%s, guests=%d)",
            event_id,
            profile.event_type.value,
            profile.city_tier.value,
            profile.guest_count,
        )
        return profile

    async def get_event(self, event_id: str) -> EventProfile | None:
        """Retrieve an event profile by event_id."""
        return await self.store.get(event_id)

    async def update_event(
        self, event_id: str, request: EventUpdateRequest
    ) -> EventProfile | None:
        """Apply partial updates to an existing event profile and recompute budget if needed.

        Args:
            event_id: Unique event identifier.
            request: Fields to update.

        Returns:
            Updated EventProfile, or None if the event does not exist.
        """
        existing = await self.store.get(event_id)
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

        now = datetime.now(timezone.utc)

        # Build updated profile preserving server-generated fields
        updated_profile = EventProfile(
            event_id=existing.event_id,  # Immutable
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
            created_at=existing.created_at,  # Immutable
            updated_at=now,  # Updated timestamp
        )

        await self.store.update(event_id, updated_profile)
        logger.info("Updated event profile %s", event_id)
        return updated_profile

    async def list_events(
        self, skip: int = 0, limit: int = 50
    ) -> tuple[list[EventProfile], int]:
        """Return a paginated list of active event profiles and total count."""
        return await self.store.list(skip=skip, limit=limit)

    async def get_event_budget_plan(
        self, event_id: str
    ) -> EventBudgetPlanResponse | None:
        """Retrieve the deterministic budget plan for a saved event profile.

        Args:
            event_id: Unique event identifier.

        Returns:
            EventBudgetPlanResponse if event exists, None otherwise.
        """
        profile = await self.store.get(event_id)
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
    ) -> BudgetRebalanceResponse | None:
        """Rebalance an existing event profile's budget using priority-based category trimming.

        Args:
            event_id: Unique event identifier.
            new_total_budget_inr: Target new budget in INR.
            strict_protect: If True, disallow cuts to catering and buffer reserve.

        Returns:
            BudgetRebalanceResponse if event exists, None otherwise.
        """
        profile = await self.store.get(event_id)
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
            created_at=profile.created_at,
            updated_at=now,
        )
        await self.store.update(event_id, updated_profile)
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
    ) -> EventTimelineScheduleResponse | None:
        """Generate and retrieve the deterministic timeline for a saved event profile.

        Args:
            event_id: Unique event identifier.
            reference_date: Optional simulated 'today' for testing.

        Returns:
            EventTimelineScheduleResponse if event exists, None otherwise.
        """
        profile = await self.store.get(event_id)
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
    ) -> EventMilestone | None:
        """Update completion status of a timeline milestone in ephemeral storage.

        Args:
            event_id: Unique event identifier.
            milestone_id: Milestone identifier (must belong to event type template).
            status: New status (pending or completed).
            reference_date: Optional simulated reference date for testing.

        Returns:
            Updated EventMilestone, or None if event not found.

        Raises:
            ValueError: If event_date is missing on profile.
            KeyError: If milestone_id does not exist in template for event type.
        """
        profile = await self.store.get(event_id)
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
            created_at=profile.created_at,
            updated_at=now,
        )
        await self.store.update(event_id, updated_profile)

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


