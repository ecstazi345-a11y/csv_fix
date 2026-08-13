-- =============================================================================
-- R1.2 — Monthly Resource Plan / Capacity Confirmation
-- =============================================================================
-- File:    sql/monthly_resource_plan_r1.sql
-- Deploy:  Supabase SQL Editor MANUALLY after review. Do NOT auto-run on prod.
--
-- Adds:
--   public.monthly_resource_plan_lines
--   public.monthly_resource_capacity_v1
--
-- Purpose:
--   Approved future-month crew capacity SoT for Page 22 Resource Gate.
--   Crew_Register / monthly_labor_summary remain people / assignment sources.
--   Daily Progress remains actual consumption.
--
-- Grain:
--   1 row = person + project + month(YYYY-MM) + crew + effective assignment period
--
-- Capacity rule:
--   available hours = SUM(confirmed_available_hours) WHERE resource_status = 'APPROVED'
--   approved_people_count = COUNT(DISTINCT person identity)
--
-- Security (planning-contour pattern / R1.2.1):
--   SELECT: anon, authenticated, service_role
--   WRITE:  service_role only (explicit REVOKE WRITE from anon/authenticated)
--   NOTE:   REVOKE FROM public alone does NOT remove Supabase default grants
--           on named roles anon/authenticated — revoke those roles explicitly.
--   RLS:    not enabled in R1.2 (grants + SECRET_KEY writes)
--
-- Does NOT:
--   - migrate month_key across plan/DP/passport tables
--   - auto-approve Crew_Register into this table
--   - modify monthly_plan_capacity_v1 (legacy/diagnostic preserved)
--   - enable RLS
-- =============================================================================

-- 1) Table
create table if not exists public.monthly_resource_plan_lines (
    resource_plan_line_id uuid primary key default gen_random_uuid(),

    project_code text not null,
    month_key text not null,  -- canonical YYYY-MM only for this table
    crew_code text not null,

    person_id text,
    person_name text not null,
    role text,

    effective_from date,
    effective_to date,

    planned_shift_hours numeric
        check (planned_shift_hours is null or planned_shift_hours >= 0),
    confirmed_available_hours numeric not null default 0
        check (confirmed_available_hours >= 0),

    resource_status text not null default 'DRAFT'
        check (resource_status in ('DRAFT', 'APPROVED', 'REJECTED')),

    approved_by text,
    approved_at timestamptz,

    source_airtable_record_id text,
    comment text,

    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),

    -- Date range: open-ended periods allowed; both set ⇒ ordered
    constraint monthly_resource_plan_lines_date_range_chk
        check (
            effective_to is null
            or effective_from is null
            or effective_to >= effective_from
        ),

    -- Canonical month key YYYY-MM
    constraint monthly_resource_plan_lines_month_key_chk
        check (month_key ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),

    -- APPROVED requires approval metadata; DRAFT/REJECTED do not
    constraint monthly_resource_plan_lines_approved_meta_chk
        check (
            resource_status <> 'APPROVED'
            or (
                approved_by is not null
                and btrim(approved_by) <> ''
                and approved_at is not null
            )
        )
);

comment on table public.monthly_resource_plan_lines is
    'R1.2 Monthly Resource Plan lines. APPROVED rows are SoT for future crew capacity.';

comment on column public.monthly_resource_plan_lines.month_key is
    'Canonical month key YYYY-MM (e.g. 2026-07). Not RU/EN text.';

comment on column public.monthly_resource_plan_lines.confirmed_available_hours is
    'Confirmed direct hours for this person assignment in the month. Only APPROVED counts.';

comment on column public.monthly_resource_plan_lines.resource_status is
    'DRAFT | APPROVED | REJECTED. Only APPROVED enters capacity.';

comment on column public.monthly_resource_plan_lines.source_airtable_record_id is
    'Optional link to Crew_Register / monthly_labor_summary.airtable_record_id. Prefill only.';

-- Anti-duplicate business key:
-- same person + same period cannot double-count.
-- Different periods for same person ARE allowed.
-- person_id nullable → coalesce empty string; null dates → sentinel.
create unique index if not exists idx_mrp_lines_business_key
    on public.monthly_resource_plan_lines (
        project_code,
        month_key,
        crew_code,
        (coalesce(nullif(btrim(person_id), ''), '')),
        person_name,
        (coalesce(effective_from, date '1900-01-01')),
        (coalesce(effective_to, date '9999-12-31'))
    );

create index if not exists idx_mrp_lines_scope
    on public.monthly_resource_plan_lines (project_code, month_key, crew_code);

create index if not exists idx_mrp_lines_scope_status
    on public.monthly_resource_plan_lines (project_code, month_key, crew_code, resource_status);

create index if not exists idx_mrp_lines_status
    on public.monthly_resource_plan_lines (resource_status);

create index if not exists idx_mrp_lines_source_airtable
    on public.monthly_resource_plan_lines (source_airtable_record_id)
    where source_airtable_record_id is not null;

-- 2) Aggregate capacity view (APPROVED only)
create or replace view public.monthly_resource_capacity_v1 as
select
    nullif(trim(l.project_code), '') as project_code,
    nullif(trim(l.month_key), '') as month_key,
    nullif(trim(l.crew_code), '') as crew_code,
    count(*)::bigint as approved_assignment_count,
    count(
        distinct coalesce(nullif(btrim(l.person_id), ''), l.person_name)
    )::bigint as approved_people_count,
    coalesce(sum(l.confirmed_available_hours), 0)::numeric as approved_available_hours,
    min(l.effective_from) as approved_from_min,
    max(l.effective_to) as approved_to_max,
    'APPROVED'::text as resource_plan_status
from public.monthly_resource_plan_lines l
where l.resource_status = 'APPROVED'
  and nullif(trim(l.project_code), '') is not null
  and nullif(trim(l.month_key), '') is not null
  and nullif(trim(l.crew_code), '') is not null
group by
    nullif(trim(l.project_code), ''),
    nullif(trim(l.month_key), ''),
    nullif(trim(l.crew_code), '');

comment on view public.monthly_resource_capacity_v1 is
    'R1.2 Approved monthly crew capacity. Grain: project + month(YYYY-MM) + crew. '
    'approved_people_count = unique people; approved_assignment_count = period lines; '
    'hours = SUM of APPROVED periods only.';

-- 3) Privileges (R1.2.1 — explicit named-role revoke + least privilege)
-- Writes via service_role / SUPABASE_SECRET_KEY only.
-- SELECT for rehydrate / Page22 / Page22B via anon key app pattern.
-- RLS not enabled in R1.2; gate = grants + service write client.
--
-- Root cause note (R1.2.1):
--   REVOKE ALL ... FROM public only clears the PUBLIC pseudo-role.
--   Supabase default privileges commonly GRANT write to anon/authenticated
--   at CREATE TABLE time; those must be revoked by role name.

revoke all on table public.monthly_resource_plan_lines from public;
revoke all on table public.monthly_resource_capacity_v1 from public;

revoke all on table public.monthly_resource_plan_lines
  from anon, authenticated;
revoke all on table public.monthly_resource_capacity_v1
  from anon, authenticated;

grant select on table public.monthly_resource_plan_lines
  to anon, authenticated, service_role;

grant select, insert, update, delete on table public.monthly_resource_plan_lines
  to service_role;

grant select on table public.monthly_resource_capacity_v1
  to anon, authenticated, service_role;

-- View: SELECT only (no write grants)
revoke insert, update, delete on table public.monthly_resource_capacity_v1
  from anon, authenticated, service_role, public;

-- 4) Smoke selects (manual)
-- select * from public.monthly_resource_plan_lines limit 5;
-- select * from public.monthly_resource_capacity_v1 limit 5;
