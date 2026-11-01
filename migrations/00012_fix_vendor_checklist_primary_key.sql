-- ==============================================================================
-- PlanProof AI - Migration 00012: Fix Vendor Checklist Items Primary Key
-- ==============================================================================
-- Description:
-- Updates the primary key of public.event_vendor_checklist_items from a single-column
-- key (id) to a composite primary key (event_id, id).
--
-- Background:
-- Vendor checklist items share standardized template IDs (e.g. 'VCL-WED-01') across
-- events of the same type. With a single-column primary key on `id`, creating a second
-- event of the same type violated uniqueness on `event_vendor_checklist_items_pkey`.
-- Scoping the primary key to (event_id, id) enables multiple events to maintain their
-- own checklist items without key collisions, matching the pattern in
-- event_milestone_statuses (event_id, milestone_id).
-- ==============================================================================

ALTER TABLE public.event_vendor_checklist_items
    DROP CONSTRAINT IF EXISTS event_vendor_checklist_items_pkey;

ALTER TABLE public.event_vendor_checklist_items
    ADD CONSTRAINT event_vendor_checklist_items_pkey PRIMARY KEY (event_id, id);
