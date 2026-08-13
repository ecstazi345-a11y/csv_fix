-- =============================================================================
-- R1.2.1 — Monthly Resource Plan security / catalog VERIFY (read-only)
-- =============================================================================
-- File:    sql/monthly_resource_plan_r1_security_verify.sql
-- Run:     Supabase SQL Editor AFTER hotfix. SELECT-only. No INSERT probes.
--
-- Expected after hotfix:
--   table row count = 0
--   view row count  = 0
--   probe __NOWRITE__ count = 0
--   anon / authenticated: SELECT yes; INSERT/UPDATE/DELETE no
--   service_role: SELECT + INSERT + UPDATE + DELETE yes (table)
--   view: SELECT only for anon / authenticated / service_role
-- =============================================================================

-- 1) Table row count
select count(*) as monthly_resource_plan_lines_count
from public.monthly_resource_plan_lines;

-- 2) View row count
select count(*) as monthly_resource_capacity_v1_count
from public.monthly_resource_capacity_v1;

-- 3) Privileges (table)
select
  grantee,
  privilege_type,
  is_grantable
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name = 'monthly_resource_plan_lines'
  and grantee in ('anon', 'authenticated', 'service_role', 'PUBLIC')
order by grantee, privilege_type;

-- 3b) Privileges (view)
select
  grantee,
  privilege_type,
  is_grantable
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name = 'monthly_resource_capacity_v1'
  and grantee in ('anon', 'authenticated', 'service_role', 'PUBLIC')
order by grantee, privilege_type;

-- 3c) Privilege matrix summary (expected shape)
with expected(role_name, privilege_type, allowed) as (
  values
    ('anon', 'SELECT', true),
    ('anon', 'INSERT', false),
    ('anon', 'UPDATE', false),
    ('anon', 'DELETE', false),
    ('authenticated', 'SELECT', true),
    ('authenticated', 'INSERT', false),
    ('authenticated', 'UPDATE', false),
    ('authenticated', 'DELETE', false),
    ('service_role', 'SELECT', true),
    ('service_role', 'INSERT', true),
    ('service_role', 'UPDATE', true),
    ('service_role', 'DELETE', true)
),
actual as (
  select grantee, privilege_type
  from information_schema.role_table_grants
  where table_schema = 'public'
    and table_name = 'monthly_resource_plan_lines'
)
select
  e.role_name,
  e.privilege_type,
  e.allowed as expected_allowed,
  (a.privilege_type is not null) as actually_granted,
  case
    when e.allowed and a.privilege_type is not null then 'OK'
    when (not e.allowed) and a.privilege_type is null then 'OK'
    else 'MISMATCH'
  end as check_result
from expected e
left join actual a
  on a.grantee = e.role_name
 and a.privilege_type = e.privilege_type
order by e.role_name, e.privilege_type;

-- 4) Table CHECK constraints
select
  con.conname,
  pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'monthly_resource_plan_lines'
  and con.contype = 'c'
order by con.conname;

-- 4b) Constraint presence flags (expected all true)
select
  exists (
    select 1 from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace nsp on nsp.oid = rel.relnamespace
    where nsp.nspname = 'public'
      and rel.relname = 'monthly_resource_plan_lines'
      and con.contype = 'c'
      and pg_get_constraintdef(con.oid) ilike '%resource_status%DRAFT%APPROVED%REJECTED%'
  ) as has_resource_status_check,
  exists (
    select 1 from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace nsp on nsp.oid = rel.relnamespace
    where nsp.nspname = 'public'
      and rel.relname = 'monthly_resource_plan_lines'
      and con.contype = 'c'
      and pg_get_constraintdef(con.oid) ilike '%confirmed_available_hours%>=%0%'
  ) as has_confirmed_hours_nonneg,
  exists (
    select 1 from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace nsp on nsp.oid = rel.relnamespace
    where nsp.nspname = 'public'
      and rel.relname = 'monthly_resource_plan_lines'
      and con.contype = 'c'
      and pg_get_constraintdef(con.oid) ilike '%planned_shift_hours%>=%0%'
  ) as has_planned_shift_hours_nonneg,
  exists (
    select 1 from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace nsp on nsp.oid = rel.relnamespace
    where nsp.nspname = 'public'
      and rel.relname = 'monthly_resource_plan_lines'
      and con.contype = 'c'
      and (
        con.conname = 'monthly_resource_plan_lines_date_range_chk'
        or pg_get_constraintdef(con.oid) ilike '%effective_to%>=%effective_from%'
      )
  ) as has_date_range_check,
  exists (
    select 1 from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace nsp on nsp.oid = rel.relnamespace
    where nsp.nspname = 'public'
      and rel.relname = 'monthly_resource_plan_lines'
      and con.contype = 'c'
      and (
        con.conname = 'monthly_resource_plan_lines_month_key_chk'
        or pg_get_constraintdef(con.oid) ilike '%month_key%'
      )
  ) as has_month_key_yyyy_mm_check,
  exists (
    select 1 from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace nsp on nsp.oid = rel.relnamespace
    where nsp.nspname = 'public'
      and rel.relname = 'monthly_resource_plan_lines'
      and con.contype = 'c'
      and (
        con.conname = 'monthly_resource_plan_lines_approved_meta_chk'
        or pg_get_constraintdef(con.oid) ilike '%APPROVED%approved_by%approved_at%'
      )
  ) as has_approved_integrity_check;

-- 5) Indexes
select
  i.relname as index_name,
  ix.indisunique as is_unique,
  ix.indisprimary as is_primary,
  pg_get_indexdef(ix.indexrelid) as index_def
from pg_index ix
join pg_class t on t.oid = ix.indrelid
join pg_class i on i.oid = ix.indexrelid
join pg_namespace nsp on nsp.oid = t.relnamespace
where nsp.nspname = 'public'
  and t.relname = 'monthly_resource_plan_lines'
order by i.relname;

-- 5b) Index presence flags (expected all true)
select
  exists (
    select 1 from pg_index ix
    join pg_class t on t.oid = ix.indrelid
    join pg_namespace nsp on nsp.oid = t.relnamespace
    where nsp.nspname = 'public'
      and t.relname = 'monthly_resource_plan_lines'
      and ix.indisprimary
  ) as has_pk,
  exists (
    select 1 from pg_class i
    join pg_index ix on ix.indexrelid = i.oid
    join pg_class t on t.oid = ix.indrelid
    join pg_namespace nsp on nsp.oid = t.relnamespace
    where nsp.nspname = 'public'
      and t.relname = 'monthly_resource_plan_lines'
      and i.relname = 'idx_mrp_lines_business_key'
      and ix.indisunique
  ) as has_unique_anti_duplicate,
  exists (
    select 1 from pg_class i
    join pg_index ix on ix.indexrelid = i.oid
    join pg_class t on t.oid = ix.indrelid
    join pg_namespace nsp on nsp.oid = t.relnamespace
    where nsp.nspname = 'public'
      and t.relname = 'monthly_resource_plan_lines'
      and i.relname = 'idx_mrp_lines_scope'
  ) as has_scope_index,
  exists (
    select 1 from pg_class i
    join pg_index ix on ix.indexrelid = i.oid
    join pg_class t on t.oid = ix.indrelid
    join pg_namespace nsp on nsp.oid = t.relnamespace
    where nsp.nspname = 'public'
      and t.relname = 'monthly_resource_plan_lines'
      and i.relname = 'idx_mrp_lines_scope_status'
  ) as has_scope_status_index;

-- 6) Probe row presence (expect 0 after hotfix)
select count(*) as probe_nowrite_count
from public.monthly_resource_plan_lines
where resource_plan_line_id = 'fff1e853-ccc5-485b-8e61-cff5d28ea424'
   or project_code = '__NOWRITE__';
