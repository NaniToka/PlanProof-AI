# PlanProof AI — Staging Preflight & Migration Runbook

> [!CRITICAL]
> **GOVERNANCE & SAFETY GATE**:
> This runbook is strictly for **staging environment preflight and verification**.
> - **Zero Automatic Execution**: No automated script, CI/CD pipeline, or AI agent is authorized to execute this runbook autonomously.
> - **Human Authorization Required**: Execution requires explicit, written approval from the designated release engineer or technical lead.
> - **Never Execute Against Production**: Verify target project credentials before issuing any command.
> - **Never Run Rollback Scripts on Shared Databases**: Down migration scripts in `migrations/down/` contain destructive `DROP TABLE ... CASCADE` statements. They are strictly prohibited on staging and production databases.

---

## 1. Preconditions & Authorization Checklist

Before any terminal command is run, the human release engineer must confirm:

- [ ] Written authorization is recorded for this staging migration window.
- [ ] The target Supabase project is confirmed to be **Staging** (project ref matching `<staging-project-ref>`, never production).
- [ ] Network routing permits direct session connections to PostgreSQL port `5432` (e.g. via direct IPv6 host or AWS IPv4 session pooler). Transaction pooler port `6543` must **not** be used for migrations.
- [ ] Staging database credentials are held locally in environment variables and are **never** committed or printed to logs.
- [ ] A dedicated pre-migration logical backup is planned (Section 3).

---

## 2. Target Environment Identity & Secret-Safe Verification

To prevent accidental execution against production or misconfigured instances, perform a dedicated staging-identity check.

### 2.1 Set Up Environment Variables (Secret-Safe)
```bash
# Set staging environment variables (replace placeholders with actual staging credentials)
export STAGING_PROJECT_REF="<staging-project-ref>"
export MIGRATION_DATABASE_URL="postgresql://postgres.<staging-project-ref>:<staging-db-password>@aws-0-<staging-region>.pooler.supabase.com:5432/postgres"

# Optional application runtime URL (for smoke testing)
export STAGING_SUPABASE_URL="https://<staging-project-ref>.supabase.co"
export STAGING_SUPABASE_ANON_KEY="<staging-anon-key>"
```

### 2.2 Secret-Safe Identity Assertion
Verify that the target connection URL references the staging project without printing credentials to the console:

```bash
# Assert connection string targets the intended staging project ref without leaking password
if [[ "$MIGRATION_DATABASE_URL" != *"$STAGING_PROJECT_REF"* ]]; then
    echo "ERROR: MIGRATION_DATABASE_URL does not match STAGING_PROJECT_REF ($STAGING_PROJECT_REF). Aborting!"
    exit 1
fi

# Assert port 5432 is specified for DDL migrations (port 6543 pooler forbidden for DDL)
if [[ "$MIGRATION_DATABASE_URL" == *":6543/"* ]]; then
    echo "ERROR: MIGRATION_DATABASE_URL specifies port 6543 (transaction pooler). DDL requires session port 5432. Aborting!"
    exit 1
fi

echo "Preflight check PASSED: Target matches staging ref [${STAGING_PROJECT_REF}] on session port 5432."
```

### 2.3 Verify Database Identity via SQL
Execute a non-destructive query to confirm database identity and connection role:

```bash
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 -c "
SELECT 
    current_database() AS db_name,
    current_user AS session_role,
    inet_server_addr() AS server_ip;
"
```
*Expected Result:*
- `db_name`: `postgres`
- `session_role`: `postgres` (or administrative release role)
- Stop Condition: If the connection fails or `session_role` is unprivileged (e.g. `anon` or `planproof_app`), **STOP immediately**.

---

## 3. Pre-Migration Staging Backup

Staging databases frequently hold testing datasets, staging test profiles, or seed configurations. To guarantee non-destructive recovery, take a logical schema and data backup prior to applying migrations:

```bash
# Generate a timestamped pre-migration custom format dump
BACKUP_FILE="staging_backup_pre_migration_$(date +%Y%m%d_%H%M%S).dump"

echo "Creating logical backup in ${BACKUP_FILE}..."
pg_dump "$MIGRATION_DATABASE_URL" \
    --schema=public \
    --format=custom \
    --file="$BACKUP_FILE"

echo "Backup completed successfully. Size: $(du -h "$BACKUP_FILE" | cut -f1)"
```

> [!IMPORTANT]
> If any migration failure occurs later, **do NOT execute down scripts** (`migrations/down/`). Use the recovery workflow in Section 4.3 or restore from this backup file via `pg_restore`.

---

## 4. Sequential Migration Execution (Per-File Transaction Safety)

Migrations must be applied in strict forward order (`00001` through `00009`). Each migration file is wrapped in an individual transaction using `--single-transaction` (`psql -1`) together with `-v ON_ERROR_STOP=1`.

### 4.1 Migration Sequence & File Roster

| Step | Migration File | Target Scope | Description |
| :---: | :--- | :--- | :--- |
| **01** | `migrations/00001_create_profiles.sql` | `public.profiles` | Profile table, `updated_at` handler, and `auth.users` trigger |
| **02** | `migrations/00002_create_events.sql` | `public.events` | Core event entity with domain CHECKs and owner FK |
| **03** | `migrations/00003_create_event_budgets.sql` | `public.event_budgets` | 8-category budget allocations and sum invariant |
| **04** | `migrations/00004_create_event_milestone_statuses.sql` | `public.event_milestone_statuses` | Milestone completion checkmarks (composite PK) |
| **05** | `migrations/00005_create_event_vendor_checklist_items.sql` | `public.event_vendor_checklist_items` | Vendor tasks, categories, and booking progress |
| **06** | `migrations/00006_create_crisis_recovery_records.sql` | `public.crisis_recovery_records` | Incident recovery plan logs (JSONB) and action counts |
| **07** | `migrations/00007_create_crisis_recovery_actions.sql` | `public.crisis_recovery_actions` | Granular action tasks and priority tracking |
| **08** | `migrations/00008_enable_row_level_security.sql` | All 7 tables | Enable RLS and establish 27 tenant isolation policies |
| **09** | `migrations/00009_grant_authenticated_role_permissions.sql` | `public` schema | Grant table and sequence permissions to `authenticated` |

---

### 4.2 Step-by-Step Execution Protocol

#### Phase 1: Apply Migration 00001 (Profile Creation & Trigger)
```bash
echo "Applying migrations/00001_create_profiles.sql..."
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f "migrations/00001_create_profiles.sql"
```

#### Phase 2: Mandatory Intermediate Trigger Gate (Post-00001 Verification)
Immediately run the catalog verification query before applying migration 00002:

```bash
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 -c "
-- 1. Verify handle_new_user() security-definer settings
SELECT 
    n.nspname AS function_schema,
    p.proname AS function_name,
    p.prosecdef AS is_security_definer,
    p.proconfig AS configuration_settings
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'public' AND p.proname = 'handle_new_user';

-- 2. Verify on_auth_user_created trigger on auth.users
SELECT 
    n.nspname AS table_schema,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled AS trigger_status,
    p.proname AS trigger_procedure
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
JOIN pg_proc p ON t.tgfoid = p.oid
WHERE n.nspname = 'auth'
  AND c.relname = 'users'
  AND t.tgname = 'on_auth_user_created';
"
```

*Expected Verification Results:*
1. `function_schema`: `public`, `function_name`: `handle_new_user`, `is_security_definer`: `t`, `configuration_settings`: `{search_path=public}`.
2. `table_schema`: `auth`, `table_name`: `users`, `trigger_name`: `on_auth_user_created`, `trigger_status`: `O` (Enabled), `trigger_procedure`: `handle_new_user`.

> [!CAUTION]
> **STOP CONDITION (Trigger Failure)**:
> If `on_auth_user_created` is missing or `tgenabled != 'O'`, **DO NOT PROCEED**.
> - The executing database role lacks required permissions on `auth.users`.
> - Contact your Supabase organization administrator to grant `TRIGGER` on `auth.users` to `postgres`, or execute the trigger block in the Supabase Dashboard SQL Editor as `supabase_admin`.
> - Halt further migrations until this check passes.

---

#### Phase 3: Apply Migrations 00002 Through 00009
```bash
for file in $(ls migrations/0000[2-9]*.sql | sort); do
    echo "Applying $file with transaction safety..."
    psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f "$file"
    if [ $? -ne 0 ]; then
        echo "ERROR: Migration $file failed! Halting loop immediately."
        exit 1
    fi
done
```

---

### 4.3 Stop Conditions & Partial-Failure Recovery Protocol

If any migration file fails mid-run:
1. **HALT IMMEDIATELY**: Do not re-run all scripts blindly.
2. **DO NOT RUN DOWN SCRIPTS**: Rollback scripts in `migrations/down/` contain destructive `DROP TABLE ... CASCADE` statements.
3. **Inspect Completed Migrations**:
   ```sql
   SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
   ```
4. **Identify the Clean Boundary**:
   Because each file ran under `--single-transaction`, the failed file rolled back cleanly. The database state matches the end of the last successful file.
5. **Diagnose and Fix**: Review the terminal error message (e.g. syntax, lock timeout, constraint violation). Correct the root cause.
6. **Resume Forward Migration**: Re-run the migration loop starting strictly at the failing file through `00009`.

---

## 5. Comprehensive Post-Migration Catalog & Security Verification

Execute the following verification queries to confirm database health:

### 5.1 Verify Table Roster (Expected: 7 tables)
```bash
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 -c "
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'profiles', 'events', 'event_budgets', 'event_milestone_statuses',
    'event_vendor_checklist_items', 'crisis_recovery_records', 'crisis_recovery_actions'
  )
ORDER BY tablename;
"
```
*Expected Result:* Exactly 7 tables returned, each with `rowsecurity = true`.

### 5.2 Verify Policy Count (Expected: 27 policies)
```bash
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 -c "
SELECT tablename, count(*) AS policy_count
FROM pg_policies
WHERE schemaname = 'public'
GROUP BY tablename
ORDER BY tablename;
"
```
*Expected Counts:*
- `crisis_recovery_actions`: 4
- `crisis_recovery_records`: 4
- `event_budgets`: 4
- `event_milestone_statuses`: 4
- `event_vendor_checklist_items`: 4
- `events`: 4
- `profiles`: 3
- **Total:** 27 policies.

### 5.3 Verify Role Grant Boundaries
```bash
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 -c "
SELECT 
    table_name,
    has_table_privilege('anon', 'public.' || table_name, 'SELECT') AS anon_select,
    has_table_privilege('anon', 'public.' || table_name, 'INSERT') AS anon_insert,
    has_table_privilege('authenticated', 'public.' || table_name, 'SELECT') AS auth_select,
    has_table_privilege('authenticated', 'public.' || table_name, 'INSERT') AS auth_insert
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
"
```
*Expected Result:*
- `anon_select` and `anon_insert`: `f` (False) for all tables.
- `auth_select` and `auth_insert`: `t` (True) for all tables.

---

## 6. End-to-End Functional Verification (Disposable Staging Account)

> [!NOTE]
> Catalog inspection proves that tables, triggers, and policies are defined. It does **not** prove that Supabase GoTrue event emission, network routing, and application tenant isolation operate end-to-end.
> The operator must execute this functional test using disposable test accounts.

### 6.1 Verified API Route Inventory

| Capability | Path | Method | Auth Requirement | Backend Handler |
| :--- | :--- | :--- | :--- | :--- |
| **System Health** | `/health` | `GET` | Public (Unauthenticated) | `app/main.py:545` |
| **Dataset Status** | `/api/v1/data-status` | `GET` | Public (Unauthenticated) | `app/main.py:559` |
| **Auth Config** | `/api/v1/auth/config` | `GET` | Public (Client Safe) | `app/main.py:583` |
| **Guest Token** | `/api/v1/auth/guest-session` | `POST` / `GET` | Blocked (401) under Postgres | `app/main.py:610` |
| **List Events** | `/api/v1/events` | `GET` | `Bearer <access_token>` | `app/main.py:832` |
| **Create Event** | `/api/v1/events` | `POST` | `Bearer <access_token>` | `app/main.py:724` |
| **Get Event** | `/api/v1/events/{event_id}` | `GET` | `Bearer <access_token>` (Owner) | `app/main.py:749` |
| **Update Event** | `/api/v1/events/{event_id}` | `PATCH` | `Bearer <access_token>` (Owner) | `app/main.py:773` |
| **Delete Event** | `/api/v1/events/{event_id}` | `DELETE` | `Bearer <access_token>` (Owner) | `app/main.py:808` |
| **Event Readiness** | `/api/v1/events/{event_id}/readiness` | `GET` | `Bearer <access_token>` (Owner) | `app/main.py:1392` |

*Supabase Auth Note:* User registration (`POST /auth/v1/signup`) and session signin (`POST /auth/v1/token?grant_type=password`) are managed externally by Supabase Auth (GoTrue), not by FastAPI application routes.

---

### 6.2 Step-by-Step Functional Walkthrough

Set up testing variables:
```bash
API_BASE_URL="https://<staging-app-host>" # or http://localhost:8000 for local connected preflight
TEST_USER_A_EMAIL="test-preflight-a-$(date +%s)@staging.planproof.ai"
TEST_USER_B_EMAIL="test-preflight-b-$(date +%s)@staging.planproof.ai"
TEST_PASSWORD="StagingPreflightPassword123!"
```

#### Step 1: Health Check (Public Route)
```bash
curl -s -f "${API_BASE_URL}/health" | grep '"status":"ok"'
```

#### Step 2: Register Tenant A via Supabase GoTrue
```bash
SIGNUP_RESPONSE=$(curl -s -X POST "${STAGING_SUPABASE_URL}/auth/v1/signup" \
    -H "apikey: ${STAGING_SUPABASE_ANON_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_USER_A_EMAIL}\",\"password\":\"${TEST_PASSWORD}\",\"data\":{\"full_name\":\"Test Operator A\"}}")

USER_A_ID=$(echo "$SIGNUP_RESPONSE" | jq -r '.user.id')
USER_A_TOKEN=$(echo "$SIGNUP_RESPONSE" | jq -r '.access_token')

echo "Tenant A created with ID: ${USER_A_ID}"
```

#### Step 3: Verify Profile Provisioning Trigger Fired
Query the database to confirm `handle_new_user()` auto-provisioned the profile row:
```bash
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 -c "
SELECT id, email, full_name, created_at
FROM public.profiles
WHERE id = '${USER_A_ID}';
"
```
*Expected Result:* Exactly 1 row returned with `email = TEST_USER_A_EMAIL` and `full_name = 'Test Operator A'`.
*Stop Condition:* If 0 rows returned, the trigger failed. Abort preflight!

#### Step 4: Create Event Under Tenant A (Authenticated Route)
```bash
CREATE_EVENT_PAYLOAD='{
  "event_type": "wedding",
  "event_name": "Staging Preflight Wedding",
  "city": "Mumbai",
  "city_tier": "metro",
  "event_date": "2026-12-15",
  "guest_count": 250,
  "total_budget_inr": 2500000,
  "language": "en"
}'

EVENT_RESPONSE=$(curl -s -X POST "${API_BASE_URL}/api/v1/events" \
    -H "Authorization: Bearer ${USER_A_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$CREATE_EVENT_PAYLOAD")

EVENT_ID=$(echo "$EVENT_RESPONSE" | jq -r '.event_id')
echo "Created Event ID: ${EVENT_ID}"
```

#### Step 5: Verify Event Retrieval and Readiness
```bash
# Retrieve Event
curl -s -f -H "Authorization: Bearer ${USER_A_TOKEN}" "${API_BASE_URL}/api/v1/events/${EVENT_ID}" | grep '"event_id":'

# Assess Readiness
curl -s -f -H "Authorization: Bearer ${USER_A_TOKEN}" "${API_BASE_URL}/api/v1/events/${EVENT_ID}/readiness" | grep '"overall_score":'
```

#### Step 6: Verify Tenant Isolation (Tenant B Cannot Access Tenant A's Event)
Register Tenant B and attempt cross-tenant access:
```bash
# Register Tenant B
SIGNUP_B=$(curl -s -X POST "${STAGING_SUPABASE_URL}/auth/v1/signup" \
    -H "apikey: ${STAGING_SUPABASE_ANON_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_USER_B_EMAIL}\",\"password\":\"${TEST_PASSWORD}\"}")

USER_B_TOKEN=$(echo "$SIGNUP_B" | jq -r '.access_token')

# Attempt to GET Tenant A's event using Tenant B's JWT (Expect 404 Not Found)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${USER_B_TOKEN}" \
    "${API_BASE_URL}/api/v1/events/${EVENT_ID}")

if [ "$HTTP_CODE" -eq 404 ]; then
    echo "Tenant isolation verified: Tenant B received 404 for Tenant A's event."
else
    echo "CRITICAL SECURITY FAILURE: Tenant B received HTTP ${HTTP_CODE} when accessing Tenant A's event!"
    exit 1
fi
```

---

## 7. Staging Teardown & Test Data Cleanup (Non-Destructive)

After verification, clean up only the disposable test accounts. Do **not** run down migrations.

```bash
# Delete test users from auth.users (cascades automatically to public.profiles, events, and child rows)
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 -c "
DELETE FROM auth.users 
WHERE email IN ('${TEST_USER_A_EMAIL}', '${TEST_USER_B_EMAIL}');
"

echo "Staging preflight test data cleaned up cleanly via cascade."
```

---

## 8. Summary of Stop Conditions & Escalation Roster

| Checkpoint | Failure Indicator | Required Action |
| :--- | :--- | :--- |
| **Target Check** | `MIGRATION_DATABASE_URL` contains port 6543 or non-staging ref | **ABORT**. Do not connect. |
| **Session Role** | `current_user` is not privileged role | **ABORT**. Re-authenticate as `postgres`. |
| **Backup** | `pg_dump` exits with non-zero status | **ABORT**. Do not run migrations without a backup. |
| **Migration 00001** | `psql` fails with trigger error on `auth.users` | **HALT**. Role lacks permissions on `auth` schema. Grant `TRIGGER` or apply via Supabase Dashboard. |
| **Trigger Gate** | `on_auth_user_created` missing or disabled | **HALT**. Do not proceed to `00002`. Investigate trigger setup. |
| **Migrations 00002–00009** | Any file throws error | **HALT**. File rolled back automatically. Diagnose and resume forward. |
| **Functional Signup** | Profile row not created in `public.profiles` | **HALT**. Supabase GoTrue trigger hook is not firing. |
| **Tenant Isolation** | Tenant B receives `200` accessing Tenant A's event | **CRITICAL SECURITY ALERT**. RLS policy is non-functional. Disable traffic. |

