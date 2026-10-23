-- ==============================================================================
-- PlanProof AI - Down Migration 00006: Drop Crisis Recovery Records Table
-- ==============================================================================

DROP TRIGGER IF EXISTS trg_crisis_recovery_records_updated_at ON public.crisis_recovery_records;
DROP TABLE IF EXISTS public.crisis_recovery_records CASCADE;
