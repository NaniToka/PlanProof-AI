-- ==============================================================================
-- PlanProof AI - Down Migration 00009: Revoke Role Permissions for RLS
-- ==============================================================================

REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM authenticated;
REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM anon;
REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
REVOKE USAGE ON SCHEMA public FROM anon, authenticated;
