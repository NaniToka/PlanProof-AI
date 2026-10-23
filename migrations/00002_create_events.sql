-- ==============================================================================
-- PlanProof AI - Migration 00002: Create Events Table
-- ==============================================================================
-- Description:
-- Establishes the public.events table representing the core EventProfile entity.
-- Enforces explicit owner relationship to public.profiles(id), valid event types,
-- city logistics tiers, supported languages, and budget/headcount boundaries.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.events (
    event_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_name TEXT,
    city TEXT,
    city_tier TEXT NOT NULL DEFAULT 'metro',
    event_date DATE,
    guest_count INTEGER NOT NULL,
    total_budget_inr BIGINT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    theme_notes TEXT NOT NULL DEFAULT '',
    is_in_progress BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    -- Domain value constraints matching Pydantic validation rules
    CONSTRAINT chk_event_type CHECK (event_type IN ('wedding', 'birthday', 'community_event')),
    CONSTRAINT chk_city_tier CHECK (city_tier IN ('metro', 'tier2', 'tier3')),
    CONSTRAINT chk_language CHECK (language IN ('en', 'hi', 'te', 'ta', 'kn', 'bn')),
    CONSTRAINT chk_guest_count CHECK (guest_count >= 1 AND guest_count <= 2000),
    CONSTRAINT chk_total_budget_inr CHECK (total_budget_inr >= 10000 AND total_budget_inr <= 50000000),
    CONSTRAINT chk_event_name_length CHECK (event_name IS NULL OR length(event_name) <= 100),
    CONSTRAINT chk_city_length CHECK (city IS NULL OR length(city) <= 100),
    CONSTRAINT chk_theme_notes_length CHECK (length(theme_notes) <= 1000)
);

-- Performance and tenancy query indexes
CREATE INDEX IF NOT EXISTS idx_events_user_id ON public.events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_user_updated_at ON public.events(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_event_date ON public.events(event_date);

-- Trigger to maintain updated_at on event modification
DROP TRIGGER IF EXISTS trg_events_updated_at ON public.events;
CREATE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON public.events
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

COMMENT ON TABLE public.events IS 'Core event planning profile owned by an authenticated user.';
