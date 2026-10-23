"""
In-Memory Event Storage Repository.

Thread-safe, ephemeral in-memory storage for event profiles with FIFO capacity eviction.
Suitable for local testing, development, and offline operation without an external database.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.repositories.base import BaseEventRepository
from app.schemas import EventProfile

logger = logging.getLogger(__name__)


class InMemoryEventRepository(BaseEventRepository):
    """Thread-safe, ephemeral in-memory storage for event profiles with tenant isolation.

    Caution:
        Data stored here is ephemeral and is cleared when the process terminates.
    """

    def __init__(self, max_capacity: int = 1000, max_size: int | None = None) -> None:
        """Initialize the store with maximum capacity to prevent unbounded memory growth."""
        self._events: dict[str, EventProfile] = {}
        self._max_capacity = max_size if max_size is not None else max_capacity
        self._lock = asyncio.Lock()

    async def create(self, profile: EventProfile, user_id: UUID | None = None) -> EventProfile:
        """Insert a new event profile into the store, scoped to user_id."""
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

            # Assign user_id if supplied and not already set
            assigned_user_id = user_id if user_id is not None else profile.user_id
            if profile.user_id != assigned_user_id:
                profile = profile.model_copy(update={"user_id": assigned_user_id})

            self._events[profile.event_id] = profile
            return profile

    async def get(self, event_id: str, user_id: UUID | None = None) -> EventProfile | None:
        """Retrieve an event profile by event_id, verifying user_id ownership."""
        async with self._lock:
            profile = self._events.get(event_id)
            if profile is None:
                return None

            if user_id is not None:
                if profile.user_id != user_id:
                    return None
            else:
                # Unauthenticated guest cannot access authenticated user events
                if profile.user_id is not None:
                    return None

            return profile

    async def update(
        self, event_id: str, profile: EventProfile, user_id: UUID | None = None
    ) -> EventProfile | None:
        """Update an existing event profile in the store, verifying ownership."""
        async with self._lock:
            if event_id not in self._events:
                return None

            existing = self._events[event_id]
            if user_id is not None:
                if existing.user_id != user_id:
                    return None
            else:
                if existing.user_id is not None:
                    return None

            # Preserve owner identity across updates
            target_user_id = existing.user_id if profile.user_id is None else profile.user_id
            if profile.user_id != target_user_id:
                profile = profile.model_copy(update={"user_id": target_user_id})

            self._events[event_id] = profile
            return profile

    async def list(
        self, skip: int = 0, limit: int = 50, user_id: UUID | None = None
    ) -> tuple[list[EventProfile], int]:
        """Return a paginated slice of stored events belonging to user_id."""
        async with self._lock:
            if user_id is not None:
                filtered = [e for e in self._events.values() if e.user_id == user_id]
            else:
                filtered = [e for e in self._events.values() if e.user_id is None]

            total = len(filtered)
            sorted_events = sorted(filtered, key=lambda e: e.updated_at, reverse=True)
            page = sorted_events[skip : skip + limit]
            return page, total

    async def delete(self, event_id: str, user_id: UUID | None = None) -> bool:
        """Delete an event profile from the store if owned by user_id."""
        async with self._lock:
            if event_id not in self._events:
                return False

            existing = self._events[event_id]
            if user_id is not None:
                if existing.user_id != user_id:
                    return False
            else:
                if existing.user_id is not None:
                    return False

            del self._events[event_id]
            return True

    async def clear(self) -> None:
        """Remove all stored events. Primarily used for test isolation."""
        async with self._lock:
            self._events.clear()

    async def count(self, user_id: UUID | None = None) -> int:
        """Return the current number of events stored, optionally filtered by user_id."""
        async with self._lock:
            if user_id is not None:
                return sum(1 for e in self._events.values() if e.user_id == user_id)
            return sum(1 for e in self._events.values() if e.user_id is None)
