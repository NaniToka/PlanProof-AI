# PlanProof AI — Database Migrations

This directory contains versioned PostgreSQL migrations and Row Level Security (RLS) policies for PlanProof AI's persistent data layer on Supabase.

For staging execution, operator preflight procedures, and end-to-end verification workflows, follow the 3-phase [Staging Preflight Runbook](../docs/STAGING_PREFLIGHT_RUNBOOK.md):
- **Phase A — Manual Dashboard Setup**: Step-by-step guidance for creating a staging project, obtaining connection strings, and inspecting JWT signing keys.
- **Phase B — Local Configuration**: Safe `.env` variable configuration and secret protection.
- **Phase C — Preflight Checks & Staging Verification**: Offline test gates, live target identity assertion, validated logical backups, and per-file transaction migrations.

---

## 1. Migration Ordering

Migrations are numbered sequentially and must be applied in the following dependency order:

| Step | File | Description | Target Table / Scope |
| :---: | :--- | :--- | :--- |
| **01** | [`00001_create_profiles.sql`](./00001_create_profiles.sql) | User accounts synced with `auth.users(id)` | `public.profiles` |
| **02** | [`00002_create_events.sql`](./00002_create_events.sql) | Core event planning profile with owner relationship | `public.events` |
| **03** | [`00003_create_event_budgets.sql`](./00003_create_event_budgets.sql) | Canonical 8-category allocations with sum invariant | `public.event_budgets` |
| **04** | [`00004_create_event_milestone_statuses.sql`](./00004_create_event_milestone_statuses.sql) | Milestone completion checkmarks | `public.event_milestone_statuses` |
| **05** | [`00005_create_event_vendor_checklist_items.sql`](./00005_create_event_vendor_checklist_items.sql) | Vendor coordination tasks and booking progression | `public.event_vendor_checklist_items` |
| **06** | [`00006_create_crisis_recovery_records.sql`](./00006_create_crisis_recovery_records.sql) | Incident recovery plan logs and action tracker headers | `public.crisis_recovery_records` |
| **07** | [`00007_create_crisis_recovery_actions.sql`](./00007_create_crisis_recovery_actions.sql) | Granular actionable recovery steps and execution notes | `public.crisis_recovery_actions` |
| **08** | [`00008_enable_row_level_security.sql`](./00008_enable_row_level_security.sql) | Enable RLS and multi-tenant isolation policies | All 7 tables |
| **09** | [`00009_grant_authenticated_role_permissions.sql`](./00009_grant_authenticated_role_permissions.sql) | Grant authenticated role schema and table permissions | `public` schema |

### Rollback / Down Migrations (Disposable Test Environments Only)
Symmetrical reversal scripts are located in [`migrations/down/`](./down/) and **must strictly be executed in reverse order (`00009` down to `00001`)**:
1. [`00009_revoke_authenticated_role_permissions.sql`](./down/00009_revoke_authenticated_role_permissions.sql)
2. [`00008_disable_row_level_security.sql`](./down/00008_disable_row_level_security.sql)
3. [`00007_drop_crisis_recovery_actions.sql`](./down/00007_drop_crisis_recovery_actions.sql)
4. [`00006_drop_crisis_recovery_records.sql`](./down/00006_drop_crisis_recovery_records.sql)
5. [`00005_drop_event_vendor_checklist_items.sql`](./down/00005_drop_event_vendor_checklist_items.sql)
6. [`00004_drop_event_milestone_statuses.sql`](./down/00004_drop_event_milestone_statuses.sql)
7. [`00003_drop_event_budgets.sql`](./down/00003_drop_event_budgets.sql)
8. [`00002_drop_events.sql`](./down/00002_drop_events.sql)
9. [`00001_drop_profiles.sql`](./down/00001_drop_profiles.sql)

---

## 2. Required Supabase Environment & Role Architecture

PlanProof AI migrations are designed for **Supabase PostgreSQL 15+** with GoTrue authentication:
- **Supabase Auth Integration**: Application tables reference `auth.users(id)` with cascade deletion. No fake or stub `auth.users` table exists in application migrations.
- **Fail-Closed Profile Trigger**: Migration `00001` installs `on_auth_user_created` on `auth.users`. This requires privileged execution (`postgres` / `supabase_admin`). If the executing role lacks required privileges on `auth.users`, migration `00001` **fails closed** with an explicit error rather than silently swallowing the failure.
- **Repository Profile Fallback**: `PostgresEventRepository.create()` includes a defensive fallback insert into `public.profiles` (`INSERT INTO public.profiles ... ON CONFLICT DO NOTHING`) to prevent foreign-key crashes if a user was created in an un-triggered test harness. *Limitation*: This fallback inserts an empty string for `email` and NULL for `full_name` because transaction claims only provide the user UUID. It is a safety-net and not a substitute for the canonical `on_auth_user_created` trigger.
- **Supabase Built-in Identity**: RLS policies evaluate tenant identity using `auth.uid()`, which is natively provided and maintained by Supabase Auth in the `auth` schema.
- **Application Database Connection Role**:
  - The runtime connection role (e.g. `planproof_app` or `planproof_test_app`) **must NOT** have `BYPASSRLS` or superuser privileges.
  - The connection role must be granted membership in `authenticated` (`GRANT authenticated TO <app_role>;`) so it can establish transaction-scoped user claims via `set_config('role', 'authenticated', true)`.
  - In plain PostgreSQL testing environments, test harnesses initialize mock auth tables separately without placing unsafe stubs into application migrations.

---

## 3. How to Apply Migrations

> [!IMPORTANT]
> **Connection Architecture: Migrations vs Runtime Traffic**
> - **Schema Migrations (DDL)**: MUST be executed using a **direct / session connection (port 5432)**, the official Supabase CLI (`supabase db push`), or the Supabase Dashboard SQL Editor. PgBouncer and Supavisor transaction poolers (port 6543) do not support DDL statements, table-level locks, or schema migration transactions.
> - **Application Runtime Traffic (DML)**: Application services connect via the **transaction pooler (port 6543)** for connection scalability, where queries execute inside individual transactions with transaction-scoped RLS claim contexts.
> - Available connection methods depend on your network environment: direct IPv6 host (`db.<project-ref>.supabase.co:5432`), IPv4 session pooler (`aws-0-<region>.pooler.supabase.com:5432`), or Supabase CLI.

### Option A: Using Supabase CLI (Recommended)
```bash
# Link project (if using remote staging/production)
supabase link --project-ref <project-ref>

# Apply all pending migrations in order
supabase db push
```

### Option B: Using `psql` Direct / Session Connection (Port 5432)
```bash
# Export direct/session connection URL (Port 5432 - NEVER use transaction pooler 6543 for DDL)
export MIGRATION_DATABASE_URL="postgresql://postgres.<project-ref>:<db-password>@<direct-host-or-session-pooler>:5432/postgres"

# Apply sequentially (00001 through 00009) in strict forward order with per-file transaction safety
for file in $(ls migrations/000*.sql | sort); do
    echo "Applying $file with transaction safety..."
    psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f "$file"
done
```

> [!NOTE]
> **Per-File Transaction Safety (`--single-transaction`)**
> Each migration file is executed inside its own transaction boundary via `--single-transaction` (`psql -1`). If a statement inside a file fails, that entire file rolls back cleanly and `-v ON_ERROR_STOP=1` immediately halts the loop. Note that migrations do **not** run as a single global transaction across files: any migration files that completed before the failure remain committed and applied.

### Option C: Using Supabase Dashboard SQL Editor
Copy and paste the contents of files `00001` through `00009` sequentially into the SQL Editor in your Supabase project dashboard and click **Run**.

---

## 4. How to Verify Migrations and Policies

After running the migrations, execute the following SQL verification queries:

### 4.1 Verify Table Creation (Expected: 7 tables)
```sql
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'profiles',
    'events',
    'event_budgets',
    'event_milestone_statuses',
    'event_vendor_checklist_items',
    'crisis_recovery_records',
    'crisis_recovery_actions'
  )
ORDER BY tablename;
```

### 4.2 Verify Row Level Security is Enabled (Expected: `rowsecurity = true` for all 7)
```sql
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

### 4.3 Verify RLS Policies (Expected: 27 policies)
```sql
SELECT tablename, policyname, permissive, roles, cmd, qual
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;
```

### 4.4 Verify Foreign Key Constraints and Cascading
```sql
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.referential_constraints AS rc
    ON tc.constraint_name = rc.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
ORDER BY tc.table_name;
```

### 4.5 Verify Profile Provisioning Trigger and Function
```sql
-- 1. Verify public.handle_new_user function exists, is SECURITY DEFINER, and enforces search_path
SELECT
    p.proname,
    p.prosecdef AS is_security_definer,
    p.proconfig AS search_path_config
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'public' AND p.proname = 'handle_new_user';
-- Expected: prosecdef = true, search_path_config = '{search_path=public}'

-- 2. Verify on_auth_user_created trigger exists on auth.users and is enabled
SELECT
    t.tgname AS trigger_name,
    t.tgenabled AS trigger_status,
    c.relname AS table_name,
    n.nspname AS schema_name
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = 'auth'
  AND c.relname = 'users'
  AND t.tgname = 'on_auth_user_created';
-- Expected: 1 row returned, trigger_name = 'on_auth_user_created', trigger_status = 'O' (Enabled)
```

---

## 5. Rollback and Recovery

> [!CAUTION]
> **Destructive Data Loss Warning**:
> The rollback scripts in [`migrations/down/`](./down/) contain destructive `DROP TABLE ... CASCADE` statements. Executing down migrations will **permanently delete** all existing user accounts, events, budgets, checklist items, and crisis recovery records.
> - **NEVER run down migrations on staging or production databases to recover from a failed migration.**
> - For deployed databases, **always fix forward** by addressing the root cause or applying a forward corrective migration (`00010_...`).
> - Destructive rollback procedures require a verified database backup and explicit human authorization.

### Safe Partial-Failure Recovery Protocol (Staging & Production)

If a migration fails mid-sequence (e.g., at file `00004`):
1. **Stop Immediately**: Do not run rollback scripts or blindly re-execute the entire migration directory.
2. **Inspect Current State**: Run verification queries in Section 4 to determine which migration files completed successfully.
3. **Diagnose the Failure**: Review the error log from the failed migration file. Because `--single-transaction` was used, the failed file was completely rolled back, leaving the database at the clean boundary of the previous successful migration.
4. **Resolve the Underlying Cause**: Fix permissions, resolve locks, or adjust environment settings.
5. **Resume Forward Migration**: Re-run migrations starting strictly from the failed migration file through `00009`.

### Disposable / Test Database Teardown Only

If tearing down a disposable local test database where data loss is expected and acceptable, down migrations must be executed in **strict reverse order** (`00009` down to `00001`) to respect foreign-key dependencies:

```bash
# DISPOSABLE TEST DATABASES ONLY - NEVER RUN IN PRODUCTION
# Execute strictly in reverse order (00009 down to 00001)
for file in $(ls -r migrations/down/000*.sql); do
    echo "Reverting $file with transaction safety..."
    psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f "$file"
done
```

---

## 6. Unverified Checks & Intentional Boundaries for Step 1B

The following checks remain intentionally unverified in Step 1B to preserve repository stability:
1. **Live Database Connectivity**: No active database connection was established during this step. No production or remote Supabase instance was touched.
2. **Runtime Policy Enforcement**: RLS policies have been statically validated for SQL syntax, column mapping, and dependency integrity, but runtime enforcement against live Supabase JWTs will be verified in Step 1C/1D when the repository and auth layers are connected.
3. **Application Decoupling**: FastAPI continues using the ephemeral in-memory `EventStore` until Step 1C/1D explicitly introduces database repositories.
