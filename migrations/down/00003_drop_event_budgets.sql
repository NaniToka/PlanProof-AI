-- ==============================================================================
-- PlanProof AI - Down Migration 00003: Drop Event Budgets Table
-- ==============================================================================

DROP TRIGGER IF EXISTS trg_event_budgets_updated_at ON public.event_budgets;
DROP TABLE IF EXISTS public.event_budgets CASCADE;
