-- ==============================================================================
-- PlanProof AI - Down Migration 00010: Guarded Rollback of ACL Hardening
-- ==============================================================================
-- Description:
-- Symmetrically rolling back Migration 00010 would re-introduce broad table-level
-- privileges (ALL) to the 'anon' role and dangerous privileges (TRUNCATE, REFERENCES,
-- TRIGGER) to the 'authenticated' role, compromising defense-in-depth isolation.
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
    RAISE EXCEPTION 'SAFETY HALT: Rolling back migration 00010 would re-grant broad table access to anon and dangerous privileges to authenticated. Manual security authorization is required.';
END $$;

-- Manual restoration statements (only to be executed after explicit security authorization):
--
-- GRANT ALL ON TABLE
--     public.profiles,
--     public.events,
--     public.event_budgets,
--     public.event_milestone_statuses,
--     public.event_vendor_checklist_items,
--     public.crisis_recovery_records,
--     public.crisis_recovery_actions
-- TO anon;
--
-- GRANT TRUNCATE, REFERENCES, TRIGGER ON TABLE
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
--     GRANT ALL ON TABLES TO anon;
--
-- ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
--     GRANT TRUNCATE, REFERENCES, TRIGGER ON TABLES TO authenticated;
