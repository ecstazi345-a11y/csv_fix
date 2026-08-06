-- =============================================================================
-- Post-deploy verification: monthly_plan_management_decisions R1 (read-only)
-- File:   sql/tests/monthly_plan_management_decisions_r1_verify.sql
-- Deploy: run in Supabase SQL Editor AFTER migration.
-- Safe: does not INSERT/UPDATE/DELETE product rows.
-- =============================================================================

-- 1) Table exists
select to_regclass('public.monthly_plan_management_decisions') as management_decisions_table;

-- 2) Columns and types
select
  column_name,
  data_type,
  udt_name,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'monthly_plan_management_decisions'
order by ordinal_position;

-- 3) plan_line_id must be uuid
select
  column_name,
  udt_name,
  data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'monthly_plan_management_decisions'
  and column_name in ('decision_id', 'plan_line_id', 'decided_at', 'updated_at', 'review_deadline');

-- 4) Unique grain index
select
  indexname,
  indexdef
from pg_indexes
where schemaname = 'public'
  and tablename = 'monthly_plan_management_decisions'
order by indexname;

-- 5) CHECK constraints
select
  con.conname,
  pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'monthly_plan_management_decisions'
  and con.contype = 'c'
order by con.conname;

-- 6) RPC signatures + security
select
  p.proname,
  pg_get_function_identity_arguments(p.oid) as args,
  p.prosecdef as security_definer,
  p.proconfig as config
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname in (
    'apply_monthly_plan_management_decision',
    'cancel_monthly_plan_management_decision'
  )
order by p.proname;

-- 7) Function grants
select
  routine_name,
  grantee,
  privilege_type
from information_schema.routine_privileges
where specific_schema = 'public'
  and routine_name in (
    'apply_monthly_plan_management_decision',
    'cancel_monthly_plan_management_decision'
  )
order by routine_name, grantee;

-- 8) Table grants
select
  grantee,
  privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name = 'monthly_plan_management_decisions'
order by grantee, privilege_type;

-- 9) RLS status
select
  c.relname,
  c.relrowsecurity as rls_enabled,
  c.relforcerowsecurity as rls_forced
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname = 'monthly_plan_management_decisions';

-- 10) Product row counts (expect 0 TEST_MGMT after clean deploy)
select
  count(*) as total_rows,
  count(*) filter (where project_code = 'TEST_MGMT') as test_mgmt_rows,
  count(*) filter (where decision_status = 'ACTIVE') as active_rows,
  count(*) filter (where decision = 'INCLUDE_RISK' and decision_status = 'ACTIVE') as active_include_risk
from public.monthly_plan_management_decisions;

-- 11) Sample rehydrate contract shape (read-only; may return 0 rows)
select
  plan_line_id,
  decision,
  decision_basis,
  responsible_person,
  review_deadline,
  decision_comment,
  risk_description,
  risk_impact,
  risk_mitigation_owner,
  risk_mitigation_deadline,
  risk_acceptance_basis,
  risk_manager_comment,
  risk_blocker,
  admission_outcome_at_decision,
  management_override,
  decided_by,
  decided_at
from public.monthly_plan_management_decisions
where project_code = 'PRJ_001_БХК'
  and month_key = 'август-2026'
  and decision_status = 'ACTIVE'
limit 20;
