-- ==============================================================================
-- PlanProof AI - Down Migration 00012: Revert Vendor Checklist Primary Key
-- ==============================================================================

ALTER TABLE public.event_vendor_checklist_items
    DROP CONSTRAINT IF EXISTS event_vendor_checklist_items_pkey;

ALTER TABLE public.event_vendor_checklist_items
    ADD CONSTRAINT event_vendor_checklist_items_pkey PRIMARY KEY (id);

