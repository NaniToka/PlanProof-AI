-- ==============================================================================
-- PlanProof AI - Migration 00006: Create Crisis Recovery Records Table
-- ==============================================================================
-- Description:
-- Establishes the public.crisis_recovery_records table storing historical crisis
-- recovery plans and progress tracking records for each event.
-- Preserves the full validated recovery plan as JSONB along with severity, status,
-- and summary progress counts.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.crisis_recovery_records (
    recovery_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES public.events(event_id) ON DELETE CASCADE,
    crisis_type TEXT NOT NULL,
    severity INTEGER NOT NULL,
    description TEXT,
    recovery_plan JSONB NOT NULL,
    source TEXT NOT NULL DEFAULT 'rules',
    status TEXT NOT NULL DEFAULT 'open',
    total_actions INTEGER NOT NULL DEFAULT 0,
    completed_actions INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    -- Constraints matching Pydantic validation rules
    CONSTRAINT chk_recovery_crisis_type_length CHECK (length(crisis_type) >= 2 AND length(crisis_type) <= 100),
    CONSTRAINT chk_recovery_severity CHECK (severity >= 1 AND severity <= 3),
    CONSTRAINT chk_recovery_status CHECK (status IN ('open', 'in_progress', 'resolved')),
    CONSTRAINT chk_recovery_description_length CHECK (description IS NULL OR length(description) <= 1000),
    CONSTRAINT chk_recovery_source_length CHECK (length(source) <= 50),
    CONSTRAINT chk_recovery_total_actions CHECK (total_actions >= 0),
    CONSTRAINT chk_recovery_completed_actions CHECK (completed_actions >= 0),
    CONSTRAINT chk_recovery_completed_le_total CHECK (completed_actions <= total_actions)
);

CREATE INDEX IF NOT EXISTS idx_recovery_records_event_id ON public.crisis_recovery_records(event_id);
CREATE INDEX IF NOT EXISTS idx_recovery_records_event_created ON public.crisis_recovery_records(event_id, created_at DESC);

-- Trigger to maintain updated_at on recovery record update
DROP TRIGGER IF EXISTS trg_crisis_recovery_records_updated_at ON public.crisis_recovery_records;
CREATE TRIGGER trg_crisis_recovery_records_updated_at
    BEFORE UPDATE ON public.crisis_recovery_records
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

COMMENT ON TABLE public.crisis_recovery_records IS 'Historical crisis recovery plan logs and action tracker headers scoped to an event.';
