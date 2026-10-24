-- ==============================================================================
-- PlanProof AI - Migration 00008: Enable Row Level Security (RLS) & Policies
-- ==============================================================================
-- Description:
-- Enforces strict multi-tenant data isolation using Supabase Row Level Security (RLS).
-- Guarantees:
-- 1. Authenticated users can only read, insert, and update their own profile.
-- 2. Authenticated users can only view, create, edit, or delete events they own.
-- 3. Users cannot reassign an event's owner to another user's UUID.
-- 4. Access to dependent event child tables (budgets, milestones, vendor items,
--    crisis recovery records, crisis recovery actions) is strictly restricted
--    via parent event ownership.
-- 5. Anonymous users cannot read or mutate persistent user-owned records.
-- ==============================================================================

-- Note: auth.uid() is natively provided and maintained by Supabase Auth in the auth schema.
-- Application migrations do not define or overwrite objects in the auth schema.


-- ------------------------------------------------------------------------------
-- 1. Enable RLS on all 7 application tables
-- ------------------------------------------------------------------------------
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_milestone_statuses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_vendor_checklist_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crisis_recovery_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crisis_recovery_actions ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------------------------
-- 2. Profiles Table Policies
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
CREATE POLICY "profiles_select_own"
    ON public.profiles
    FOR SELECT
    TO authenticated
    USING (auth.uid() = id);

DROP POLICY IF EXISTS "profiles_insert_own" ON public.profiles;
CREATE POLICY "profiles_insert_own"
    ON public.profiles
    FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
CREATE POLICY "profiles_update_own"
    ON public.profiles
    FOR UPDATE
    TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- ------------------------------------------------------------------------------
-- 3. Events Table Policies (Owner Isolation & Anti-Reassignment)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "events_select_own" ON public.events;
CREATE POLICY "events_select_own"
    ON public.events
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "events_insert_own" ON public.events;
CREATE POLICY "events_insert_own"
    ON public.events
    FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "events_update_own" ON public.events;
CREATE POLICY "events_update_own"
    ON public.events
    FOR UPDATE
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "events_delete_own" ON public.events;
CREATE POLICY "events_delete_own"
    ON public.events
    FOR DELETE
    TO authenticated
    USING (auth.uid() = user_id);

-- ------------------------------------------------------------------------------
-- 4. Event Budgets Table Policies (Parent Event Ownership)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "budgets_select_own" ON public.event_budgets;
CREATE POLICY "budgets_select_own"
    ON public.event_budgets
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_budgets.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "budgets_insert_own" ON public.event_budgets;
CREATE POLICY "budgets_insert_own"
    ON public.event_budgets
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_budgets.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "budgets_update_own" ON public.event_budgets;
CREATE POLICY "budgets_update_own"
    ON public.event_budgets
    FOR UPDATE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_budgets.event_id
              AND events.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_budgets.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "budgets_delete_own" ON public.event_budgets;
CREATE POLICY "budgets_delete_own"
    ON public.event_budgets
    FOR DELETE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_budgets.event_id
              AND events.user_id = auth.uid()
        )
    );

-- ------------------------------------------------------------------------------
-- 5. Event Milestone Statuses Policies (Parent Event Ownership)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "milestones_select_own" ON public.event_milestone_statuses;
CREATE POLICY "milestones_select_own"
    ON public.event_milestone_statuses
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_milestone_statuses.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "milestones_insert_own" ON public.event_milestone_statuses;
CREATE POLICY "milestones_insert_own"
    ON public.event_milestone_statuses
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_milestone_statuses.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "milestones_update_own" ON public.event_milestone_statuses;
CREATE POLICY "milestones_update_own"
    ON public.event_milestone_statuses
    FOR UPDATE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_milestone_statuses.event_id
              AND events.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_milestone_statuses.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "milestones_delete_own" ON public.event_milestone_statuses;
CREATE POLICY "milestones_delete_own"
    ON public.event_milestone_statuses
    FOR DELETE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_milestone_statuses.event_id
              AND events.user_id = auth.uid()
        )
    );

-- ------------------------------------------------------------------------------
-- 6. Event Vendor Checklist Items Policies (Parent Event Ownership)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "vendor_items_select_own" ON public.event_vendor_checklist_items;
CREATE POLICY "vendor_items_select_own"
    ON public.event_vendor_checklist_items
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_vendor_checklist_items.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "vendor_items_insert_own" ON public.event_vendor_checklist_items;
CREATE POLICY "vendor_items_insert_own"
    ON public.event_vendor_checklist_items
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_vendor_checklist_items.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "vendor_items_update_own" ON public.event_vendor_checklist_items;
CREATE POLICY "vendor_items_update_own"
    ON public.event_vendor_checklist_items
    FOR UPDATE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_vendor_checklist_items.event_id
              AND events.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_vendor_checklist_items.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "vendor_items_delete_own" ON public.event_vendor_checklist_items;
CREATE POLICY "vendor_items_delete_own"
    ON public.event_vendor_checklist_items
    FOR DELETE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = event_vendor_checklist_items.event_id
              AND events.user_id = auth.uid()
        )
    );

-- ------------------------------------------------------------------------------
-- 7. Crisis Recovery Records Policies (Parent Event Ownership)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "recovery_records_select_own" ON public.crisis_recovery_records;
CREATE POLICY "recovery_records_select_own"
    ON public.crisis_recovery_records
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_records.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "recovery_records_insert_own" ON public.crisis_recovery_records;
CREATE POLICY "recovery_records_insert_own"
    ON public.crisis_recovery_records
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_records.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "recovery_records_update_own" ON public.crisis_recovery_records;
CREATE POLICY "recovery_records_update_own"
    ON public.crisis_recovery_records
    FOR UPDATE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_records.event_id
              AND events.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_records.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "recovery_records_delete_own" ON public.crisis_recovery_records;
CREATE POLICY "recovery_records_delete_own"
    ON public.crisis_recovery_records
    FOR DELETE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_records.event_id
              AND events.user_id = auth.uid()
        )
    );

-- ------------------------------------------------------------------------------
-- 8. Crisis Recovery Actions Policies (Parent Event Ownership)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "recovery_actions_select_own" ON public.crisis_recovery_actions;
CREATE POLICY "recovery_actions_select_own"
    ON public.crisis_recovery_actions
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_actions.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "recovery_actions_insert_own" ON public.crisis_recovery_actions;
CREATE POLICY "recovery_actions_insert_own"
    ON public.crisis_recovery_actions
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_actions.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "recovery_actions_update_own" ON public.crisis_recovery_actions;
CREATE POLICY "recovery_actions_update_own"
    ON public.crisis_recovery_actions
    FOR UPDATE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_actions.event_id
              AND events.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_actions.event_id
              AND events.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "recovery_actions_delete_own" ON public.crisis_recovery_actions;
CREATE POLICY "recovery_actions_delete_own"
    ON public.crisis_recovery_actions
    FOR DELETE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.events
            WHERE events.event_id = crisis_recovery_actions.event_id
              AND events.user_id = auth.uid()
        )
    );
