# PlanProof AI — Staging Preflight & Migration Runbook

> [!CRITICAL]
> **GOVERNANCE & SAFETY GATE**:
> This runbook is strictly for **staging environment preflight, configuration, and verification**.
> - **Zero Automatic Execution**: No automated script, CI/CD pipeline, or AI agent is authorized to execute this runbook autonomously.
> - **Human Authorization Required**: Execution requires explicit, written approval from the designated release engineer or technical lead.
> - **Never Execute Against Production**: Verify target project credentials before issuing any command.
> - **Never Run Rollback Scripts on Shared Databases**: Down migration scripts in `migrations/down/` contain destructive `DROP TABLE ... CASCADE` statements. They are strictly prohibited on staging and production databases.
> - **Local Safety Boundary**: This task is local documentation only. No remote database connection, SQL execution, backup, account creation, or data deletion is performed during local development.

---

## Document Roadmap & Execution Phases

This runbook is divided into three sequential phases for operators and beginners:

1. **[Phase A — Manual Dashboard Setup](#phase-a--manual-dashboard-setup)**: Numbered step-by-step instructions to create and inspect a dedicated Supabase staging project in the web browser.
2. **[Phase B — Local Configuration](#phase-b--local-configuration)**: How to configure local environment variables (`.env`) safely using dashboard-retrieved values and verify secret protection.
3. **[Phase C — Preflight Checks & Staging Verification](#phase-c--preflight-checks--staging-verification)**: Preflight gates distinguishing offline automated tests from live database verification, sequential migration execution, and disposable account testing.

---

## Phase A — Manual Dashboard Setup

Follow these numbered steps in your web browser to create and inspect your staging project. **Do not attempt to create or configure the project via automated scripts.**

### Step A.1: Create a Dedicated Supabase Staging Project
1. Open [https://supabase.com/dashboard](https://supabase.com/dashboard) and log in to your account.
2. Select your Organization, then click **New Project**.
3. Fill in the project details:
   - **Name**: Enter a clear staging identifier, e.g., `planproof-staging`. (Never reuse a production or local project).
   - **Database Password**: Click **Generate a password** (or type a strong, unique 24+ character password). Copy this password immediately and store it securely in your password manager.
     > [!WARNING]
     > Supabase does **not** display this password again after creation. If lost, you will need to reset it in project settings.
   - **Region**: Choose the geographical region closest to your application hosting environment (e.g., `ap-south-1` Mumbai or `us-east-1` N. Virginia) to minimize network latency.
   - **Pricing Plan**: Select Free or Pro tier as appropriate for staging.
4. Click **Create new project** and wait 1–2 minutes while Supabase provisions the PostgreSQL instance, GoTrue auth service, and storage.

---

### Step A.2: Record Project Reference and Hostnames
Once the project dashboard loads:
1. In the browser URL bar, observe your project URL:
   `https://supabase.com/dashboard/project/<staging-project-ref>`
2. Record your `<staging-project-ref>` (a 20-character alphanumeric string, e.g. `abcdefghijklmnopqrst`). This reference uniquely identifies your staging project.
3. Note your public API domain: `https://<staging-project-ref>.supabase.co`.

---

### Step A.3: Obtain Connection Strings (Port 5432 vs Port 6543)
Never invent database hostnames or connection parameters. Always obtain the official connection strings directly from your dashboard:

1. In the left sidebar, click the **Project Settings** icon (gear icon at the bottom left), then select **Database**.
2. Scroll to the **Connection parameters** / **Connection string** section (or click the green **Connect** button at the top header).
3. Select the **URI** tab. You will see two distinct connection options:

#### Option 1: Direct / Session Connection (Port 5432) — Required for Migrations
- **Port**: `5432`
- **Dashboard Label**: **Session** (or Direct Connection).
- **URI Format**: `postgresql://postgres.<staging-project-ref>:[YOUR-PASSWORD]@aws-0-[region].pooler.supabase.com:5432/postgres` (or direct IPv6 `db.<staging-project-ref>.supabase.co:5432`).
- **Purpose**: Used **exclusively** for `MIGRATION_DATABASE_URL` (running DDL migrations, `pg_dump`, and catalog maintenance).
- **Why Port 5432 is Mandatory for DDL**: Schema migrations execute statements like `CREATE TABLE`, `ALTER TABLE`, table-level locks, and multi-statement transactional scripts. Transaction poolers do not support DDL commands or persistent transaction states.

#### Option 2: Transaction Pooler Connection (Port 6543) — Required for Application Runtime
- **Port**: `6543`
- **Dashboard Label**: **Transaction** (Supavisor / PgBouncer pooler).
- **URI Format**: `postgresql://postgres.<staging-project-ref>:[YOUR-PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres`
- **Purpose**: Used for `DATABASE_URL` (FastAPI application runtime queries).
- **Why Port 6543 is Used for Runtime**: The transaction pooler multiplexes short queries across a manageable number of backend PostgreSQL connections, protecting the database from connection exhaustion when handling web requests.
- **Statement Cache Requirement**: In PlanProof AI, `database_statement_cache_size=0` is automatically configured so that asyncpg does not issue named prepared statements that fail in transaction pooling mode.

---

### Step A.4: Inspect Auth & JWT Signing Configuration (Confirmed: ES256)
Do not guess or assume which signing algorithm your Supabase project uses. Supabase projects vary by creation date and tier:

1. In the left sidebar, navigate to **Project Settings** $\rightarrow$ **API**.
2. Copy the **Project URL**: `https://<staging-project-ref>.supabase.co` (Confirmed staging URL: `https://gtolvlwdipiqlqasatnf.supabase.co`).
3. Under **Project API keys**, locate the public client key:
   - In newer Supabase projects, this key is labeled **Publishable key** and begins with `sb_publishable_`.
   - In older Supabase projects, this key is labeled **`anon` `public`** key and is a JWT beginning with `eyJhbGci...`.
   - Both formats are client-safe and fully supported by PlanProof AI and `@supabase/supabase-js`.
   - **CRITICAL SECURITY RULE**: Never copy or configure the **Secret key** (`sb_secret_...`) or **`service_role`** key into `SUPABASE_ANON_KEY`. Secret keys grant administrative backend privileges and must never be exposed to browser clients. PlanProof AI strictly validates and rejects any secret or service-role keys in `SUPABASE_ANON_KEY`.
4. Locate the **JWT Settings** section (or **Authentication** $\rightarrow$ **JWT Settings** / **Signing Keys** in newer dashboards):
   - **Inspect the Signing Method**:
     - The confirmed staging project uses an **ECC (P-256)** key, which corresponds to **`ES256`** asymmetric signing.
     - Tokens are verified against public keys retrieved dynamically from the JWKS endpoint (`https://gtolvlwdipiqlqasatnf.supabase.co/auth/v1/.well-known/jwks.json`).
   - **Handling Previous / Legacy HS256 Signing Keys**:
     - The Supabase dashboard may list a "Previous signing key" (symmetric HS256).
     - **Old Token Rejection**: When `SUPABASE_JWT_ALGORITHMS` is pinned to `ES256`, any legacy token signed with HS256 will be rejected immediately with `INVALID_ALGORITHM` (HTTP 401).
     - **No Legacy Support Needed**: For this fresh staging integration, database migrations have not been applied and no pre-existing active user sessions exist. GoTrue issues all new tokens using the active ECC key. Adding HS256 back into the allowlist would require storing `SUPABASE_JWT_SECRET` and needlessly weaken the algorithm allowlist.
   - **When `SUPABASE_JWT_SECRET` is Required vs Omitted**:
     - `SUPABASE_JWT_SECRET` is required **only** for symmetric `HS256`.
     - For `ES256`, verification uses public keys via the JWKS endpoint or `SUPABASE_JWT_PUBLIC_KEY`. `SUPABASE_JWT_SECRET` is **not** required and should be left unset/empty.
   - **Pinning the Algorithm**:
     - Pin `SUPABASE_JWT_ALGORITHMS=ES256`. This restricts token verification strictly to the active ECC algorithm and unconditionally blocks unsigned tokens, algorithm confusion attacks, or unexpected algorithm families.

---

### Step A.5: Understand Database Roles and RLS Permissions
In Supabase:
1. The migration connection logs in as the administrative role (`postgres`).
2. PlanProof AI application queries run under transaction-local RLS claims:
   ```sql
   SELECT set_config('role', 'authenticated', true);
   SELECT set_config('request.jwt.claim.sub', '<user-uuid>', true);
   ```
3. The connecting database role must have permission to switch roles (`GRANT authenticated TO <app_role>;`). The default `postgres` role has this membership.
4. If role switching fails, the repository fails closed, aborts the transaction, and raises `RepositoryError`.

---

## Phase B — Local Configuration

Now that you have retrieved your project parameters from the dashboard, configure your local development and staging environment files safely.

### Step B.1: Prepare `.env` from Example Template
```bash
# In the PlanProof-AI root directory:
cp .env.example .env
```

### Step B.2: Populate `.env` with Dashboard Values (Secret-Safe Template)
Open `.env` in your editor. Replace the placeholders with the actual values copied from your Supabase dashboard:

```ini
# Application Environment
APP_NAME=PlanProof AI
APP_ENV=staging
STORAGE_BACKEND=postgres

# Supabase Public Parameters (Client-Safe)
# Project reference: gtolvlwdipiqlqasatnf (matches https://<staging-project-ref>.supabase.co)
SUPABASE_URL=https://gtolvlwdipiqlqasatnf.supabase.co
# Public client API key (either new publishable key 'sb_publishable_...' or legacy anon JWT):
SUPABASE_ANON_KEY=<staging-anon-key>

# Supabase Auth Verification Configuration (ES256 Asymmetric via JWKS)
SUPABASE_JWT_AUDIENCE=authenticated
# Pinned strictly to the active confirmed ECC algorithm:
SUPABASE_JWT_ALGORITHMS=ES256
# Note: SUPABASE_JWT_SECRET is NOT needed for ES256 and should be left empty:
SUPABASE_JWT_SECRET=

# Database Connections (Obtained from Dashboard in Step A.3)
# Runtime Application Pooler (Port 6543):
DATABASE_URL=postgresql://postgres.gtolvlwdipiqlqasatnf:<staging-db-password>@aws-0-<staging-region>.pooler.supabase.com:6543/postgres?sslmode=require

# Direct Session Connection for Migrations (Port 5432 - NEVER use 6543 for DDL):
MIGRATION_DATABASE_URL=postgresql://postgres.gtolvlwdipiqlqasatnf:<staging-db-password>@aws-0-<staging-region>.pooler.supabase.com:5432/postgres?sslmode=require
```

> [!CAUTION]
> **Secret Handling Rules**:
> - Never request, print, or commit passwords, secrets, or `.env` files.
> - Never print connection strings containing passwords to terminal logs.
> - `DATABASE_URL` and `MIGRATION_DATABASE_URL` contain passwords and must **never** be shared or committed.
> - `SUPABASE_ANON_KEY` must contain only the public publishable key (`sb_publishable_...`) or anon key (`eyJ...`). Never put secret keys (`sb_secret_...`) or `service_role` keys in `SUPABASE_ANON_KEY`.
> - Staging placeholders like `<staging-project-ref>` and `<staging-db-password>` must be replaced in `.env` with real credentials but never committed to version control.

### Step B.3: Restrict File Permissions and Verify Git Ignore
1. Set restrictive file permissions so only your user account can read `.env`:
   ```bash
   chmod 600 .env
   ```
2. Verify that `.env` is covered by `.gitignore`:
   ```bash
   git check-ignore -v .env
   ```
   *Expected Output:* `.gitignore:3:.env` (or similar confirming git ignores the file).
3. Confirm Git working tree status:
   ```bash
   git status
   ```
   *Expected Output:* `.env` does **not** appear in untracked files.

---

## Phase C — Preflight Checks & Staging Verification

Phase C specifies all verification gates. **Do not apply any migrations until the preflight checks pass.**

---

### Section C.1: Offline Preflight Verification (Local Machine)
These tests run completely offline and verify application logic, configuration parsing, and schema integrity without touching any remote database:

```bash
# 1. Run migration and runbook documentation integrity tests:
.venv/bin/pytest tests/test_migrations.py -v

# 2. Run configuration and secret protection tests:
.venv/bin/pytest tests/test_config.py -v

# 3. Run cryptographic JWT authentication tests:
.venv/bin/pytest tests/test_auth.py -v

# 4. Run the full offline regression suite:
.venv/bin/pytest
```
*Expected Result:* All tests pass (with only real network/database tests appropriately skipped). If any offline test fails, halt and fix the local code first.

---

### Section C.2: Target Environment Identity & Secret-Safe Verification (Live Staging)
Once authorized by the release lead to proceed with staging verification:

#### 1. Set Staging Shell Variables
```bash
# Set staging environment variables (replace placeholders with actual staging credentials)
export STAGING_PROJECT_REF="<staging-project-ref>"
export MIGRATION_DATABASE_URL="postgresql://postgres.<staging-project-ref>:<staging-db-password>@aws-0-<staging-region>.pooler.supabase.com:5432/postgres"

# Application runtime URL (for smoke testing)
export STAGING_SUPABASE_URL="https://<staging-project-ref>.supabase.co"
export STAGING_SUPABASE_ANON_KEY="<staging-anon-key>"
```

#### 2. Secret-Safe Identity Assertion
Verify that the target connection URL references the staging project without printing credentials to the console:

```bash
# 1. Require explicit, non-empty staging project reference (cannot be blank or unreplaced placeholder)
if [ -z "${STAGING_PROJECT_REF:-}" ] || [ "${STAGING_PROJECT_REF}" = "<staging-project-ref>" ]; then
    echo "ERROR: STAGING_PROJECT_REF must be explicitly set to a valid non-empty staging project reference (cannot be empty or default placeholder). Aborting!"
    exit 1
fi

# 2. Require explicit, non-empty database URL
if [ -z "${MIGRATION_DATABASE_URL:-}" ] || [ "${MIGRATION_DATABASE_URL}" = "postgresql://postgres.<staging-project-ref>:<staging-db-password>@aws-0-<staging-region>.pooler.supabase.com:5432/postgres" ]; then
    echo "ERROR: MIGRATION_DATABASE_URL must be explicitly set to a valid non-empty connection string. Aborting!"
    exit 1
fi

# 3. Assert connection string targets the intended staging project ref without leaking password
if [[ "$MIGRATION_DATABASE_URL" != *"$STAGING_PROJECT_REF"* ]]; then
    echo "ERROR: MIGRATION_DATABASE_URL does not target the expected STAGING_PROJECT_REF ($STAGING_PROJECT_REF). Aborting!"
    exit 1
fi

# 4. Assert port 5432 is specified for DDL migrations (port 6543 pooler forbidden for DDL)
if [[ "$MIGRATION_DATABASE_URL" == *":6543/"* ]]; then
    echo "ERROR: MIGRATION_DATABASE_URL specifies port 6543 (transaction pooler). DDL requires session port 5432. Aborting!"
    exit 1
fi

echo "Preflight check PASSED: Target matches staging ref [${STAGING_PROJECT_REF}] on session port 5432."
```

#### 3. Verify Database Identity via Non-Destructive SQL
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
- **Stop Condition:** If the connection fails, if `current_database()` does not match expectations, or if `session_role` is unprivileged (e.g. `anon` or `planproof_app`), **STOP immediately**.

---

### Section C.3: Pre-Migration Staging Backup & Recovery Protocol

Staging databases frequently hold testing datasets, staging test profiles, or seed configurations. Prior to applying migrations, the operator must execute and rigorously validate a logical backup.

> [!WARNING]
> **Scope & Limitations of Logical Backup**:
> The command below captures a logical dump of the `public` schema (`--schema=public`).
> - **What is captured:** Application tables, views, sequences, types, and data in `public`.
> - **What is NOT captured:** Managed Supabase Auth data (`auth.users`, identities, refresh tokens, MFA factors), Storage metadata (`storage.buckets`, `storage.objects`), Vault secrets, Edge functions, database extensions, or project configuration settings. It is **not** a complete Supabase platform backup.
> - **Archive Listing != Restore Proof:** Running `pg_restore --list` is a basic archive integrity check verifying that the custom-format header and Table of Contents (TOC) are readable. It does **not** prove that restoring the objects into the database will succeed (it does not execute SQL DDL/DML, test target schema conflicts, or verify foreign-key / trigger constraints during restore).
> - **Recovery Assumption Warning:** A dump must never be assumed recoverable solely because the command exited without error. A valid restore plan must be approved before proceeding.

#### 1. Execute Logical Backup
```bash
# Generate timestamped backup file with restrictive permissions
BACKUP_FILE="staging_backup_public_pre_migration_$(date +%Y%m%d_%H%M%S).dump"
umask 077

echo "Creating logical backup in ${BACKUP_FILE}..."
pg_dump "$MIGRATION_DATABASE_URL" \
    --schema=public \
    --format=custom \
    --file="$BACKUP_FILE"

DUMP_STATUS=$?
if [ $DUMP_STATUS -ne 0 ]; then
    echo "ERROR: pg_dump failed with exit code ${DUMP_STATUS}! Aborting migration."
    exit 1
fi

# Ensure restrictive file permissions
chmod 600 "$BACKUP_FILE"
```

#### 2. Validate Backup Existence, Non-Empty Size, and Dump Integrity
```bash
# 1. Assert single target backup file is explicitly identified without unquoted wildcards
if [ -z "${BACKUP_FILE:-}" ]; then
    echo "ERROR: BACKUP_FILE is unset or empty! Set BACKUP_FILE to the intended single backup file path."
    exit 1
fi

# Disallow glob characters in BACKUP_FILE to prevent ambiguous multi-file checks
if [[ "$BACKUP_FILE" == *"*"* ]] || [[ "$BACKUP_FILE" == *"?"* ]]; then
    echo "ERROR: BACKUP_FILE must be an explicit filename without wildcards (* or ?). Aborting!"
    exit 1
fi

# 2. Assert backup file exists as a regular file and is non-empty
if [ ! -f "$BACKUP_FILE" ] || [ ! -s "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file ${BACKUP_FILE} does not exist or has zero bytes! Aborting migration."
    exit 1
fi

# 3. Validate dump archive table of contents via pg_restore
# NOTE: This validates that the custom archive header and TOC are readable.
# It is a basic integrity check and does NOT prove that a database restore will succeed.
pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1
RESTORE_CHECK_STATUS=$?
if [ $RESTORE_CHECK_STATUS -ne 0 ]; then
    echo "ERROR: pg_restore --list validation failed (exit code ${RESTORE_CHECK_STATUS})! Dump file is invalid or corrupt. Aborting migration."
    exit 1
fi

echo "Backup validated: ${BACKUP_FILE} exists, is non-empty ($(du -h "$BACKUP_FILE" | cut -f1)), and archive header is readable."
```

#### 3. Recovery Decision Rules
- If any migration fails, **do NOT execute down scripts** (`migrations/down/`).
- Down migrations contain destructive `DROP TABLE ... CASCADE` statements and will wipe out existing staging data.
- Prefer **fixing forward** (diagnosing the root cause and resuming from the failed migration boundary).
- If the public schema becomes corrupted or inconsistent, restore using `pg_restore`:
  ```bash
  # RESTORE WORKFLOW (Requires human review and confirmation)
  # pg_restore --clean --if-exists --schema=public -d "$MIGRATION_DATABASE_URL" "$BACKUP_FILE"
  ```

---

### Section C.4: Sequential Migration Execution (Per-File Transaction Safety)

Migrations must be applied in strict forward order (`00001` through `00009`). Each migration file is wrapped in an individual transaction using `--single-transaction` (`psql -1`) together with `-v ON_ERROR_STOP=1`.

#### Migration Sequence & File Roster

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
| **09** | `migrations/00009_grant_authenticated_role_permissions.sql` | `public` schema | Grant least-privilege permissions on the seven application tables to `authenticated` |

---

#### Step 1: Apply Migration 00001 (Profile Creation & Trigger)
```bash
echo "Applying migrations/00001_create_profiles.sql..."
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f "migrations/00001_create_profiles.sql"

if [ $? -ne 0 ]; then
    echo "ERROR: Migration 00001 failed! Halting immediately."
    exit 1
fi
```

#### Step 2: Mandatory Intermediate Trigger Gate (Post-00001 Verification)
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
> **TRIGGER PRIVILEGE BOUNDARY & STOP CONDITION**:
> - **Catalog Visibility != Functional Proof**: Visibility of the trigger in `pg_trigger` confirms registration in PostgreSQL catalogs. It does **not** prove that GoTrue has execution permissions, that the payload mapping works, or that profile provisioning succeeds during live signup.
> - **Supabase-Managed Object Boundary**: In Supabase, `auth.users` is owned and managed by GoTrue / `supabase_auth_admin`. Standard migration roles (such as `postgres` or application roles) cannot grant privileges on or modify Supabase-managed authentication internals.
> - **Stop Condition**: If `00001_create_profiles.sql` fails to create the trigger (raising `insufficient_privilege`) or if the catalog query returns 0 rows or `tgenabled != 'O'`:
>   1. **HALT IMMEDIATELY**. Do not apply migrations `00002` through `00009`.
>   2. **DO NOT attempt to bypass Supabase security boundaries** or alter `auth` schema ownership.
>   3. **Escalate to the Supabase Project Owner**: Have an administrator inspect the trigger setup via the official Supabase Dashboard SQL Editor (running under `supabase_admin`).

---

#### Step 3: Apply Migrations 00002 Through 00009
```bash
for file in migrations/0000[2-9]*.sql; do
    if [ ! -f "$file" ]; then
        echo "ERROR: Migration file $file not found!"
        exit 1
    fi
    echo "Applying $file with transaction safety..."
    psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f "$file"
    if [ $? -ne 0 ]; then
        echo "ERROR: Migration $file failed! Halting loop immediately."
        exit 1
    fi
done
```

---

#### Stop Conditions & Partial-Failure Recovery Protocol
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

### Section C.5: Post-Migration Catalog & Security Verification

Execute the following verification queries to confirm database health:

#### 1. Verify Table Roster (Expected: 7 tables)
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

#### 2. Verify Policy Count (Expected: 27 policies)
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
- **Total: 27 policies.**

#### 3. Verify Role Grant Boundaries
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

### Section C.6: End-to-End Functional Verification (Disposable Staging Accounts)

> [!NOTE]
> Catalog inspection proves that tables, triggers, and policies are defined. It does **not** prove that Supabase GoTrue event emission, network routing, and application tenant isolation operate end-to-end.
> The operator must execute this functional test using explicitly recorded disposable test accounts.

#### Verified API Route Inventory

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

#### Functional Walkthrough Steps

Set up testing variables:
```bash
API_BASE_URL="https://<staging-app-host>" # or http://localhost:8000 for local connected preflight
TEST_USER_A_EMAIL="test-preflight-a-$(date +%s)@staging.planproof.ai"
TEST_USER_B_EMAIL="test-preflight-b-$(date +%s)@staging.planproof.ai"
TEST_PASSWORD="StagingPreflightPassword123!"
```

##### 1. Health Check (Public Route)
```bash
curl -s -f "${API_BASE_URL}/health" | grep '"status":"ok"'
```

##### 2. Register Tenant A via Supabase GoTrue
```bash
SIGNUP_RESPONSE=$(curl -s -X POST "${STAGING_SUPABASE_URL}/auth/v1/signup" \
    -H "apikey: ${STAGING_SUPABASE_ANON_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_USER_A_EMAIL}\",\"password\":\"${TEST_PASSWORD}\",\"data\":{\"full_name\":\"Test Operator A\"}}")

USER_A_ID=$(echo "$SIGNUP_RESPONSE" | jq -r '.user.id')
USER_A_TOKEN=$(echo "$SIGNUP_RESPONSE" | jq -r '.access_token')

echo "RECORDED DISPOSABLE USER A -> UUID: ${USER_A_ID}, EMAIL: ${TEST_USER_A_EMAIL}"
```

##### 3. Verify Profile Provisioning Trigger Fired
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

##### 4. Create Event Under Tenant A (Authenticated Route)
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

##### 5. Verify Event Retrieval and Readiness
```bash
# Retrieve Event
curl -s -f -H "Authorization: Bearer ${USER_A_TOKEN}" "${API_BASE_URL}/api/v1/events/${EVENT_ID}" | grep '"event_id":'

# Assess Readiness
curl -s -f -H "Authorization: Bearer ${USER_A_TOKEN}" "${API_BASE_URL}/api/v1/events/${EVENT_ID}/readiness" | grep '"overall_score":'
```

##### 6. Verify Tenant Isolation (Tenant B Cannot Access Tenant A's Event)
Register Tenant B and attempt cross-tenant access:
```bash
# Register Tenant B
SIGNUP_B=$(curl -s -X POST "${STAGING_SUPABASE_URL}/auth/v1/signup" \
    -H "apikey: ${STAGING_SUPABASE_ANON_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_USER_B_EMAIL}\",\"password\":\"${TEST_PASSWORD}\"}")

USER_B_ID=$(echo "$SIGNUP_B" | jq -r '.user.id')
USER_B_TOKEN=$(echo "$SIGNUP_B" | jq -r '.access_token')

echo "RECORDED DISPOSABLE USER B -> UUID: ${USER_B_ID}, EMAIL: ${TEST_USER_B_EMAIL}"

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

### Section C.7: Safe Staging Teardown & Exact Disposable-Account Cleanup

> [!CAUTION]
> **EXACT DISPOSABLE-ACCOUNT CLEANUP PROTOCOL**:
> - **Supported Auth Interfaces Only**: Use the official Supabase Dashboard or the supported Supabase Auth Admin API. Direct SQL deletion from `auth.users` is prohibited in normal staging cleanup procedures.
> - **Exact Recorded Identities Only**: Deletion must target **only** the exact UUIDs (`USER_A_ID`, `USER_B_ID`) and exact emails (`TEST_USER_A_EMAIL`, `TEST_USER_B_EMAIL`) explicitly recorded in Section C.6.
> - **Never Use Pattern Deletion**: Never run broad deletion queries (e.g. `WHERE email LIKE '%...'` or domain matching). Broad pattern matching risks deleting other staging testers or pre-existing QA accounts.
> - **Human Confirmation Required**: The operator must visually verify the recorded UUIDs and associated emails and obtain operator confirmation before proceeding.
> - **Never Run by Automated Tasks**: Cleanup must never be executed automatically by local agents, background jobs, or CI/CD pipelines.

#### Why Direct SQL Deletion from `auth.users` is Excluded
1. **Managed Service Boundary**: In Supabase, the `auth` schema and `auth.users` table are owned and managed by GoTrue (`supabase_admin`). Direct database manipulation bypasses GoTrue auth lifecycle hooks (such as sessions, identities, refresh tokens, MFA factors, and audit logs), which can leave orphaned internal authentication state.
2. **Role Privilege Accuracy**: The `service_role` is an HTTP API role used with secret API keys for PostgREST and GoTrue administrative endpoints. It is **not** a PostgreSQL superuser and does not authorize direct SQL modifications on `auth.users`.
3. **Cascading Teardown**: When a user is deleted through the supported Auth management interface (Dashboard or Admin API), PostgreSQL enforces foreign-key constraints defined in PlanProof migrations:
   - `public.profiles(id)` directly references `auth.users(id) ON DELETE CASCADE` (Migration `00001`).
   - `public.events(user_id)` directly references `public.profiles(id) ON DELETE CASCADE` (Migration `00002`).
   - All five event child tables reference `public.events(event_id) ON DELETE CASCADE`:
     - `public.event_budgets` (Migration `00003`)
     - `public.event_milestone_statuses` (Migration `00004`)
     - `public.event_vendor_checklist_items` (Migration `00005`)
     - `public.crisis_recovery_records` (Migration `00006`)
     - `public.crisis_recovery_actions` (Migration `00007`, also referencing `crisis_recovery_records ON DELETE CASCADE`)
   Thus, deleting the user via GoTrue cleanly cascades through `profiles` $\rightarrow$ `events` $\rightarrow$ all child records.

---

#### Method 1: Supabase Dashboard (Recommended UI Workflow)
The most transparent and safe operational method:
1. Log in to the official **Supabase Dashboard** for the verified Staging project.
2. Navigate to **Authentication** $\rightarrow$ **Users**.
3. In the search box, search for the exact recorded User UUID (`USER_A_ID`).
4. Visually confirm that the associated email matches `TEST_USER_A_EMAIL`.
5. Click **Delete User** and confirm deletion.
6. Repeat steps 3–5 for `USER_B_ID` and `TEST_USER_B_EMAIL`.
7. Verify that both disposable accounts are removed from the user list.

---

#### Method 2: Supabase Auth Admin API (Supported API Workflow)
If performing teardown programmatically via a release workstation:
1. Verify that `USER_A_ID` and `USER_B_ID` are non-empty and match the exact recorded values.
2. Obtain explicit operator confirmation before issuing the API calls:
   ```bash
   echo "Confirm deletion of verified disposable staging accounts:"
   echo " - User A: ${USER_A_ID} (${TEST_USER_A_EMAIL})"
   echo " - User B: ${USER_B_ID} (${TEST_USER_B_EMAIL})"
   read -p "Proceed with deletion? (y/N): " CONFIRM
   if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
       echo "Cleanup aborted by operator."
       exit 0
   fi
   ```
3. Issue administrative deletion requests using the Supabase Auth Admin endpoint (requires `SUPABASE_SERVICE_ROLE_KEY`):
   ```bash
   # Delete User A
   curl -s -X DELETE "${STAGING_SUPABASE_URL}/auth/v1/admin/users/${USER_A_ID}" \
        -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
        -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}"

   # Delete User B
   curl -s -X DELETE "${STAGING_SUPABASE_URL}/auth/v1/admin/users/${USER_B_ID}" \
        -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
        -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}"
   ```
4. Verify HTTP 200 OK responses, confirming GoTrue has removed the users and triggered relational cascading.

---

## Summary of Stop Conditions & Escalation Roster

| Checkpoint | Failure Indicator | Required Action |
| :--- | :--- | :--- |
| **Target Check** | `MIGRATION_DATABASE_URL` contains port 6543 or non-staging ref | **ABORT**. Do not connect. |
| **Session Role** | `current_user` is not privileged role | **ABORT**. Re-authenticate as `postgres`. |
| **Backup** | `pg_dump` fails, file missing/empty, or `pg_restore --list` fails | **ABORT**. Do not run migrations without a validated backup. |
| **Migration 00001** | `psql` fails with trigger error on `auth.users` | **HALT**. Role lacks permissions on `auth` schema. Do NOT bypass; escalate to Supabase Project Owner. |
| **Trigger Gate** | `on_auth_user_created` missing or disabled in catalog | **HALT**. Do not proceed to `00002`. Investigate trigger setup with Project Owner. |
| **Migrations 00002–00009** | Any file throws error | **HALT**. File rolled back automatically via `--single-transaction`. Diagnose and resume forward. |
| **Functional Signup** | Profile row not created in `public.profiles` | **HALT**. GoTrue trigger hook is not firing despite catalog entry. |
| **Tenant Isolation** | Tenant B receives `200` accessing Tenant A's event | **CRITICAL SECURITY ALERT**. RLS policy is non-functional. Disable traffic. |
| **Cleanup** | Exact user IDs not recorded or mismatch | **HALT**. Do not run broad deletion queries. Clean via Supabase Dashboard. |
