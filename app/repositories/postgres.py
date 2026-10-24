"""
PostgreSQL Event Storage Repository.

Production-grade persistent repository implementing BaseEventRepository using asyncpg.
Handles connection pooling, parameterized queries, relational entity mapping,
multi-table transactional integrity, Supabase transaction-local RLS claims,
and tenant data isolation without fixed guest accounts.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator
from uuid import UUID

import asyncpg

from app.config import Settings
from app.repositories.base import (
    BaseEventRepository,
    DatabaseConnectionError,
    EventNotFoundError,
    RepositoryError,
    RepositoryIntegrityError,
)
from app.schemas import (
    CityTier,
    CrisisRecoveryRecord,
    EventBudgetBreakdown,
    EventCrisisRecoveryResponse,
    EventProfile,
    EventType,
    EventVendorChecklistItem,
    LanguageCode,
    MilestoneStatus,
    RecoveryActionStatus,
    RecoveryStatus,
    TrackedRecoveryAction,
    VendorBookingStatus,
    VendorChecklistCategory,
    VendorChecklistPriority,
    VendorChecklistStatus,
)

logger = logging.getLogger(__name__)


class PostgresEventRepository(BaseEventRepository):
    """PostgreSQL implementation of BaseEventRepository using asyncpg and Supabase RLS.

    Database Role Architecture:
    - The connection role (e.g. 'planproof_app' or 'planproof_test_app') must NOT be a
      superuser and must NOT possess the BYPASSRLS privilege.
    - The connection role must be granted membership in the 'authenticated' role
      (GRANT authenticated TO <connection_role>;) to permit transaction-local role switching.
    - Each database operation executes inside an explicit transaction where the verified
      user identity is set via transaction-local configuration parameters:
        1. set_config('role', 'authenticated', true)
        2. set_config('request.jwt.claim.sub', str(user_id), true)
    - All RLS policies on tables and child tables are evaluated by PostgreSQL engine itself.
    """

    def __init__(
        self,
        database_url: str | Settings | None = None,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 10.0,
        default_user_id: UUID | None = None,
        pool: asyncpg.Pool | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize PostgreSQL repository configuration without connecting immediately.

        Args:
            database_url: PostgreSQL connection string or Settings instance.
            min_size: Minimum connection pool connections.
            max_size: Maximum connection pool connections.
            timeout: Timeout in seconds for connection acquisition.
            default_user_id: Deprecated optional user UUID (Step 2 requires verified user_id).
            pool: Optional pre-configured asyncpg.Pool instance (useful for testing/injection).
            settings: Optional Settings instance.
        """
        if isinstance(database_url, Settings):
            settings = database_url
            database_url = None

        if settings is not None:
            self.settings = settings
            self._database_url = settings.get_database_url_value() or ""
            self._min_size = settings.database_pool_min_size
            self._max_size = settings.database_pool_max_size
            self._timeout = settings.database_connection_timeout
        else:
            self.settings = None
            self._database_url = database_url or ""
            self._min_size = min_size
            self._max_size = max_size
            self._timeout = timeout

        self._default_user_id = default_user_id
        self._pool = pool
        self._external_pool = pool is not None

    # --------------------------------------------------------------------------
    # Lifecycle Management
    # --------------------------------------------------------------------------

    async def connect(self) -> None:
        """Initialize connection pool lazily or during application startup."""
        if self._pool is None:
            try:
                self._pool = await asyncpg.create_pool(
                    dsn=self._database_url,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    timeout=self._timeout,
                )
                logger.info(
                    "PostgreSQL connection pool initialized (min=%d, max=%d)",
                    self._min_size,
                    self._max_size,
                )
            except Exception as exc:
                logger.error("Failed to establish PostgreSQL connection pool: %s", type(exc).__name__)
                raise DatabaseConnectionError(
                    f"Failed to connect to PostgreSQL database: {type(exc).__name__}"
                ) from exc

    async def disconnect(self) -> None:
        """Close connection pool cleanly during application shutdown."""
        if self._pool is not None and not self._external_pool:
            try:
                await self._pool.close()
                logger.info("PostgreSQL connection pool closed cleanly.")
            finally:
                self._pool = None

    @asynccontextmanager
    async def _acquire(self) -> AsyncIterator[asyncpg.Connection]:
        """Acquire a connection from the pool, establishing pool if needed."""
        if self._pool is None:
            await self.connect()
        assert self._pool is not None
        try:
            async with self._pool.acquire() as conn:
                yield conn
        except (asyncpg.PostgresConnectionError, asyncpg.CannotConnectNowError) as exc:
            logger.error("Database connection failure: %s", type(exc).__name__)
            raise DatabaseConnectionError(f"Database connection error: {exc}") from exc

    @asynccontextmanager
    async def acquire_connection(self) -> AsyncIterator[asyncpg.Connection]:
        """Public context manager to acquire a connection from the pool for maintenance or tests."""
        async with self._acquire() as conn:
            yield conn

    # --------------------------------------------------------------------------
    # RLS Claim Context Management (Transaction-Local)
    # --------------------------------------------------------------------------

    @staticmethod
    async def _set_rls_context(conn: asyncpg.Connection, user_id: UUID) -> None:
        """Establish transaction-scoped Supabase claim context for Row Level Security.

        Uses SET LOCAL / set_config with is_local=true so that claims revert
        automatically upon COMMIT or ROLLBACK, preventing pool leakage.
        """
        await conn.execute("SELECT set_config('role', 'authenticated', true);")
        await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true);", str(user_id))

    # --------------------------------------------------------------------------
    # Core Event Profile Aggregate Operations
    # --------------------------------------------------------------------------

    async def create(self, profile: EventProfile, user_id: UUID | None = None) -> EventProfile:
        """Insert a complete event profile across all related child tables in a transaction."""
        owner_id = user_id or profile.user_id or self._default_user_id
        if owner_id is None:
            raise RepositoryIntegrityError("Cannot persist event without an authenticated user ID.")

        async with self._acquire() as conn:
            try:
                async with conn.transaction():
                    await self._set_rls_context(conn, owner_id)

                    # 0. Ensure user profile exists (authenticated application operation)
                    await conn.execute(
                        """
                        INSERT INTO public.profiles (id, email)
                        VALUES ($1, '')
                        ON CONFLICT (id) DO NOTHING;
                        """,
                        owner_id,
                    )

                    # 1. Insert parent event
                    await conn.execute(
                        """
                        INSERT INTO public.events (
                            event_id, user_id, event_type, event_name, city, city_tier,
                            event_date, guest_count, total_budget_inr, language,
                            theme_notes, is_in_progress, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14);
                        """,
                        profile.event_id,
                        owner_id,
                        profile.event_type.value,
                        profile.event_name,
                        profile.city,
                        profile.city_tier.value,
                        profile.event_date,
                        profile.guest_count,
                        profile.total_budget_inr,
                        profile.language.value,
                        profile.theme_notes,
                        profile.is_in_progress,
                        profile.created_at,
                        profile.updated_at,
                    )

                    # 2. Insert budget allocations if present
                    if profile.budget is not None:
                        b = profile.budget
                        await conn.execute(
                            """
                            INSERT INTO public.event_budgets (
                                event_id, venue, catering, decor, photo_video, attire_beauty,
                                entertainment, logistics, buffer, total_budget_inr,
                                created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);
                            """,
                            profile.event_id,
                            b.venue,
                            b.catering,
                            b.decor,
                            b.photo_video,
                            b.attire_beauty,
                            b.entertainment,
                            b.logistics,
                            b.buffer,
                            b.total_budget_inr,
                            profile.created_at,
                            profile.updated_at,
                        )

                    # 3. Insert milestone status overrides
                    for mid, st in profile.milestone_statuses.items():
                        await conn.execute(
                            """
                            INSERT INTO public.event_milestone_statuses (
                                event_id, milestone_id, status, created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5);
                            """,
                            profile.event_id,
                            mid,
                            st.value,
                            profile.created_at,
                            profile.updated_at,
                        )

                    # 4. Insert vendor checklist items
                    for item in profile.vendor_checklist:
                        await conn.execute(
                            """
                            INSERT INTO public.event_vendor_checklist_items (
                                id, event_id, category, title, description, status,
                                due_date, days_before_event, priority, notes,
                                vendor_name, booking_status, created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14);
                            """,
                            item.id,
                            profile.event_id,
                            item.category.value,
                            item.title,
                            item.description,
                            item.status.value,
                            item.due_date,
                            item.days_before_event,
                            item.priority.value,
                            item.notes,
                            item.vendor_name,
                            item.booking_status.value,
                            item.created_at,
                            item.updated_at,
                        )

                    # 5. Insert recovery records and actions
                    for rec in profile.recovery_records:
                        plan_json = json.dumps(rec.recovery_plan.model_dump(mode="json"))
                        await conn.execute(
                            """
                            INSERT INTO public.crisis_recovery_records (
                                recovery_id, event_id, crisis_type, severity, description,
                                recovery_plan, source, status, total_actions, completed_actions,
                                created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);
                            """,
                            rec.recovery_id,
                            profile.event_id,
                            rec.crisis_type,
                            rec.severity,
                            rec.description,
                            plan_json,
                            rec.source,
                            rec.status.value,
                            rec.total_actions,
                            rec.completed_actions,
                            rec.created_at,
                            rec.updated_at,
                        )
                        for act in rec.actions:
                            await conn.execute(
                                """
                                INSERT INTO public.crisis_recovery_actions (
                                    action_id, recovery_id, event_id, title, description,
                                    priority, status, notes, created_at, updated_at
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);
                                """,
                                act.action_id,
                                rec.recovery_id,
                                profile.event_id,
                                act.title,
                                act.description,
                                act.priority,
                                act.status.value,
                                act.notes,
                                act.created_at,
                                act.updated_at,
                            )

                if profile.user_id != owner_id:
                    profile = profile.model_copy(update={"user_id": owner_id})
                return profile
            except asyncpg.IntegrityConstraintViolationError as err:
                raise RepositoryIntegrityError(f"Database constraint violation on create: {err}") from err
            except Exception as exc:
                if isinstance(exc, (RepositoryError,)):
                    raise
                raise RepositoryError(f"Failed to create event: {exc}") from exc

    async def _fetch_profile_in_conn(
        self, conn: asyncpg.Connection, event_id: str, user_id: UUID
    ) -> EventProfile | None:
        """Internal helper to fetch full event aggregate within an existing transaction/connection."""
        # 1. Fetch parent event
        row = await conn.fetchrow(
            """
            SELECT event_id, user_id, event_type, event_name, city, city_tier,
                   event_date, guest_count, total_budget_inr, language,
                   theme_notes, is_in_progress, created_at, updated_at
            FROM public.events
            WHERE event_id = $1 AND user_id = $2;
            """,
            event_id,
            user_id,
        )
        if not row:
            return None

        # 2. Fetch budget
        b_row = await conn.fetchrow(
            """
            SELECT venue, catering, decor, photo_video, attire_beauty,
                   entertainment, logistics, buffer, total_budget_inr
            FROM public.event_budgets
            WHERE event_id = $1;
            """,
            event_id,
        )
        budget = (
            EventBudgetBreakdown(
                venue=b_row["venue"],
                catering=b_row["catering"],
                decor=b_row["decor"],
                photo_video=b_row["photo_video"],
                attire_beauty=b_row["attire_beauty"],
                entertainment=b_row["entertainment"],
                logistics=b_row["logistics"],
                buffer=b_row["buffer"],
                total_budget_inr=b_row["total_budget_inr"],
            )
            if b_row
            else None
        )

        # 3. Fetch milestone statuses
        ms_rows = await conn.fetch(
            """
            SELECT milestone_id, status
            FROM public.event_milestone_statuses
            WHERE event_id = $1;
            """,
            event_id,
        )
        milestone_statuses = {r["milestone_id"]: MilestoneStatus(r["status"]) for r in ms_rows}

        # 4. Fetch vendor checklist items
        v_rows = await conn.fetch(
            """
            SELECT id, category, title, description, status,
                   due_date, days_before_event, priority, notes,
                   vendor_name, booking_status, created_at, updated_at
            FROM public.event_vendor_checklist_items
            WHERE event_id = $1
            ORDER BY due_date ASC NULLS LAST, created_at ASC;
            """,
            event_id,
        )
        vendor_checklist = [
            EventVendorChecklistItem(
                id=r["id"],
                category=VendorChecklistCategory(r["category"]),
                title=r["title"],
                description=r["description"],
                status=VendorChecklistStatus(r["status"]),
                due_date=r["due_date"],
                days_before_event=r["days_before_event"],
                priority=VendorChecklistPriority(r["priority"]),
                notes=r["notes"],
                vendor_name=r["vendor_name"],
                booking_status=VendorBookingStatus(r["booking_status"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in v_rows
        ]

        # 5. Fetch recovery records and actions
        rec_rows = await conn.fetch(
            """
            SELECT recovery_id, crisis_type, severity, description,
                   recovery_plan, source, status, total_actions, completed_actions,
                   created_at, updated_at
            FROM public.crisis_recovery_records
            WHERE event_id = $1
            ORDER BY created_at DESC;
            """,
            event_id,
        )
        recovery_records: list[CrisisRecoveryRecord] = []
        for rr in rec_rows:
            rec_id = rr["recovery_id"]
            act_rows = await conn.fetch(
                """
                SELECT action_id, title, description, priority, status, notes,
                       created_at, updated_at
                FROM public.crisis_recovery_actions
                WHERE recovery_id = $1
                ORDER BY created_at ASC;
                """,
                rec_id,
            )
            actions = [
                TrackedRecoveryAction(
                    action_id=ar["action_id"],
                    recovery_id=rec_id,
                    title=ar["title"],
                    description=ar["description"],
                    priority=ar["priority"],
                    status=RecoveryActionStatus(ar["status"]),
                    notes=ar["notes"],
                    created_at=ar["created_at"],
                    updated_at=ar["updated_at"],
                )
                for ar in act_rows
            ]
            plan_data = rr["recovery_plan"]
            if isinstance(plan_data, str):
                plan_dict = json.loads(plan_data)
            else:
                plan_dict = plan_data
            plan = EventCrisisRecoveryResponse.model_validate(plan_dict)

            recovery_records.append(
                CrisisRecoveryRecord(
                    recovery_id=rec_id,
                    event_id=event_id,
                    crisis_type=rr["crisis_type"],
                    severity=rr["severity"],
                    description=rr["description"],
                    recovery_plan=plan,
                    actions=actions,
                    source=rr["source"],
                    status=RecoveryStatus(rr["status"]),
                    total_actions=rr["total_actions"],
                    completed_actions=rr["completed_actions"],
                    created_at=rr["created_at"],
                    updated_at=rr["updated_at"],
                )
            )

        return EventProfile(
            event_id=row["event_id"],
            user_id=row["user_id"],
            event_type=EventType(row["event_type"]),
            event_name=row["event_name"],
            city=row["city"],
            city_tier=CityTier(row["city_tier"]),
            event_date=row["event_date"],
            guest_count=row["guest_count"],
            total_budget_inr=row["total_budget_inr"],
            language=LanguageCode(row["language"]),
            theme_notes=row["theme_notes"],
            is_in_progress=row["is_in_progress"],
            budget=budget,
            milestone_statuses=milestone_statuses,
            vendor_checklist=vendor_checklist,
            recovery_records=recovery_records,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get(self, event_id: str, user_id: UUID | None = None) -> EventProfile | None:
        """Retrieve complete event profile with all child entities, scoped to user_id."""
        effective_user_id = user_id or self._default_user_id
        if effective_user_id is None:
            return None

        async with self._acquire() as conn:
            try:
                async with conn.transaction():
                    await self._set_rls_context(conn, effective_user_id)
                    return await self._fetch_profile_in_conn(conn, event_id, effective_user_id)
            except Exception as exc:
                if isinstance(exc, (RepositoryError,)):
                    raise
                raise RepositoryError(f"Failed to fetch event '{event_id}': {exc}") from exc

    async def update(
        self, event_id: str, profile: EventProfile, user_id: UUID | None = None
    ) -> EventProfile | None:
        """Update event profile and synchronize dependent child entities in a transaction."""
        owner_id = user_id or profile.user_id or self._default_user_id
        if owner_id is None:
            return None

        async with self._acquire() as conn:
            try:
                async with conn.transaction():
                    await self._set_rls_context(conn, owner_id)

                    # 1. Update parent event row
                    res = await conn.execute(
                        """
                        UPDATE public.events SET
                            event_type = $2,
                            event_name = $3,
                            city = $4,
                            city_tier = $5,
                            event_date = $6,
                            guest_count = $7,
                            total_budget_inr = $8,
                            language = $9,
                            theme_notes = $10,
                            is_in_progress = $11,
                            updated_at = $12
                        WHERE event_id = $1 AND user_id = $13;
                        """,
                        event_id,
                        profile.event_type.value,
                        profile.event_name,
                        profile.city,
                        profile.city_tier.value,
                        profile.event_date,
                        profile.guest_count,
                        profile.total_budget_inr,
                        profile.language.value,
                        profile.theme_notes,
                        profile.is_in_progress,
                        profile.updated_at,
                        owner_id,
                    )
                    if res == "UPDATE 0":
                        return None

                    # 2. Update/upsert budget
                    if profile.budget is not None:
                        b = profile.budget
                        await conn.execute(
                            """
                            INSERT INTO public.event_budgets (
                                event_id, venue, catering, decor, photo_video, attire_beauty,
                                entertainment, logistics, buffer, total_budget_inr,
                                created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                            ON CONFLICT (event_id) DO UPDATE SET
                                venue = EXCLUDED.venue,
                                catering = EXCLUDED.catering,
                                decor = EXCLUDED.decor,
                                photo_video = EXCLUDED.photo_video,
                                attire_beauty = EXCLUDED.attire_beauty,
                                entertainment = EXCLUDED.entertainment,
                                logistics = EXCLUDED.logistics,
                                buffer = EXCLUDED.buffer,
                                total_budget_inr = EXCLUDED.total_budget_inr,
                                updated_at = EXCLUDED.updated_at;
                            """,
                            event_id,
                            b.venue,
                            b.catering,
                            b.decor,
                            b.photo_video,
                            b.attire_beauty,
                            b.entertainment,
                            b.logistics,
                            b.buffer,
                            b.total_budget_inr,
                            profile.updated_at,
                            profile.updated_at,
                        )

                    # 3. Synchronize milestone statuses
                    for mid, st in profile.milestone_statuses.items():
                        await conn.execute(
                            """
                            INSERT INTO public.event_milestone_statuses (
                                event_id, milestone_id, status, created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (event_id, milestone_id) DO UPDATE SET
                                status = EXCLUDED.status,
                                updated_at = EXCLUDED.updated_at;
                            """,
                            event_id,
                            mid,
                            st.value,
                            profile.updated_at,
                            profile.updated_at,
                        )

                    # 4. Synchronize vendor checklist items
                    for item in profile.vendor_checklist:
                        await conn.execute(
                            """
                            INSERT INTO public.event_vendor_checklist_items (
                                id, event_id, category, title, description, status,
                                due_date, days_before_event, priority, notes,
                                vendor_name, booking_status, created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                            ON CONFLICT (id) DO UPDATE SET
                                category = EXCLUDED.category,
                                title = EXCLUDED.title,
                                description = EXCLUDED.description,
                                status = EXCLUDED.status,
                                due_date = EXCLUDED.due_date,
                                days_before_event = EXCLUDED.days_before_event,
                                priority = EXCLUDED.priority,
                                notes = EXCLUDED.notes,
                                vendor_name = EXCLUDED.vendor_name,
                                booking_status = EXCLUDED.booking_status,
                                updated_at = EXCLUDED.updated_at;
                            """,
                            item.id,
                            event_id,
                            item.category.value,
                            item.title,
                            item.description,
                            item.status.value,
                            item.due_date,
                            item.days_before_event,
                            item.priority.value,
                            item.notes,
                            item.vendor_name,
                            item.booking_status.value,
                            item.created_at,
                            item.updated_at,
                        )

                    # 5. Synchronize recovery records and actions
                    for rec in profile.recovery_records:
                        plan_json = json.dumps(rec.recovery_plan.model_dump(mode="json"))
                        await conn.execute(
                            """
                            INSERT INTO public.crisis_recovery_records (
                                recovery_id, event_id, crisis_type, severity, description,
                                recovery_plan, source, status, total_actions, completed_actions,
                                created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                            ON CONFLICT (recovery_id) DO UPDATE SET
                                status = EXCLUDED.status,
                                description = EXCLUDED.description,
                                completed_actions = EXCLUDED.completed_actions,
                                updated_at = EXCLUDED.updated_at;
                            """,
                            rec.recovery_id,
                            event_id,
                            rec.crisis_type,
                            rec.severity,
                            rec.description,
                            plan_json,
                            rec.source,
                            rec.status.value,
                            rec.total_actions,
                            rec.completed_actions,
                            rec.created_at,
                            rec.updated_at,
                        )
                        for act in rec.actions:
                            await conn.execute(
                                """
                                INSERT INTO public.crisis_recovery_actions (
                                    action_id, recovery_id, event_id, title, description,
                                    priority, status, notes, created_at, updated_at
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                                ON CONFLICT (action_id) DO UPDATE SET
                                    status = EXCLUDED.status,
                                    notes = EXCLUDED.notes,
                                    updated_at = EXCLUDED.updated_at;
                                """,
                                act.action_id,
                                rec.recovery_id,
                                event_id,
                                act.title,
                                act.description,
                                act.priority,
                                act.status.value,
                                act.notes,
                                act.created_at,
                                act.updated_at,
                            )
                if profile.user_id != owner_id:
                    profile = profile.model_copy(update={"user_id": owner_id})
                return profile
            except asyncpg.IntegrityConstraintViolationError as err:
                raise RepositoryIntegrityError(f"Database constraint violation on update: {err}") from err
            except Exception as exc:
                if isinstance(exc, (RepositoryError,)):
                    raise
                raise RepositoryError(f"Failed to update event '{event_id}': {exc}") from exc

    async def list(
        self, skip: int = 0, limit: int = 50, user_id: UUID | None = None
    ) -> tuple[list[EventProfile], int]:
        """Return a paginated slice of stored events belonging to user_id, ordered newest first."""
        effective_user_id = user_id or self._default_user_id
        if effective_user_id is None:
            return [], 0

        async with self._acquire() as conn:
            try:
                async with conn.transaction():
                    await self._set_rls_context(conn, effective_user_id)
                    total: int = await conn.fetchval(
                        "SELECT COUNT(*) FROM public.events WHERE user_id = $1;", effective_user_id
                    )
                    rows = await conn.fetch(
                        """
                        SELECT event_id
                        FROM public.events
                        WHERE user_id = $1
                        ORDER BY updated_at DESC
                        OFFSET $2 LIMIT $3;
                        """,
                        effective_user_id,
                        skip,
                        limit,
                    )
                    profiles: list[EventProfile] = []
                    for r in rows:
                        p = await self._fetch_profile_in_conn(conn, r["event_id"], effective_user_id)
                        if p:
                            profiles.append(p)
                    return profiles, total
            except Exception as exc:
                if isinstance(exc, (RepositoryError,)):
                    raise
                raise RepositoryError(f"Failed to list events: {exc}") from exc

    async def delete(self, event_id: str, user_id: UUID | None = None) -> bool:
        """Delete an event profile from PostgreSQL (cascading deletes child rows)."""
        effective_user_id = user_id or self._default_user_id
        if effective_user_id is None:
            return False

        async with self._acquire() as conn:
            try:
                async with conn.transaction():
                    await self._set_rls_context(conn, effective_user_id)
                    res = await conn.execute(
                        "DELETE FROM public.events WHERE event_id = $1 AND user_id = $2;",
                        event_id,
                        effective_user_id,
                    )
                    return res == "DELETE 1"
            except Exception as exc:
                raise RepositoryError(f"Failed to delete event '{event_id}': {exc}") from exc

    async def count(self, user_id: UUID | None = None) -> int:
        """Return the current number of events stored for user_id."""
        effective_user_id = user_id or self._default_user_id
        if effective_user_id is None:
            return 0

        async with self._acquire() as conn:
            try:
                async with conn.transaction():
                    await self._set_rls_context(conn, effective_user_id)
                    count_val: int = await conn.fetchval(
                        "SELECT COUNT(*) FROM public.events WHERE user_id = $1;", effective_user_id
                    )
                    return count_val
            except Exception as exc:
                raise RepositoryError(f"Failed to count events: {exc}") from exc

    async def clear(self) -> None:
        """Remove all stored events. Primarily used for test isolation."""
        async with self._acquire() as conn:
            try:
                await conn.execute("DELETE FROM public.events;")
            except Exception as exc:
                raise RepositoryError(f"Failed to clear events: {exc}") from exc
