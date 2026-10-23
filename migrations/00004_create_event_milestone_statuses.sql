-- ==============================================================================
-- PlanProof AI - Migration 00004: Create Event Milestone Statuses Table
-- ==============================================================================
-- Description:
-- Establishes the public.event_milestone_statuses table storing user completion
-- status overrides ('pending', 'completed') for timeline milestones.
-- Milestone definitions and lead-time days are derived deterministically from code
-- templates; this table persists user completion checkmarks.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.event_milestone_statuses (
    event_id TEXT NOT NULL REFERENCES public.events(event_id) ON DELETE CASCADE,
    milestone_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    PRIMARY KEY (event_id, milestone_id),
    CONSTRAINT chk_milestone_id_length CHECK (length(milestone_id) >= 1 AND length(milestone_id) <= 50),
    CONSTRAINT chk_milestone_status CHECK (status IN ('pending', 'completed'))
);

CREATE INDEX IF NOT EXISTS idx_milestone_statuses_event_id ON public.event_milestone_statuses(event_id);

-- Trigger to maintain updated_at on milestone status toggle
DROP TRIGGER IF EXISTS trg_milestone_statuses_updated_at ON public.event_milestone_statuses;
CREATE TRIGGER trg_milestone_statuses_updated_at
    BEFORE UPDATE ON public.event_milestone_statuses
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

COMMENT ON TABLE public.event_milestone_statuses IS 'User completion status overrides for timeline milestones scoped to an event.';
