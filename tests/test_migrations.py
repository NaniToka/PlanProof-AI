"""Automated tests validating SQL migration structure, schema definitions, and RLS policies."""

from pathlib import Path
import re
import pytest

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"
DOWN_MIGRATIONS_DIR = MIGRATIONS_DIR / "down"

REQUIRED_TABLES = [
    "profiles",
    "events",
    "event_budgets",
    "event_milestone_statuses",
    "event_vendor_checklist_items",
    "crisis_recovery_records",
    "crisis_recovery_actions",
]


def test_migrations_directory_exists() -> None:
    """Verify that migrations/ and migrations/down/ directories exist and contain files."""
    assert MIGRATIONS_DIR.exists() and MIGRATIONS_DIR.is_dir()
    assert DOWN_MIGRATIONS_DIR.exists() and DOWN_MIGRATIONS_DIR.is_dir()
    assert (MIGRATIONS_DIR / "README.md").exists()


def test_migration_files_sequential_naming() -> None:
    """Verify that migration files follow the 5-digit sequential numbering convention."""
    up_files = sorted([f.name for f in MIGRATIONS_DIR.glob("*.sql")])
    down_files = sorted([f.name for f in DOWN_MIGRATIONS_DIR.glob("*.sql")])

    assert len(up_files) == 8, f"Expected 8 migration files, found {len(up_files)}: {up_files}"
    assert len(down_files) == 8, f"Expected 8 down migration files, found {len(down_files)}: {down_files}"

    expected_prefixes = [f"{i:05d}_" for i in range(1, 9)]
    for prefix, filename in zip(expected_prefixes, up_files):
        assert filename.startswith(prefix), f"File {filename} does not start with expected prefix {prefix}"


def test_all_seven_tables_created() -> None:
    """Verify that all 7 required domain tables are created across the migration files."""
    all_sql = "\n".join(f.read_text(encoding="utf-8") for f in MIGRATIONS_DIR.glob("*.sql"))

    for table in REQUIRED_TABLES:
        pattern = rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\b"
        assert re.search(pattern, all_sql, re.IGNORECASE) is not None, (
            f"Table public.{table} creation statement missing in migrations."
        )


def test_events_table_schema_integrity() -> None:
    """Verify critical columns, foreign keys, and constraints on public.events."""
    events_sql = (MIGRATIONS_DIR / "00002_create_events.sql").read_text(encoding="utf-8")

    # Primary key and user ownership FK
    assert "event_id TEXT PRIMARY KEY" in events_sql
    assert "user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE" in events_sql

    # Domain constraints matching Pydantic rules
    assert "chk_event_type CHECK" in events_sql
    assert "chk_city_tier CHECK" in events_sql
    assert "chk_guest_count CHECK" in events_sql
    assert "chk_total_budget_inr CHECK" in events_sql
    assert "chk_language CHECK" in events_sql

    # Indexes
    assert "idx_events_user_id" in events_sql
    assert "idx_events_user_updated_at" in events_sql


def test_budget_table_sum_integrity() -> None:
    """Verify that public.event_budgets enforces the 8 canonical categories and sum invariant."""
    budget_sql = (MIGRATIONS_DIR / "00003_create_event_budgets.sql").read_text(encoding="utf-8")

    canonical_categories = [
        "venue",
        "catering",
        "decor",
        "photo_video",
        "attire_beauty",
        "entertainment",
        "logistics",
        "buffer",
        "total_budget_inr",
    ]
    for cat in canonical_categories:
        assert cat in budget_sql, f"Canonical category '{cat}' missing from event_budgets table."

    # Mathematical integrity constraint
    assert "chk_budget_sum_equals_total" in budget_sql
    assert "venue + catering + decor + photo_video + attire_beauty + entertainment + logistics + buffer = total_budget_inr" in budget_sql


def test_vendor_checklist_items_table_integrity() -> None:
    """Verify that public.event_vendor_checklist_items enforces domain categories and booking progression."""
    vendor_sql = (MIGRATIONS_DIR / "00005_create_event_vendor_checklist_items.sql").read_text(encoding="utf-8")

    assert "chk_vendor_category CHECK" in vendor_sql
    assert "chk_vendor_status CHECK" in vendor_sql
    assert "chk_vendor_booking_status CHECK" in vendor_sql
    assert "chk_vendor_priority CHECK" in vendor_sql
    assert "REFERENCES public.events(event_id) ON DELETE CASCADE" in vendor_sql


def test_crisis_recovery_records_and_actions_integrity() -> None:
    """Verify that crisis recovery records and actions preserve plans, actions, and cascading."""
    records_sql = (MIGRATIONS_DIR / "00006_create_crisis_recovery_records.sql").read_text(encoding="utf-8")
    actions_sql = (MIGRATIONS_DIR / "00007_create_crisis_recovery_actions.sql").read_text(encoding="utf-8")

    assert "recovery_plan JSONB NOT NULL" in records_sql
    assert "REFERENCES public.events(event_id) ON DELETE CASCADE" in records_sql
    assert "chk_recovery_severity CHECK" in records_sql

    assert "REFERENCES public.crisis_recovery_records(recovery_id) ON DELETE CASCADE" in actions_sql
    assert "REFERENCES public.events(event_id) ON DELETE CASCADE" in actions_sql
    assert "chk_action_status CHECK" in actions_sql


def test_rls_enabled_on_all_seven_tables() -> None:
    """Verify that Row Level Security is explicitly enabled on all 7 tables in migration 00008."""
    rls_sql = (MIGRATIONS_DIR / "00008_enable_row_level_security.sql").read_text(encoding="utf-8")

    for table in REQUIRED_TABLES:
        pattern = rf"ALTER\s+TABLE\s+public\.{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY;"
        assert re.search(pattern, rls_sql, re.IGNORECASE) is not None, (
            f"RLS enablement missing for public.{table} in migration 00008"
        )


def test_rls_policies_scope_and_anti_reassignment() -> None:
    """Verify multi-tenant policies: authenticated only, parent ownership, and anti-reassignment."""
    rls_sql = (MIGRATIONS_DIR / "00008_enable_row_level_security.sql").read_text(encoding="utf-8")

    # Anti-reassignment check: events update must check auth.uid() = user_id on WITH CHECK
    assert "WITH CHECK (auth.uid() = user_id)" in rls_sql

    # Child tables must use EXISTS subquery on public.events
    child_tables = [
        "event_budgets",
        "event_milestone_statuses",
        "event_vendor_checklist_items",
        "crisis_recovery_records",
        "crisis_recovery_actions",
    ]
    for table in child_tables:
        subquery_pattern = rf"EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+public\.events\s+WHERE\s+events\.event_id\s*=\s*{table}\.event_id\s+AND\s+events\.user_id\s*=\s*auth\.uid\(\)\s*\)"
        assert re.search(subquery_pattern, rls_sql, re.IGNORECASE) is not None, (
            f"Child table public.{table} missing parent event ownership subquery in RLS policies."
        )

    # Every policy must be restricted TO authenticated
    assert "TO authenticated" in rls_sql


def test_down_migrations_match_up_migrations() -> None:
    """Verify that down migrations cleanly reverse all created tables and triggers."""
    for table in REQUIRED_TABLES:
        table_found = False
        for down_file in DOWN_MIGRATIONS_DIR.glob("*.sql"):
            content = down_file.read_text(encoding="utf-8")
            if f"DROP TABLE IF EXISTS public.{table}" in content:
                table_found = True
                break
        assert table_found, f"Missing DROP TABLE statement for public.{table} in migrations/down/"
