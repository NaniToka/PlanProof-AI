-- ==============================================================================
-- PlanProof AI - Down Migration 00001: Drop Profiles Table and Functions
-- ==============================================================================

-- Drop trigger on auth.users if exists and permitted
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'auth' AND tablename = 'users') THEN
        DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping auth.users trigger drop due to permissions: %', SQLERRM;
END $$;

DROP FUNCTION IF EXISTS public.handle_new_user();

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
DROP TABLE IF EXISTS public.profiles CASCADE;

DROP FUNCTION IF EXISTS public.handle_updated_at();
