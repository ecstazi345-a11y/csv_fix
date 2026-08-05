-- =============================================================================
-- Post-deploy verification for Registry R1 (read-only + NOTIFY)
-- Run in Supabase SQL Editor. Safe. Does not modify product rows.
-- =============================================================================

-- 1) new fields
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public'
  and table_name = 'monthly_plan_constraints'
  and column_name in (
    'actual_resolution_date',
    'required_action',
    'problem_owner'
  )
order by column_name;

-- 2) audit table
select to_regclass('public.monthly_plan_constraint_events') as events_table;

-- 3) RPC
select
  p.proname,
  pg_get_function_identity_arguments(p.oid) as args
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname = 'resolve_monthly_plan_constraint';

-- 4) grants
select
  grantee,
  privilege_type
from information_schema.routine_privileges
where specific_schema = 'public'
  and routine_name = 'resolve_monthly_plan_constraint'
order by grantee;

-- 5) views
select
  to_regclass('public.monthly_plan_constraints_dashboard_v1') as dashboard_v1,
  to_regclass('public.monthly_plan_constraints_dashboard_v2') as dashboard_v2;

-- 6) events empty after migration
select count(*) as events_count
from public.monthly_plan_constraint_events;

-- 7) reload PostgREST schema cache
notify pgrst, 'reload schema';
