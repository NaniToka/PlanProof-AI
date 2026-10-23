-- ==============================================================================
-- PlanProof AI - Migration 00003: Create Event Budgets Table
-- ==============================================================================
-- Description:
-- Establishes the public.event_budgets table storing the 8 canonical budget category
-- allocations in integer Indian Rupees (INR) for each event profile.
-- Strictly enforces the non-negative invariant and that category allocations sum
-- exactly to total_budget_inr.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.event_budgets (
    event_id TEXT PRIMARY KEY REFERENCES public.events(event_id) ON DELETE CASCADE,
    venue BIGINT NOT NULL DEFAULT 0,
    catering BIGINT NOT NULL DEFAULT 0,
    decor BIGINT NOT NULL DEFAULT 0,
    photo_video BIGINT NOT NULL DEFAULT 0,
    attire_beauty BIGINT NOT NULL DEFAULT 0,
    entertainment BIGINT NOT NULL DEFAULT 0,
    logistics BIGINT NOT NULL DEFAULT 0,
    buffer BIGINT NOT NULL DEFAULT 0,
    total_budget_inr BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    -- Category non-negative constraints
    CONSTRAINT chk_venue_non_negative CHECK (venue >= 0),
    CONSTRAINT chk_catering_non_negative CHECK (catering >= 0),
    CONSTRAINT chk_decor_non_negative CHECK (decor >= 0),
    CONSTRAINT chk_photo_video_non_negative CHECK (photo_video >= 0),
    CONSTRAINT chk_attire_beauty_non_negative CHECK (attire_beauty >= 0),
    CONSTRAINT chk_entertainment_non_negative CHECK (entertainment >= 0),
    CONSTRAINT chk_logistics_non_negative CHECK (logistics >= 0),
    CONSTRAINT chk_buffer_non_negative CHECK (buffer >= 0),
    CONSTRAINT chk_total_budget_non_negative CHECK (total_budget_inr >= 0),

    -- Mathematical integrity check: categories must sum exactly to stated total budget
    CONSTRAINT chk_budget_sum_equals_total CHECK (
        venue + catering + decor + photo_video + attire_beauty + entertainment + logistics + buffer = total_budget_inr
    )
);

-- Trigger to maintain updated_at on budget rebalancing/updates
DROP TRIGGER IF EXISTS trg_event_budgets_updated_at ON public.event_budgets;
CREATE TRIGGER trg_event_budgets_updated_at
    BEFORE UPDATE ON public.event_budgets
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

COMMENT ON TABLE public.event_budgets IS 'Canonical 8-category budget allocations in integer INR summing exactly to total event budget.';
