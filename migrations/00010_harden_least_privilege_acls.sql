-- ==============================================================================
-- PlanProof AI - Migration 00010: Harden Least-Privilege Table and Default ACLs
-- ==============================================================================
-- Description:
-- Enforces defense-in-depth least-privilege access control on the seven PlanProof AI
-- application tables and hardens default privileges for future tables created by
-- the migration owner ('postgres') in schema 'public'.
--
-- Security Objectives & ACL Enforcement:
-- 1. Preflight Safety Guard: Inspects pg_default_acl for unsafe global default privileges
--    (defaclnamespace = 0). If global table defaults for 'postgres' grant access to
--    'anon', 'authenticated', or 'PUBLIC', halts immediately to prevent silent
--    privilege leakage into schema public without modifying other schemas.
-- 2. Revoke ALL table privileges from 'anon' AND the 'PUBLIC' pseudo-role on all seven
--    application tables. Closes the gap where 'anon' could inherit table privileges
--    via 'PUBLIC' if RLS were ever disabled.
-- 3. Revoke dangerous discretionary privileges (TRUNCATE, REFERENCES, TRIGGER)
--    from 'authenticated' on all seven application tables, preserving only
--    application CRUD (SELECT, INSERT, UPDATE, DELETE).
-- 4. Harden schema-specific default privileges (pg_default_acl) for role 'postgres'
--    in schema 'public' so future tables do not automatically grant permissions to
--    'anon' or 'PUBLIC', and grant strictly CRUD to 'authenticated'.
-- 5. Preserve existing RLS policies and table ownership without disruption.
-- 6. Maintain unrestricted administrative access for 'service_role' and 'postgres'.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Preflight Guard: Verify No Unsafe Global Default Privileges (defaclnamespace = 0)
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    unsafe_global_count INT;
BEGIN
    -- Check for global default table privileges (defaclnamespace = 0) for role postgres
    -- that grant permissions to anon, authenticated, or PUBLIC (grantee = 0).
    SELECT COUNT(*)
    INTO unsafe_global_count
    FROM pg_default_acl d
    CROSS JOIN LATERAL aclexplode(d.defaclacl) a
    LEFT JOIN pg_roles r ON r.oid = a.grantee
    WHERE d.defaclrole = 'postgres'::regrole
      AND d.defaclnamespace = 0
      AND d.defaclobjtype = 'r'
      AND (r.rolname IN ('anon', 'authenticated') OR a.grantee = 0);

    IF unsafe_global_count > 0 THEN
        RAISE EXCEPTION 'SAFETY HALT: Found % unsafe global default table privilege(s) for role postgres (defaclnamespace = 0). Schema-specific revocation cannot guarantee future table isolation without modifying global defaults. Operator manual authorization required.', unsafe_global_count;
    END IF;
END $$;

-- ------------------------------------------------------------------------------
-- 2. Existing Application Tables: Revoke All Privileges from 'anon' and 'PUBLIC'
-- ------------------------------------------------------------------------------
REVOKE ALL ON TABLE
    public.profiles,
    public.events,
    public.event_budgets,
    public.event_milestone_statuses,
    public.event_vendor_checklist_items,
    public.crisis_recovery_records,
    public.crisis_recovery_actions
FROM anon, PUBLIC;

-- ------------------------------------------------------------------------------
-- 3. Existing Application Tables: Revoke Dangerous Privileges from 'authenticated'
--    Preserves SELECT, INSERT, UPDATE, DELETE while removing TRUNCATE, REFERENCES, TRIGGER.
-- ------------------------------------------------------------------------------
REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE
    public.profiles,
    public.events,
    public.event_budgets,
    public.event_milestone_statuses,
    public.event_vendor_checklist_items,
    public.crisis_recovery_records,
    public.crisis_recovery_actions
FROM authenticated;

-- ------------------------------------------------------------------------------
-- 4. Future Tables: Harden Default Privileges in Schema 'public' for Role 'postgres'
-- ------------------------------------------------------------------------------
-- Prevent future tables created by 'postgres' from automatically granting access to 'anon' or 'PUBLIC'
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon, PUBLIC;

-- Ensure future tables created by 'postgres' grant only CRUD to 'authenticated'
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM authenticated;
