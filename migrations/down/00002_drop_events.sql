-- ==============================================================================
-- PlanProof AI - Down Migration 00002: Drop Events Table
-- ==============================================================================

DROP TRIGGER IF EXISTS trg_events_updated_at ON public.events;
DROP TABLE IF EXISTS public.events CASCADE;
