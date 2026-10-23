-- ==============================================================================
-- PlanProof AI - Migration 00009: Grant Role Permissions for RLS Policies
-- ==============================================================================
-- Description:
-- Grants appropriate schema and table permissions to 'authenticated' and 'anon' roles
-- so that PostgreSQL can evaluate Row Level Security (RLS) policies.
-- In production Supabase, these permissions are established automatically.
-- ==============================================================================

GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
