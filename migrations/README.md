# PlanProof AI — Database Migrations

This directory contains versioned PostgreSQL migrations and Row Level Security (RLS) policies for PlanProof AI's persistent data layer on Supabase.

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

### Rollback / Down Migrations
Symmetrical reversal scripts are located in [`migrations/down/`](./down/) and must be executed in reverse order (`00009` down to `00001`).

---

## 2. Required Supabase Environment & Role Architecture

PlanProof AI migrations are designed for **Supabase PostgreSQL 15+** with GoTrue authentication:
- **Supabase Auth Integration**: Application tables reference `auth.users(id)` with cascade deletion. No fake or stub `auth.users` table exists in application migrations.
- **Supabase Built-in Identity**: RLS policies evaluate tenant identity using `auth.uid()`, which is natively provided and maintained by Supabase Auth in the `auth` schema.
- **Application Database Connection Role**:
  - The runtime connection role (e.g. `planproof_app` or `planproof_test_app`) **must NOT** have `BYPASSRLS` or superuser privileges.
  - The connection role must be granted membership in `authenticated` (`GRANT authenticated TO <app_role>;`) so it can establish transaction-scoped user claims via `set_config('role', 'authenticated', true)`.
  - In plain PostgreSQL testing environments, test harnesses initialize mock auth tables separately without placing unsafe stubs into application migrations.

---

## 3. How to Apply Migrations

### Option A: Using Supabase CLI (Recommended)
```bash
# Start local Supabase containers (if using local development)
supabase start

# Apply all pending migrations in order
supabase db push
```

### Option B: Using `psql` Connection Pooler
```bash
# Export your sanitized database URL (transaction pooler port 6543)
export DATABASE_URL="postgresql://postgres.<project-ref>:<db-password>@<pooler-host>:6543/postgres"

# Apply sequentially
for file in migrations/000*.sql; do
    echo "Applying $file..."
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"
done
```

### Option C: Using Supabase Dashboard SQL Editor
Copy and paste the contents of files `00001` through `00008` sequentially into the SQL Editor in your Supabase project dashboard and click **Run**.

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

---

## 5. Rollback and Recovery

If a migration fails or must be rolled back:

```bash
for file in migrations/down/000*.sql; do
    echo "Reverting $file..."
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"
done
```

---

## 6. Unverified Checks & Intentional Boundaries for Step 1B

The following checks remain intentionally unverified in Step 1B to preserve repository stability:
1. **Live Database Connectivity**: No active database connection was established during this step. No production or remote Supabase instance was touched.
2. **Runtime Policy Enforcement**: RLS policies have been statically validated for SQL syntax, column mapping, and dependency integrity, but runtime enforcement against live Supabase JWTs will be verified in Step 1C/1D when the repository and auth layers are connected.
3. **Application Decoupling**: FastAPI continues using the ephemeral in-memory `EventStore` until Step 1C/1D explicitly introduces database repositories.
