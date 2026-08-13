-- =============================================================================
-- R1.2.1 — Monthly Resource Plan security hotfix
-- =============================================================================
-- File:    sql/monthly_resource_plan_r1_security_hotfix.sql
-- Deploy:  Supabase SQL Editor MANUALLY after review. Do NOT auto-run.
--
-- Scope ONLY:
--   A) Fix grants on monthly_resource_plan_lines / monthly_resource_capacity_v1
--   B) Controlled delete of the single post-deploy __NOWRITE__ probe row
--
-- Does NOT:
--   - recreate table/view
--   - alter constraints / indexes
--   - touch other schemas / product tables
--   - enable RLS
--   - change capacity math / Page22 / Page22B
-- =============================================================================

-- ---------------------------------------------------------------------------
-- A) Privileges — named-role revoke (PUBLIC revoke alone is insufficient)
-- ---------------------------------------------------------------------------
-- Root cause:
--   REVOKE ALL ... FROM public clears only the PUBLIC pseudo-role.
--   Supabase default privileges typically leave INSERT/UPDATE/DELETE on
--   anon / authenticated after CREATE TABLE. Revoke those roles by name.

revoke all on table public.monthly_resource_plan_lines from public;
revoke all on table public.monthly_resource_capacity_v1 from public;

revoke all on table public.monthly_resource_plan_lines
  from anon, authenticated;

revoke all on table public.monthly_resource_capacity_v1
  from anon, authenticated;

-- Table: SELECT for app rehydrate; WRITE only service_role
grant select on table public.monthly_resource_plan_lines
  to anon, authenticated, service_role;

grant select, insert, update, delete on table public.monthly_resource_plan_lines
  to service_role;

-- View: SELECT only for all API roles (no write grants)
grant select on table public.monthly_resource_capacity_v1
  to anon, authenticated, service_role;

revoke insert, update, delete on table public.monthly_resource_capacity_v1
  from anon, authenticated, service_role, public;

-- ---------------------------------------------------------------------------
-- B) Controlled cleanup — exact probe row only
-- ---------------------------------------------------------------------------
delete from public.monthly_resource_plan_lines
where resource_plan_line_id = 'fff1e853-ccc5-485b-8e61-cff5d28ea424'
  and project_code = '__NOWRITE__'
  and month_key = '2099-01'
  and crew_code = 'X'
  and person_name = 'X'
  and resource_status = 'DRAFT'
  and confirmed_available_hours = 0;
