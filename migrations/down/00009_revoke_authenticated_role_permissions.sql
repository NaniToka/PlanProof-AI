-- ==============================================================================
-- PlanProof AI - Down Migration 00009: Revoke Role Permissions for RLS
-- ==============================================================================
-- Description:
-- Symmetrically revokes table permissions granted to the 'authenticated' role
-- on the seven PlanProof AI application tables.
--
-- Note on Schema USAGE:
-- USAGE on schema public is pre-configured by Supabase for 'anon' and 'authenticated'
-- at project initialization. To preserve pre-existing database configuration and avoid
-- breaking standard Supabase/PostgREST routing, schema USAGE is not revoked here.
-- ==============================================================================

REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.profiles,
    public.events,
    public.event_budgets,
    public.event_milestone_statuses,
    public.event_vendor_checklist_items,
    public.crisis_recovery_records,
    public.crisis_recovery_actions
FROM authenticated;
