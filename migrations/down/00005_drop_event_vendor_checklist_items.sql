-- ==============================================================================
-- PlanProof AI - Down Migration 00005: Drop Vendor Checklist Items Table
-- ==============================================================================

DROP TRIGGER IF EXISTS trg_vendor_checklist_items_updated_at ON public.event_vendor_checklist_items;
DROP TABLE IF EXISTS public.event_vendor_checklist_items CASCADE;
