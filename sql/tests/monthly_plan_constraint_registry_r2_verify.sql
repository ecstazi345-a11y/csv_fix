-- =============================================================================
-- Post-deploy verification for Registry R2.1 (read-only)
-- File: sql/tests/monthly_plan_constraint_registry_r2_verify.sql
-- Run in Supabase SQL Editor after migration. Safe. No product writes.
-- =============================================================================

-- 1) New columns / types / defaults
select
  column_name,
  data_type,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'monthly_plan_constraints'
  and column_name in (
    'constraint_occurred_at',
    'subcontractor_coordinator',
    'problem_description',
    'problem_impact',
    'deadline_status',
    'deadline_source',
    'next_control_date',
    'constraint_priority',
    'resolution_basis',
    'constraint_category',
    'problem_owner',
    'required_action',
    'actual_resolution_date',
    'owner_name',
    'constraint_created_at'
  )
order by column_name;

-- 2) CHECKs (category must NOT have R2 enum check)
select
  con.conname,
  pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'monthly_plan_constraints'
  and con.contype = 'c'
  and con.conname in (
    'monthly_plan_constraints_deadline_status_chk',
    'monthly_plan_constraints_deadline_source_chk',
    'monthly_plan_constraints_constraint_priority_chk'
  )
order by con.conname;

select
  count(*) as category_enum_check_count
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'monthly_plan_constraints'
  and con.contype = 'c'
  and pg_get_constraintdef(con.oid) ilike '%constraint_category%ENGINEERING%';

-- 3) Indexes
select
  indexname,
  indexdef
from pg_indexes
where schemaname = 'public'
  and tablename = 'monthly_plan_constraints'
  and indexname like 'idx_mpc_r2_%'
order by indexname;

-- 4) update / resolve RPC signatures
select
  p.proname,
  pg_get_function_identity_arguments(p.oid) as args,
  p.prosecdef as security_definer
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname in (
    'update_monthly_plan_constraint',
    'resolve_monthly_plan_constraint'
  )
order by p.proname;

-- 5) Grants
select
  routine_name,
  grantee,
  privilege_type
from information_schema.routine_privileges
where specific_schema = 'public'
  and routine_name in (
    'update_monthly_plan_constraint',
    'resolve_monthly_plan_constraint'
  )
order by routine_name, grantee;

-- 6) dashboard_v2 columns (R2 + computed)
select column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'monthly_plan_constraints_dashboard_v2'
  and column_name in (
    'constraint_occurred_at',
    'subcontractor_coordinator',
    'problem_description',
    'problem_impact',
    'deadline_status',
    'deadline_source',
    'next_control_date',
    'constraint_priority',
    'resolution_basis',
    'days_open',
    'days_overdue',
    'is_overdue',
    'days_open_real',
    'deadline_days_overdue',
    'is_deadline_overdue',
    'is_next_control_overdue',
    'effective_deadline_status',
    'evidence_count',
    'effective_promised_date',
    'days_since_promise',
    'is_promise_overdue'
  )
order by column_name;

-- 7) Product counts (unchanged by migration alone)
select count(*) as constraints_total
from public.monthly_plan_constraints;

select count(*) as events_total
from public.monthly_plan_constraint_events;

select count(*) as test_reg_r2_rows
from public.monthly_plan_constraints
where project_code = 'TEST_REG_R2';

-- Expect test_reg_r2_rows = 0 after tests ROLLBACK / before tests.

-- 8) deadline_status / priority fill after migration defaults
select
  count(*) filter (where deadline_status is null) as deadline_status_nulls,
  count(*) filter (where constraint_priority is null) as priority_nulls,
  count(*) filter (where deadline_status = 'NOT_SET') as deadline_not_set,
  count(*) filter (where constraint_priority = 'NORMAL') as priority_normal
from public.monthly_plan_constraints;

-- 9) RLS status (informational — do not change)
select
  c.relname,
  c.relrowsecurity as rls_enabled,
  c.relforcerowsecurity as rls_forced
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in (
    'monthly_plan_constraints',
    'monthly_plan_constraint_events'
  )
order by c.relname;

-- 10) Reload PostgREST schema cache (safe)
notify pgrst, 'reload schema';
