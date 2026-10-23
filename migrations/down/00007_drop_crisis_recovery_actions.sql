-- ==============================================================================
-- PlanProof AI - Down Migration 00007: Drop Crisis Recovery Actions Table
-- ==============================================================================

DROP TRIGGER IF EXISTS trg_crisis_recovery_actions_updated_at ON public.crisis_recovery_actions;
DROP TABLE IF EXISTS public.crisis_recovery_actions CASCADE;
