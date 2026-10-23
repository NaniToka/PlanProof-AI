"""
In-Memory Event Storage Repository.

Thread-safe, ephemeral in-memory storage for event profiles with FIFO capacity eviction.
Suitable for local testing, development, and offline operation without an external database.
"""

from __future__ import annotations

import asyncio
import logging

from app.repositories.base import BaseEventRepository
from app.schemas import EventProfile

logger = logging.getLogger(__name__)


class InMemoryEventRepository(BaseEventRepository):
    """Thread-safe, ephemeral in-memory storage for event profiles.

    Caution:
        Data stored here is ephemeral and is cleared when the process terminates.
    """

    def __init__(self, max_capacity: int = 1000, max_size: int | None = None) -> None:
        """Initialize the store with maximum capacity to prevent unbounded memory growth."""
        self._events: dict[str, EventProfile] = {}
        self._max_capacity = max_size if max_size is not None else max_capacity
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
