-- ==============================================================================
-- PlanProof AI - Migration 00007: Create Crisis Recovery Actions Table
-- ==============================================================================
-- Description:
-- Establishes the public.crisis_recovery_actions table storing individual actionable
-- recovery steps tracked within an event crisis recovery record.
-- Supports granular tracking (status: pending, in_progress, completed) and coordinator notes.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.crisis_recovery_actions (
    action_id TEXT PRIMARY KEY,
    recovery_id TEXT NOT NULL REFERENCES public.crisis_recovery_records(recovery_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES public.events(event_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    -- Constraints matching Pydantic validation rules
    CONSTRAINT chk_action_title_length CHECK (length(title) >= 1 AND length(title) <= 200),
    CONSTRAINT chk_action_description_length CHECK (length(description) >= 1 AND length(description) <= 1000),
    CONSTRAINT chk_action_priority CHECK (priority >= 1 AND priority <= 3),
    CONSTRAINT chk_action_status CHECK (status IN ('pending', 'in_progress', 'completed')),
    CONSTRAINT chk_action_notes_length CHECK (notes IS NULL OR length(notes) <= 1000)
);

CREATE INDEX IF NOT EXISTS idx_recovery_actions_recovery_id ON public.crisis_recovery_actions(recovery_id);
CREATE INDEX IF NOT EXISTS idx_recovery_actions_event_id ON public.crisis_recovery_actions(event_id);

-- Trigger to maintain updated_at on action status or notes update
DROP TRIGGER IF EXISTS trg_crisis_recovery_actions_updated_at ON public.crisis_recovery_actions;
CREATE TRIGGER trg_crisis_recovery_actions_updated_at
    BEFORE UPDATE ON public.crisis_recovery_actions
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

COMMENT ON TABLE public.crisis_recovery_actions IS 'Individual actionable recovery tasks belonging to a crisis recovery record.';
