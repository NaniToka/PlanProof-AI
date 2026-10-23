"""
Abstract Base Event Repository Interface and Exceptions.

Defines the contract for persistent and ephemeral event storage backends,
supporting aggregate EventProfile operations and granular domain entity persistence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.schemas import (
    CrisisRecoveryRecord,
    EventBudgetBreakdown,
    EventProfile,
    EventVendorChecklistItem,
    MilestoneStatus,
    RecoveryActionStatus,
    RecoveryStatus,
    TrackedRecoveryAction,
)


# ==============================================================================
# 1. Repository Exceptions
# ==============================================================================


class RepositoryError(Exception):
    """Base exception for all event repository errors."""


class EventNotFoundError(RepositoryError):
    """Raised when an event profile is not found in the repository."""


class DatabaseConnectionError(RepositoryError):
    """Raised when database connection, pooling, or communication fails."""


class RepositoryIntegrityError(RepositoryError):
    """Raised when a relational, unique, or business integrity constraint is violated."""


# ==============================================================================
# 2. Abstract Base Repository Interface
# ==============================================================================


class BaseEventRepository(ABC):
    """Abstract interface for event storage repositories."""

    # --------------------------------------------------------------------------
    # Lifecycle Management
    # --------------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish connections or initialize resources (e.g. connection pool)."""
        return None

    async def disconnect(self) -> None:
        """Close connections or release pooled resources."""
        return None

    # --------------------------------------------------------------------------
    # Core Event Profile Aggregate Operations
    # --------------------------------------------------------------------------

    @abstractmethod
    async def create(self, profile: EventProfile, user_id: UUID | None = None) -> EventProfile:
        """Insert a new event profile into storage.

        Args:
            profile: Complete domain model to persist.
            user_id: Verified owning user UUID.

        Returns:
            The stored EventProfile.
        """

    @abstractmethod
    async def get(self, event_id: str, user_id: UUID | None = None) -> EventProfile | None:
        """Retrieve an event profile by its unique identifier, scoped to user_id.

        Args:
            event_id: The event ID (e.g. EV-...)
            user_id: Optional owning user UUID to enforce tenant isolation.

        Returns:
            The matching EventProfile if found and owned, or None otherwise.
        """

    @abstractmethod
    async def update(
        self, event_id: str, profile: EventProfile, user_id: UUID | None = None
    ) -> EventProfile | None:
        """Update an existing event profile scoped to user_id.

        Args:
            event_id: The event ID to update.
            profile: The updated profile data.
            user_id: Optional owning user UUID to enforce tenant isolation.

        Returns:
            The updated EventProfile, or None if the event does not exist or is unauthorized.
        """

    @abstractmethod
    async def list(
        self, skip: int = 0, limit: int = 50, user_id: UUID | None = None
    ) -> tuple[list[EventProfile], int]:
        """Return a paginated slice of stored events and total count, scoped to user_id.

        Args:
            skip: Offset of records to skip.
            limit: Maximum records to return.
            user_id: Optional owning user UUID to filter tenant events.

        Returns:
            Tuple of (list of events, total count).
        """

    @abstractmethod
    async def delete(self, event_id: str, user_id: UUID | None = None) -> bool:
        """Delete an event profile from storage scoped to user_id.

        Args:
            event_id: The event ID to delete.
            user_id: Optional owning user UUID to enforce tenant isolation.

        Returns:
            True if removed, False if not found or unauthorized.
        """

    @abstractmethod
    async def count(self, user_id: UUID | None = None) -> int:
        """Return the total number of events currently stored, optionally scoped to user_id."""

    @abstractmethod
    async def clear(self) -> None:
        """Remove all stored events. Primarily used for isolated unit testing."""

    # --------------------------------------------------------------------------
    # Granular Domain Persistence Operations
    # --------------------------------------------------------------------------

    async def get_budget(
        self, event_id: str, user_id: UUID | None = None
    ) -> EventBudgetBreakdown | None:
        """Retrieve the budget allocation breakdown for an event."""
        profile = await self.get(event_id, user_id=user_id)
        return profile.budget if profile else None

    async def save_budget(
        self, event_id: str, budget: EventBudgetBreakdown, user_id: UUID | None = None
    ) -> EventBudgetBreakdown | None:
        """Persist budget allocations for an event."""
        profile = await self.get(event_id, user_id=user_id)
        if not profile:
            return None
        updated = profile.model_copy(
            update={
                "budget": budget,
                "total_budget_inr": budget.total_budget_inr,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        saved = await self.update(event_id, updated, user_id=user_id)
        return saved.budget if saved else None

    async def get_milestone_statuses(
        self, event_id: str, user_id: UUID | None = None
    ) -> dict[str, MilestoneStatus] | None:
        """Retrieve milestone completion status overrides for an event."""
        profile = await self.get(event_id, user_id=user_id)
        return profile.milestone_statuses if profile else None

    async def save_milestone_status(
        self, event_id: str, milestone_id: str, status: MilestoneStatus, user_id: UUID | None = None
    ) -> dict[str, MilestoneStatus] | None:
        """Update or insert a milestone status override for an event."""
        profile = await self.get(event_id, user_id=user_id)
        if not profile:
            return None
        statuses = dict(profile.milestone_statuses)
        statuses[milestone_id] = status
        updated = profile.model_copy(
            update={
                "milestone_statuses": statuses,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        saved = await self.update(event_id, updated, user_id=user_id)
        return saved.milestone_statuses if saved else None

    async def get_vendor_checklist(
        self, event_id: str, user_id: UUID | None = None
    ) -> list[EventVendorChecklistItem] | None:
        """Retrieve the vendor checklist items for an event."""
        profile = await self.get(event_id, user_id=user_id)
        return profile.vendor_checklist if profile else None

    async def save_vendor_checklist_item(
        self, event_id: str, item: EventVendorChecklistItem, user_id: UUID | None = None
    ) -> EventVendorChecklistItem | None:
        """Update or insert an individual vendor checklist item."""
        profile = await self.get(event_id, user_id=user_id)
        if not profile:
            return None
        items = list(profile.vendor_checklist)
        idx = next((i for i, x in enumerate(items) if x.id == item.id), None)
        if idx is not None:
            items[idx] = item
        else:
            items.append(item)
        updated = profile.model_copy(
            update={
                "vendor_checklist": items,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        saved = await self.update(event_id, updated, user_id=user_id)
        if not saved:
            return None
        return next((x for x in saved.vendor_checklist if x.id == item.id), None)

    async def create_recovery_record(
        self, event_id: str, record: CrisisRecoveryRecord, user_id: UUID | None = None
    ) -> CrisisRecoveryRecord | None:
        """Append a historical crisis recovery record to an event."""
        profile = await self.get(event_id, user_id=user_id)
        if not profile:
            return None
        records = [record] + list(profile.recovery_records)
        updated = profile.model_copy(
            update={
                "recovery_records": records,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        saved = await self.update(event_id, updated, user_id=user_id)
        if not saved:
            return None
        return next((r for r in saved.recovery_records if r.recovery_id == record.recovery_id), None)

    async def get_recovery_record(
        self, event_id: str, recovery_id: str, user_id: UUID | None = None
    ) -> CrisisRecoveryRecord | None:
        """Retrieve a specific crisis recovery record for an event."""
        profile = await self.get(event_id, user_id=user_id)
        if not profile:
            return None
        return next((r for r in profile.recovery_records if r.recovery_id == recovery_id), None)

    async def list_recovery_records(
        self, event_id: str, user_id: UUID | None = None
    ) -> list[CrisisRecoveryRecord] | None:
        """Retrieve all recovery records for an event ordered newest first."""
        profile = await self.get(event_id, user_id=user_id)
        if not profile:
            return None
        return sorted(profile.recovery_records, key=lambda r: r.created_at, reverse=True)

    async def update_recovery_record(
        self,
        event_id: str,
        recovery_id: str,
        status: RecoveryStatus | None = None,
        description: str | None = None,
        user_id: UUID | None = None,
    ) -> CrisisRecoveryRecord | None:
        """Update header attributes of an existing crisis recovery record."""
        profile = await self.get(event_id, user_id=user_id)
        if not profile:
            return None
        records = list(profile.recovery_records)
        idx = next((i for i, r in enumerate(records) if r.recovery_id == recovery_id), None)
        if idx is None:
            return None
        target = records[idx]
        upd_fields: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if status is not None:
            upd_fields["status"] = status
        if description is not None:
            upd_fields["description"] = description
        records[idx] = target.model_copy(update=upd_fields)
        saved = await self.update(
            event_id,
            profile.model_copy(
                update={"recovery_records": records, "updated_at": datetime.now(timezone.utc)}
            ),
            user_id=user_id,
        )
        if not saved:
            return None
        return next((r for r in saved.recovery_records if r.recovery_id == recovery_id), None)

    async def update_recovery_action(
        self,
        event_id: str,
        recovery_id: str,
        action_id: str,
        status: RecoveryActionStatus | None = None,
        notes: str | None = None,
        user_id: UUID | None = None,
    ) -> TrackedRecoveryAction | None:
        """Update execution status or host notes on a tracked recovery action."""
        profile = await self.get(event_id, user_id=user_id)
        if not profile:
            return None
        records = list(profile.recovery_records)
        rec_idx = next((i for i, r in enumerate(records) if r.recovery_id == recovery_id), None)
        if rec_idx is None:
            return None
        rec = records[rec_idx]
        actions = list(rec.actions)
        act_idx = next((i for i, a in enumerate(actions) if a.action_id == action_id), None)
        if act_idx is None:
            return None
        act = actions[act_idx]
        act_upd: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if status is not None:
            act_upd["status"] = status
        if notes is not None:
            act_upd["notes"] = notes
        actions[act_idx] = act.model_copy(update=act_upd)
        completed_count = sum(1 for a in actions if a.status == RecoveryActionStatus.COMPLETED)
        records[rec_idx] = rec.model_copy(
            update={
                "actions": actions,
                "completed_actions": completed_count,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        saved = await self.update(
            event_id,
            profile.model_copy(
                update={"recovery_records": records, "updated_at": datetime.now(timezone.utc)}
            ),
            user_id=user_id,
        )
        if not saved:
            return None
        target_rec = next((r for r in saved.recovery_records if r.recovery_id == recovery_id), None)
        if not target_rec:
            return None
        return next((a for a in target_rec.actions if a.action_id == action_id), None)
