-- ==============================================================================
-- PlanProof AI - Down Migration 00004: Drop Milestone Statuses Table
-- ==============================================================================

DROP TRIGGER IF EXISTS trg_milestone_statuses_updated_at ON public.event_milestone_statuses;
DROP TABLE IF EXISTS public.event_milestone_statuses CASCADE;
