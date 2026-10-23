-- ==============================================================================
-- PlanProof AI - Migration 00005: Create Event Vendor Checklist Items Table
-- ==============================================================================
-- Description:
-- Establishes the public.event_vendor_checklist_items table tracking vendor
-- coordination tasks, calendar deadlines, priority levels, notes, and booking progress.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.event_vendor_checklist_items (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES public.events(event_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    due_date DATE,
    days_before_event INTEGER,
    priority TEXT NOT NULL DEFAULT 'medium',
    notes TEXT,
    vendor_name TEXT,
    booking_status TEXT NOT NULL DEFAULT 'not_started',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    -- Constraints matching Pydantic enum validation rules
    CONSTRAINT chk_vendor_category CHECK (
        category IN (
            'venue_permissions',
            'catering_refreshments',
            'decoration_setup',
            'photography_videography',
            'attire_beauty',
            'entertainment_equipment',
            'transport_logistics',
            'invitations_coordination',
            'cleanup_post_event'
        )
    ),
    CONSTRAINT chk_vendor_status CHECK (
        status IN ('pending', 'in_progress', 'completed', 'skipped')
    ),
    CONSTRAINT chk_vendor_priority CHECK (
        priority IN ('low', 'medium', 'high')
    ),
    CONSTRAINT chk_vendor_booking_status CHECK (
        booking_status IN ('not_started', 'researching', 'contacted', 'booked', 'cancelled')
    ),
    CONSTRAINT chk_vendor_days_before_event CHECK (
        days_before_event IS NULL OR days_before_event >= 0
    ),
    CONSTRAINT chk_vendor_title_length CHECK (length(title) >= 1 AND length(title) <= 150),
    CONSTRAINT chk_vendor_desc_length CHECK (length(description) >= 1 AND length(description) <= 500),
    CONSTRAINT chk_vendor_notes_length CHECK (notes IS NULL OR length(notes) <= 500),
    CONSTRAINT chk_vendor_name_length CHECK (vendor_name IS NULL OR length(vendor_name) <= 100)
);

CREATE INDEX IF NOT EXISTS idx_vendor_items_event_id ON public.event_vendor_checklist_items(event_id);
CREATE INDEX IF NOT EXISTS idx_vendor_items_event_status ON public.event_vendor_checklist_items(event_id, status);

-- Trigger to maintain updated_at on vendor checklist item update
DROP TRIGGER IF EXISTS trg_vendor_checklist_items_updated_at ON public.event_vendor_checklist_items;
CREATE TRIGGER trg_vendor_checklist_items_updated_at
    BEFORE UPDATE ON public.event_vendor_checklist_items
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

COMMENT ON TABLE public.event_vendor_checklist_items IS 'Vendor coordination tasks, booking milestones, and contact details for an event.';
