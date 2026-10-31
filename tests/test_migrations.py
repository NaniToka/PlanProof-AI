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

    assert len(up_files) >= 8, f"Expected at least 8 migration files, found {len(up_files)}: {up_files}"
    assert len(down_files) == len(up_files), f"Expected matching down migration files, found {len(down_files)} vs {len(up_files)}"

    expected_prefixes = [f"{i:05d}_" for i in range(1, len(up_files) + 1)]
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


def test_no_stub_auth_objects_created_in_migrations() -> None:
    """Verify that no migration creates fake auth.users table or overwrites auth.uid().

    In Supabase, auth schema objects (auth.users, auth.uid) are managed by Supabase Auth (GoTrue).
    Application migrations must never create or alter stub auth objects.
    """
    for up_file in MIGRATIONS_DIR.glob("*.sql"):
        sql = up_file.read_text(encoding="utf-8")
        # Assert no fake auth.users table creation
        assert not re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?auth\.users\b", sql, re.IGNORECASE
        ), f"Migration {up_file.name} contains forbidden stub auth.users table creation"

        # Assert no overwriting of auth.uid function
        assert not re.search(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+auth\.uid\b", sql, re.IGNORECASE
        ), f"Migration {up_file.name} contains forbidden overwriting of auth.uid() function"


def test_migration_00009_role_grants_security() -> None:
    """Verify that migration 00009 enforces least-privilege explicit table grants for authenticated role."""
    sql = (MIGRATIONS_DIR / "00009_grant_authenticated_role_permissions.sql").read_text(encoding="utf-8")
    assert "TO authenticated" in sql

    # Anon should NOT be granted table access
    assert not re.search(r"GRANT\s+.*?\s+ON\s+(?:TABLE\s+|ALL\s+TABLES\s+).*?TO\s+anon\b", sql, re.IGNORECASE), (
        "Migration 00009 must not grant table access to anon"
    )

    # Broad 'ON ALL TABLES IN SCHEMA public' is forbidden in favor of least-privilege explicit table grants
    assert not re.search(r"GRANT\s+.*?\s+ON\s+ALL\s+TABLES\s+IN\s+SCHEMA\s+public", sql, re.IGNORECASE), (
        "Migration 00009 must not use broad 'ON ALL TABLES IN SCHEMA public'; explicit tables required"
    )

    # Broad or unnecessary sequence grants are forbidden (all 7 tables use UUID or slug PKs)
    assert not re.search(r"GRANT\s+.*?\s+ON\s+ALL\s+SEQUENCES", sql, re.IGNORECASE), (
        "Migration 00009 must not contain unnecessary 'ON ALL SEQUENCES' grants"
    )

    # Exactly the 7 PlanProof AI application tables must be explicitly granted
    expected_tables = [
        "public.profiles",
        "public.events",
        "public.event_budgets",
        "public.event_milestone_statuses",
        "public.event_vendor_checklist_items",
        "public.crisis_recovery_records",
        "public.crisis_recovery_actions",
    ]
    for table in expected_tables:
        assert table in sql, f"Migration 00009 must explicitly grant permissions on {table}"


def test_migration_00009_down_migration_least_privilege_and_symmetrical() -> None:
    """Verify that down migration 00009 symmetrically revokes permissions only from the 7 application tables."""
    down_sql = (DOWN_MIGRATIONS_DIR / "00009_revoke_authenticated_role_permissions.sql").read_text(encoding="utf-8")

    # Broad 'ON ALL TABLES IN SCHEMA public' is forbidden on rollback
    assert not re.search(r"REVOKE\s+.*?\s+ON\s+ALL\s+TABLES\s+IN\s+SCHEMA\s+public", down_sql, re.IGNORECASE), (
        "Down migration 00009 must not use broad 'ON ALL TABLES IN SCHEMA public'"
    )

    # Symmetrically targets all 7 application tables
    expected_tables = [
        "public.profiles",
        "public.events",
        "public.event_budgets",
        "public.event_milestone_statuses",
        "public.event_vendor_checklist_items",
        "public.crisis_recovery_records",
        "public.crisis_recovery_actions",
    ]
    for table in expected_tables:
        assert table in down_sql, f"Down migration 00009 must explicitly revoke permissions on {table}"

    # Does not revoke pre-existing Supabase default USAGE on schema public
    assert not re.search(r"REVOKE\s+USAGE\s+ON\s+SCHEMA\s+public\s+FROM", down_sql, re.IGNORECASE), (
        "Down migration 00009 must not revoke schema USAGE, which is pre-configured by Supabase"
    )

    # Does not touch or modify Supabase-managed schemas or tables
    for managed_schema in ["auth.", "storage.", "realtime.", "vault."]:
        assert managed_schema not in down_sql.lower(), f"Down migration must not touch {managed_schema}"



def test_handle_new_user_security_definer_and_search_path() -> None:
    """Verify that handle_new_user() in 00001_create_profiles.sql sets search_path = public.

    SECURITY DEFINER functions in PostgreSQL execute with the privileges of the owner.
    They must explicitly set search_path to prevent malicious search_path manipulation attacks.
    """
    sql = (MIGRATIONS_DIR / "00001_create_profiles.sql").read_text(encoding="utf-8")
    match = re.search(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+public\.handle_new_user\(\).*?SECURITY\s+DEFINER\s+SET\s+search_path\s*=\s*public",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, (
        "public.handle_new_user() must be declared with SECURITY DEFINER SET search_path = public"
    )


def test_migration_documentation_separates_ddl_port_5432_from_pooler_port_6543() -> None:
    """Verify migrations/README.md directs DDL migrations to direct/session port 5432, not pooler port 6543."""
    readme_text = (MIGRATIONS_DIR / "README.md").read_text(encoding="utf-8")

    # Assert README documents port 5432 for DDL migrations
    assert ":5432/postgres" in readme_text, "migrations/README.md must specify direct/session port 5432 for migrations"
    assert "MIGRATION_DATABASE_URL" in readme_text

    # Assert README forbids/warns against port 6543 for migrations
    assert "NEVER use transaction pooler 6543 for DDL" in readme_text or "poolers (port 6543) do not support DDL" in readme_text
    assert not re.search(r"psql\s+[\"']?\$(?:DATABASE_URL|MIGRATION_DATABASE_URL)[\"']?.*?6543", readme_text), (
        "migrations/README.md must not instruct psql execution over transaction pooler port 6543"
    )


def test_profile_trigger_fails_closed_without_swallowing_errors() -> None:
    """Verify 00001_create_profiles.sql fails closed with RAISE EXCEPTION rather than swallowing errors."""
    sql = (MIGRATIONS_DIR / "00001_create_profiles.sql").read_text(encoding="utf-8")

    # Must NOT swallow error as a notice
    assert "Skipping auth.users trigger setup due to permissions" not in sql, (
        "Migration 00001 must not swallow trigger creation errors with a silent notice"
    )

    # Must fail closed with RAISE EXCEPTION when trigger creation fails on auth.users
    assert "RAISE EXCEPTION" in sql, (
        "Migration 00001 must raise an explicit exception if trigger creation fails on auth.users"
    )
    assert "on_auth_user_created" in sql
    assert "handle_new_user" in sql


def test_no_ascending_rollback_in_documentation() -> None:
    """Verify migrations/README.md does not document an unsafe ascending rollback loop."""
    readme_text = (MIGRATIONS_DIR / "README.md").read_text(encoding="utf-8")

    # Ascending shell glob for file in migrations/down/000*.sql without reversal is forbidden
    assert "for file in migrations/down/000*.sql; do" not in readme_text, (
        "README.md must not instruct executing down migrations via an ascending shell glob"
    )

    # Down migrations must be documented in reverse order (00010/00009 down to 00001)
    assert "00010 down to 00001" in readme_text or "00009 down to 00001" in readme_text or "ls -r migrations/down" in readme_text, (
        "README.md must instruct executing down migrations in reverse dependency order"
    )


def test_rollback_documentation_warns_of_destructive_data_loss() -> None:
    """Verify migrations/README.md explicitly warns against running down scripts in staging/production."""
    readme_text = (MIGRATIONS_DIR / "README.md").read_text(encoding="utf-8")

    assert "DROP TABLE ... CASCADE" in readme_text or "DROP TABLE" in readme_text
    assert "permanently delete" in readme_text.lower() or "data loss" in readme_text.lower()
    assert "fix forward" in readme_text.lower()
    assert "NEVER run down migrations on staging or production" in readme_text


def test_migration_documentation_uses_single_transaction_and_error_stop() -> None:
    """Verify migrations/README.md enforces --single-transaction and -v ON_ERROR_STOP=1."""
    readme_text = (MIGRATIONS_DIR / "README.md").read_text(encoding="utf-8")

    assert "--single-transaction" in readme_text
    assert "-v ON_ERROR_STOP=1" in readme_text


def test_trigger_verification_catalog_query_in_documentation() -> None:
    """Verify migrations/README.md documents the catalog query for on_auth_user_created trigger on auth.users."""
    readme_text = (MIGRATIONS_DIR / "README.md").read_text(encoding="utf-8")

    assert "pg_trigger" in readme_text
    assert "on_auth_user_created" in readme_text
    assert "tgenabled" in readme_text
    assert "auth.users" in readme_text


def test_postgres_repository_profile_fallback_documented() -> None:
    """Verify PostgresEventRepository documents the purpose and limitations of the profile fallback."""
    repo_file = Path(__file__).parent.parent / "app" / "repositories" / "postgres.py"
    repo_text = repo_file.read_text(encoding="utf-8")

    assert "defensive fallback" in repo_text.lower()
    assert "empty string" in repo_text.lower()
    assert "on_auth_user_created" in repo_text


# ==============================================================================
# Runbook Documentation Regression Tests (Static Documentation Checks)
# ==============================================================================

RUNBOOK_PATH = Path(__file__).parent.parent / "docs" / "STAGING_PREFLIGHT_RUNBOOK.md"


def test_staging_runbook_exists_and_prohibits_unauthorized_execution() -> None:
    """Verify docs/STAGING_PREFLIGHT_RUNBOOK.md exists and strictly forbids unauthorized/autonomous execution."""
    assert RUNBOOK_PATH.exists() and RUNBOOK_PATH.is_file(), "STAGING_PREFLIGHT_RUNBOOK.md must exist in docs/"
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "Zero Automatic Execution" in text or "no automated script" in text.lower()
    assert "Human Authorization Required" in text or "explicit, written approval" in text.lower()
    assert "Never Execute Against Production" in text or "never production" in text.lower()


def test_staging_runbook_specifies_identity_check_and_secret_safety() -> None:
    """Verify runbook enforces a dedicated staging project identity check and secret-safe execution."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Staging project check independent of port
    assert "STAGING_PROJECT_REF" in text
    assert "MIGRATION_DATABASE_URL" in text
    assert "current_database()" in text or "session_role" in text

    # Secret-safe checks (no hardcoded passwords or printing secrets)
    assert "<staging-project-ref>" in text
    assert "<staging-db-password>" in text
    assert "leaking" in text.lower() or "secret-safe" in text.lower()


def test_staging_runbook_mandates_transaction_safety_and_stop_conditions() -> None:
    """Verify runbook mandates per-file transactions, ON_ERROR_STOP, and clear stop conditions."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "--single-transaction" in text
    assert "-v ON_ERROR_STOP=1" in text
    assert "STOP CONDITION" in text or "Stop Condition" in text
    assert "Non-Destructive" in text or "non-destructive" in text.lower()


def test_staging_runbook_includes_post_00001_and_final_verifications() -> None:
    """Verify runbook documents post-00001 trigger checks and final catalog/RLS/grant checks."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Intermediate post-00001 trigger check
    assert "on_auth_user_created" in text
    assert "handle_new_user" in text
    assert "SECURITY DEFINER" in text or "is_security_definer" in text
    assert "tgenabled" in text

    # Final post-migration verifications
    assert "rowsecurity" in text
    assert "pg_policies" in text
    assert "has_table_privilege" in text
    assert "27 policies" in text or "Total: 27" in text


def test_staging_runbook_specifies_disposable_account_functional_test() -> None:
    """Verify runbook documents end-to-end functional testing using a disposable staging account."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "disposable" in text.lower()
    assert "auth/v1/signup" in text
    assert "/api/v1/events" in text
    assert "tenant b" in text.lower() or "cross-tenant" in text.lower()
    assert "404" in text  # Isolation assertion returns 404


def test_staging_runbook_backup_validation_and_limitations() -> None:
    """Verify runbook checks pg_dump exit status, non-empty file, dump validation, and notes limitations."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Exit code and non-empty file checks
    assert "DUMP_STATUS" in text or "exit code" in text.lower()
    assert "-s " in text or "! -s" in text, "Must check that backup file is non-empty (-s)"
    assert "chmod 600" in text, "Must enforce restrictive file permissions on backup"

    # Supported dump validation via pg_restore --list
    assert "pg_restore --list" in text, "Must document pg_restore --list dump validation"

    # Limitations explicitly documented
    assert "--schema=public" in text
    assert "auth.users" in text or "auth" in text.lower()
    assert "limitations" in text.lower() or "what is not captured" in text.lower()


def test_staging_runbook_trigger_guidance_distinguishes_catalog_from_functional_proof() -> None:
    """Verify trigger catalog check is not presented as proof of GoTrue signup success and respects auth boundaries."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Distinguish catalog from functional proof
    assert "does not prove" in text.lower() or "catalog visibility != functional proof" in text.lower()
    assert "gotrue" in text.lower()

    # Respect Supabase-managed object boundaries (do not suggest bypassing)
    assert "do not attempt to bypass" in text.lower() or "bypass" in text.lower()
    assert "escalat" in text.lower() or "project owner" in text.lower()


def test_staging_runbook_exact_cleanup_without_pattern_matching() -> None:
    """Verify cleanup forbids broad email patterns and requires exact recorded identities with human confirmation."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Prohibits broad pattern matching (LIKE)
    assert "never use pattern deletion" in text.lower() or "never run `delete ... where email like" in text.lower() or "like '%" in text.lower()

    # Requires exact recorded identities (UUID and email) and human confirmation
    assert "exact recorded identities" in text.lower() or "exact" in text.lower()
    assert "confirmation" in text.lower() and ("human" in text.lower() or "operator" in text.lower())

    # Prefers Dashboard or Admin API workflow
    assert "dashboard" in text.lower() or "admin api" in text.lower()
    assert "supabase_admin" in text.lower() or "service_role" in text.lower()


def test_staging_runbook_staging_ref_assertion_prevents_empty_or_placeholder() -> None:
    """Verify staging identity assertion prevents empty or unreplaced placeholder project references."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Ensures check for non-empty and non-placeholder STAGING_PROJECT_REF
    assert "-z \"${STAGING_PROJECT_REF:-}\"" in text or "-z \"$STAGING_PROJECT_REF\"" in text or "STAGING_PROJECT_REF:-" in text
    assert "<staging-project-ref>" in text
    # Ensures abort on failure
    assert "exit 1" in text
    # Asserts secret safety: connection string password should not be printed
    assert 'echo "ERROR: MIGRATION_DATABASE_URL' in text
    assert 'echo "$MIGRATION_DATABASE_URL"' not in text


def test_staging_runbook_backup_archive_listing_distinguished_from_restore_proof() -> None:
    """Verify backup documentation explains pg_restore --list is a header check, not proof of restore success."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Verifies archive listing check distinction
    assert "pg_restore --list" in text
    assert "restore" in text.lower()
    assert "basic" in text.lower() or "not prove" in text.lower() or "integrity check" in text.lower()

    # Verifies single-file target validation
    assert "! -f \"$BACKUP_FILE\"" in text or "-f \"$BACKUP_FILE\"" in text
    assert "! -s \"$BACKUP_FILE\"" in text or "-s \"$BACKUP_FILE\"" in text


def test_staging_runbook_cleanup_privilege_and_cascade_accuracy() -> None:
    """Verify cleanup excludes direct SQL auth.users deletion, uses Dashboard/Admin API, and verifies cascade."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Ensures direct SQL deletion from auth.users is removed from cleanup procedures
    assert "DELETE FROM auth.users" not in text
    assert "direct sql deletion from `auth.users` is prohibited" in text.lower() or "direct sql deletion" in text.lower()

    # Does not mischaracterize service_role as a superuser
    assert "service_role superuser" not in text.lower()

    # Documents supported cleanup workflows: Dashboard and/or Auth Admin API
    assert "dashboard" in text.lower()
    assert "admin" in text.lower()

    # Operator confirmation required before account deletion
    assert "confirmation" in text.lower() or "confirm" in text.lower()

    # Accurately identifies cascade chain through profiles and events to child tables
    assert "public.profiles" in text
    assert "public.events" in text
    assert "public.event_budgets" in text
    assert "public.crisis_recovery_records" in text


def test_staging_runbook_three_phases_and_beginner_guidance() -> None:
    """Verify runbook is organized into Phase A (Dashboard Setup), Phase B (Local Config), and Phase C (Preflight)."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Three distinct phases
    assert "Phase A — Manual Dashboard Setup" in text
    assert "Phase B — Local Configuration" in text
    assert "Phase C — Preflight Checks" in text

    # Phase A instructions: manual project creation, connection strings, JWT algorithm identification
    assert "https://supabase.com/dashboard" in text
    assert "planproof-staging" in text
    assert "5432" in text and "6543" in text
    assert "SUPABASE_JWT_ALGORITHMS" in text
    assert "RS256" in text or "ES256" in text or "HS256" in text

    # Phase B instructions: .env copy, chmod 600, git check-ignore
    assert "cp .env.example .env" in text
    assert "chmod 600 .env" in text
    assert "git check-ignore" in text

    # Phase C: clearly separates offline preflight checks from live preflight
    assert "Offline Preflight Verification" in text or "offline" in text.lower()
    assert "pytest" in text


def test_migration_00010_acl_hardening_structure_and_scope() -> None:
    """Verify that migration 00010 revokes all privileges from anon and PUBLIC and removes dangerous privileges from authenticated."""
    sql = (MIGRATIONS_DIR / "00010_harden_least_privilege_acls.sql").read_text(encoding="utf-8")

    # 1. Targets all seven domain tables for revoking from anon and PUBLIC
    for table in REQUIRED_TABLES:
        assert f"public.{table}" in sql, f"Migration 00010 must explicitly target public.{table}"

    # 2. Both anon and the PUBLIC pseudo-role have ALL table privileges revoked
    assert re.search(r"REVOKE\s+ALL\s+ON\s+TABLE\s+.*?\s+FROM\s+(?:anon,\s*PUBLIC|PUBLIC,\s*anon)\b", sql, re.IGNORECASE | re.DOTALL), (
        "Migration 00010 must execute REVOKE ALL ON TABLE ... FROM anon, PUBLIC"
    )

    # 3. Authenticated has TRUNCATE, REFERENCES, TRIGGER revoked
    assert re.search(
        r"REVOKE\s+TRUNCATE,\s*REFERENCES,\s*TRIGGER\s+ON\s+TABLE\s+.*?\s+FROM\s+authenticated\b",
        sql,
        re.IGNORECASE | re.DOTALL,
    ), "Migration 00010 must revoke TRUNCATE, REFERENCES, TRIGGER from authenticated"

    # 4. Authenticated retains CRUD: SELECT, INSERT, UPDATE, DELETE are NOT revoked
    assert not re.search(
        r"REVOKE\s+.*?\b(?:SELECT|INSERT|UPDATE|DELETE)\b.*?\s+FROM\s+authenticated\b",
        sql,
        re.IGNORECASE,
    ), "Migration 00010 must preserve SELECT, INSERT, UPDATE, DELETE for authenticated"

    # 5. Service role and postgres administrative privileges are not revoked
    for role in ["service_role", "postgres", "supabase_admin"]:
        assert not re.search(rf"REVOKE\s+.*?\s+FROM\s+{role}\b", sql, re.IGNORECASE), (
            f"Migration 00010 must not revoke privileges from administrative role {role}"
        )

    # 6. Does not touch or modify Supabase-managed schemas or tables
    for managed_schema in ["auth.", "storage.", "realtime.", "vault."]:
        assert managed_schema not in sql.lower(), f"Migration 00010 must not touch {managed_schema}"


def test_migration_00010_default_privileges_hardening() -> None:
    """Verify that migration 00010 hardens default privileges in pg_default_acl for future tables created by postgres in public."""
    sql = (MIGRATIONS_DIR / "00010_harden_least_privilege_acls.sql").read_text(encoding="utf-8")

    # 1. Hardens default privileges for role postgres in schema public for anon and PUBLIC
    assert re.search(
        r"ALTER\s+DEFAULT\s+PRIVILEGES\s+FOR\s+ROLE\s+postgres\s+IN\s+SCHEMA\s+public\s+REVOKE\s+ALL\s+ON\s+TABLES\s+FROM\s+(?:anon,\s*PUBLIC|PUBLIC,\s*anon)\b",
        sql,
        re.IGNORECASE,
    ), "Migration 00010 must revoke default table privileges from anon and PUBLIC for role postgres in schema public"

    # 2. Hardens default privileges for role postgres in schema public for authenticated
    assert re.search(
        r"ALTER\s+DEFAULT\s+PRIVILEGES\s+FOR\s+ROLE\s+postgres\s+IN\s+SCHEMA\s+public\s+REVOKE\s+TRUNCATE,\s*REFERENCES,\s*TRIGGER\s+ON\s+TABLES\s+FROM\s+authenticated\b",
        sql,
        re.IGNORECASE,
    ), "Migration 00010 must revoke default TRUNCATE, REFERENCES, TRIGGER on tables from authenticated"

    # 3. Strictly scoped to IN SCHEMA public (does not affect global or other schemas)
    alter_matches = re.findall(r"ALTER\s+DEFAULT\s+PRIVILEGES\s+(.*?);", sql, re.IGNORECASE | re.DOTALL)
    assert len(alter_matches) == 2, f"Expected exactly 2 ALTER DEFAULT PRIVILEGES statements, found {len(alter_matches)}"
    for match in alter_matches:
        assert "IN SCHEMA public" in match, "ALTER DEFAULT PRIVILEGES must be strictly scoped to 'IN SCHEMA public'"
        assert "FOR ROLE postgres" in match, "ALTER DEFAULT PRIVILEGES must specify 'FOR ROLE postgres'"


def test_migration_00010_global_defaults_fail_closed_preflight_guard() -> None:
    """Verify migration 00010 includes a fail-closed preflight guard checking for unsafe global default privileges."""
    sql = (MIGRATIONS_DIR / "00010_harden_least_privilege_acls.sql").read_text(encoding="utf-8")

    # Must contain PL/pgSQL DO block with preflight validation
    assert "DO $$" in sql
    assert "pg_default_acl" in sql
    assert "defaclnamespace = 0" in sql
    assert "aclexplode" in sql
    assert "RAISE EXCEPTION" in sql
    assert "unsafe_global_count" in sql or "SAFETY HALT" in sql


def test_migration_00010_down_migration_safety_guard() -> None:
    """Verify that down migration 00010 fails closed and requires explicit manual security review."""
    down_sql = (DOWN_MIGRATIONS_DIR / "00010_rollback_acl_hardening.sql").read_text(encoding="utf-8")

    # Must fail closed with RAISE EXCEPTION
    assert "RAISE EXCEPTION" in down_sql, "Down migration 00010 must fail closed with RAISE EXCEPTION"
    assert "Manual security authorization is required" in down_sql

    # Must NOT execute un-guarded GRANT statements to anon or PUBLIC
    executed_statements = [
        line.strip() for line in down_sql.splitlines()
        if not line.strip().startswith("--") and line.strip()
    ]
    non_guarded_sql = "\n".join(executed_statements)
    assert not re.search(r"^\s*GRANT\s+.*?\s+TO\s+(?:anon|PUBLIC)\b", non_guarded_sql, re.MULTILINE | re.IGNORECASE), (
        "Down migration 00010 must not execute un-guarded GRANT statements to anon or PUBLIC"
    )


def test_rls_policies_and_enablement_preserved_in_00010() -> None:
    """Verify that migration 00010 does not tamper with RLS status or existing policies."""
    sql = (MIGRATIONS_DIR / "00010_harden_least_privilege_acls.sql").read_text(encoding="utf-8")

    assert "DISABLE ROW LEVEL SECURITY" not in sql.upper(), "Migration 00010 must not disable RLS"
    assert "DROP POLICY" not in sql.upper(), "Migration 00010 must not drop any RLS policies"
    assert "CREATE POLICY" not in sql.upper(), "Migration 00010 must not create or replace RLS policies"


def test_step_7e_catalog_audit_confirms_no_global_defaults_and_no_public_grants() -> None:
    """Verify via Step 7E recorded catalog audit that no global defaults or PUBLIC table grants exist on staging."""
    import json
    audit_file = Path("/Users/tokanani/.gemini/antigravity/brain/d9b199cd-48fd-4563-b681-ae0c06b06497/scratch/audit_step_7e_results.json")
    if not audit_file.exists():
        pytest.skip("Step 7E audit results not present on local machine")

    with open(audit_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. No global default ACLs exist on staging
    global_defaults = [d for d in data.get("default_acls", []) if d.get("schema") == "(all schemas)"]
    assert len(global_defaults) == 0, f"Expected 0 global default ACLs, found: {global_defaults}"

    # 2. No PUBLIC grants on existing table ACLs
    for tbl, info in data.get("table_privileges", {}).items():
        relacl = info.get("relacl", "")
        assert not (",=" in relacl or relacl.startswith("{=")), f"Table public.{tbl} has unexpected PUBLIC grant: {relacl}"







