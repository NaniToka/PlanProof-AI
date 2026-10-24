-- ==============================================================================
-- PlanProof AI - Migration 00009: Grant Role Permissions for RLS Policies
-- ==============================================================================
-- Description:
-- Grants appropriate schema and table permissions to 'authenticated' and 'anon' roles
-- so that PostgreSQL can evaluate Row Level Security (RLS) policies.
-- Architecture Requirements for Application Connection Role:
-- 1. The database connection role (e.g. planproof_app) MUST NOT have BYPASSRLS or superuser privileges.
-- 2. The connection role must be granted membership in 'authenticated' (GRANT authenticated TO <app_role>;)
--    so it can switch to 'authenticated' within transactions via set_config('role', 'authenticated', true).
-- 3. In production Supabase, standard pooler connections execute under authenticated or authenticator context.
-- 4. 'anon' role is restricted to USAGE on schema public; no SELECT/write permissions on private tables.
-- ==============================================================================

GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
