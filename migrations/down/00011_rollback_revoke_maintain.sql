-- ==============================================================================
-- PlanProof AI - Down Migration 00011: Guarded Rollback of MAINTAIN Revocation
-- ==============================================================================
-- Description:
-- Symmetrically rolling back Migration 00011 would re-grant the MAINTAIN privilege
-- (VACUUM, ANALYZE, REINDEX, LOCK TABLE) to the 'authenticated' role.
--
-- Security Policy & Operational Safety:
-- 1. Automatic/unattended execution is strictly forbidden and blocked by a guard.
-- 2. Rolling back this migration requires explicit manual security review and
--    written authorization by the database security owner.
-- 3. If rollback is explicitly authorized for diagnostic or testing purposes in an
--    isolated environment, an operator must execute the commented statements below.
-- ==============================================================================

DO $$
BEGIN
    RAISE EXCEPTION 'SAFETY HALT: Rolling back migration 00011 would re-grant the MAINTAIN privilege to authenticated. Manual security authorization is required.';
END $$;

-- Manual restoration statements (only to be executed after explicit security authorization):
--
-- GRANT MAINTAIN ON TABLE
--     public.profiles,
--     public.events,
--     public.event_budgets,
--     public.event_milestone_statuses,
--     public.event_vendor_checklist_items,
--     public.crisis_recovery_records,
--     public.crisis_recovery_actions
-- TO authenticated;
--
-- ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
--     GRANT MAINTAIN ON TABLES TO authenticated;

