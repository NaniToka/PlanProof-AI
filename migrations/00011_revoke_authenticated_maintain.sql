-- ==============================================================================
-- PlanProof AI - Migration 00011: Revoke Unintended MAINTAIN Privilege
-- ==============================================================================
-- Description:
-- Removes the MAINTAIN privilege from the 'authenticated' role on all seven
-- PlanProof AI application tables and updates schema-specific default privileges
-- for future tables created by 'postgres' in schema 'public'.
--
-- Background:
-- PostgreSQL 16+ introduced the 'MAINTAIN' privilege (permitting VACUUM, ANALYZE,
-- REINDEX, REFRESH MATERIALIZED VIEW, CLUSTER, and LOCK TABLE).
-- In Supabase default ACLs, MAINTAIN was included under 'ALL TABLES'. While Migration
-- 00010 stripped TRUNCATE, REFERENCES, and TRIGGER, 'authenticated' retained MAINTAIN.
--
-- Security Objectives:
-- 1. Revoke MAINTAIN from 'authenticated' on the seven application tables, ensuring
--    runtime application callers possess strictly CRUD privileges (SELECT, INSERT,
--    UPDATE, DELETE).
-- 2. Update default privileges (pg_default_acl) for role 'postgres' in schema 'public'
--    so future tables do not automatically grant MAINTAIN to 'authenticated'.
-- 3. Preserve administrative privileges for 'service_role' and 'postgres'.
-- 4. Preserve all existing RLS policies and table ownership.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Existing Application Tables: Revoke MAINTAIN from 'authenticated'
-- ------------------------------------------------------------------------------
REVOKE MAINTAIN ON TABLE
    public.profiles,
    public.events,
    public.event_budgets,
    public.event_milestone_statuses,
    public.event_vendor_checklist_items,
    public.crisis_recovery_records,
    public.crisis_recovery_actions
FROM authenticated;

-- ------------------------------------------------------------------------------
-- 2. Future Tables: Revoke MAINTAIN from Default Privileges for Role 'postgres'
-- ------------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE MAINTAIN ON TABLES FROM authenticated;

