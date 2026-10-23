-- ==============================================================================
-- PlanProof AI - Down Migration 00008: Disable RLS and Drop Policies
-- ==============================================================================

-- Drop Policies
DROP POLICY IF EXISTS "recovery_actions_delete_own" ON public.crisis_recovery_actions;
DROP POLICY IF EXISTS "recovery_actions_update_own" ON public.crisis_recovery_actions;
DROP POLICY IF EXISTS "recovery_actions_insert_own" ON public.crisis_recovery_actions;
DROP POLICY IF EXISTS "recovery_actions_select_own" ON public.crisis_recovery_actions;

DROP POLICY IF EXISTS "recovery_records_delete_own" ON public.crisis_recovery_records;
DROP POLICY IF EXISTS "recovery_records_update_own" ON public.crisis_recovery_records;
DROP POLICY IF EXISTS "recovery_records_insert_own" ON public.crisis_recovery_records;
DROP POLICY IF EXISTS "recovery_records_select_own" ON public.crisis_recovery_records;

DROP POLICY IF EXISTS "vendor_items_delete_own" ON public.event_vendor_checklist_items;
DROP POLICY IF EXISTS "vendor_items_update_own" ON public.event_vendor_checklist_items;
DROP POLICY IF EXISTS "vendor_items_insert_own" ON public.event_vendor_checklist_items;
DROP POLICY IF EXISTS "vendor_items_select_own" ON public.event_vendor_checklist_items;

DROP POLICY IF EXISTS "milestones_delete_own" ON public.event_milestone_statuses;
DROP POLICY IF EXISTS "milestones_update_own" ON public.event_milestone_statuses;
DROP POLICY IF EXISTS "milestones_insert_own" ON public.event_milestone_statuses;
DROP POLICY IF EXISTS "milestones_select_own" ON public.event_milestone_statuses;

DROP POLICY IF EXISTS "budgets_delete_own" ON public.event_budgets;
DROP POLICY IF EXISTS "budgets_update_own" ON public.event_budgets;
DROP POLICY IF EXISTS "budgets_insert_own" ON public.event_budgets;
DROP POLICY IF EXISTS "budgets_select_own" ON public.event_budgets;

DROP POLICY IF EXISTS "events_delete_own" ON public.events;
DROP POLICY IF EXISTS "events_update_own" ON public.events;
DROP POLICY IF EXISTS "events_insert_own" ON public.events;
DROP POLICY IF EXISTS "events_select_own" ON public.events;

DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;

-- Disable RLS
ALTER TABLE IF EXISTS public.crisis_recovery_actions DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.crisis_recovery_records DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.event_vendor_checklist_items DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.event_milestone_statuses DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.event_budgets DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.events DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.profiles DISABLE ROW LEVEL SECURITY;
