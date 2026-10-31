-- ==============================================================================
-- PlanProof AI - Migration 00009: Grant Role Permissions for RLS Policies
-- ==============================================================================
-- Description:
-- Grants least-privilege table permissions to the 'authenticated' role for the
-- seven PlanProof AI application tables so PostgreSQL can evaluate Row Level
-- Security (RLS) policies.
--
-- Security Design & Least-Privilege Enforcement:
-- 1. Explicitly grants table permissions ONLY on the seven PlanProof AI application tables.
-- 2. Strictly avoids broad 'ON ALL TABLES IN SCHEMA public' grants to prevent
--    privilege leakage to future, temporary, or unrelated tables.
-- 3. 'anon' role is restricted to USAGE on schema public; zero read or write
--    permissions are granted to 'anon' on private application tables.
-- 4. Omits sequence grants as all seven tables use UUID or string slug primary keys.
-- 5. Application database connection switches to 'authenticated' inside transactions
--    via set_config('role', 'authenticated', true).
-- ==============================================================================

GRANT USAGE ON SCHEMA public TO anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.profiles,
    public.events,
    public.event_budgets,
    public.event_milestone_statuses,
    public.event_vendor_checklist_items,
    public.crisis_recovery_records,
    public.crisis_recovery_actions
TO authenticated;
