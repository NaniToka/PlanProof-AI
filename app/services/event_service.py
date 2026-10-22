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
from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings, get_settings
from app.data_loader import DatasetRepository
from app.schemas import (
    EventCreateRequest,
    EventProfile,
    EventUpdateRequest,
    validate_event_date,
)
from app.services.budget import calculate_initial_budget

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
