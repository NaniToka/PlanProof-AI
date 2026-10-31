-- ==============================================================================
-- PlanProof AI - Migration 00010: Harden Least-Privilege Table and Default ACLs
-- ==============================================================================
-- Description:
-- Enforces defense-in-depth least-privilege access control on the seven PlanProof AI
-- application tables and hardens default privileges for future tables created by
-- the migration owner ('postgres') in schema 'public'.
--
-- Security Objectives:
-- 1. Revoke ALL table privileges from 'anon' on all seven application tables.
--    Prevents accidental data leakage if Row Level Security (RLS) is ever disabled.
-- 2. Revoke dangerous discretionary privileges (TRUNCATE, REFERENCES, TRIGGER)
--    from 'authenticated' on all seven application tables, preserving only
--    application CRUD (SELECT, INSERT, UPDATE, DELETE).
-- 3. Harden default privileges (pg_default_acl) for role 'postgres' in schema 'public'
--    so future tables do not automatically grant permissions to 'anon' and grant
--    only CRUD to 'authenticated'.
-- 4. Preserve existing RLS policies and table ownership without disruption.
-- 5. Maintain unrestricted administrative access for 'service_role' and 'postgres'.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Existing Application Tables: Revoke All Privileges from 'anon'
-- ------------------------------------------------------------------------------
REVOKE ALL ON TABLE
    public.profiles,
    public.events,
    public.event_budgets,
    public.event_milestone_statuses,
    public.event_vendor_checklist_items,
    public.crisis_recovery_records,
    public.crisis_recovery_actions
FROM anon;

-- ------------------------------------------------------------------------------
-- 2. Existing Application Tables: Revoke Dangerous Privileges from 'authenticated'
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
-- 3. Future Tables: Harden Default Privileges in Schema 'public' for Role 'postgres'
-- ------------------------------------------------------------------------------
-- Prevent future tables created by 'postgres' from automatically granting access to 'anon'
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon;

-- Ensure future tables created by 'postgres' grant only CRUD to 'authenticated'
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM authenticated;

