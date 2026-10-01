-- =============================================================================
-- Labor Norm Decisions R1 — durable human provisional register
-- =============================================================================
-- File:    sql/labor_norm_decisions_r1.sql
-- Deploy:  Supabase SQL Editor MANUALLY after explicit human approval.
--          Do NOT auto-run on prod from the app.
--
-- Scope:   LND-R1 human decision register ONLY.
--          Does NOT change Daily Progress, productivity views, P50/P80,
--          LaborNormResolver, Constructor, Candidate Package, or Page53.
--
-- Adds:
--   public.labor_norm_decisions
--   public.apply_labor_norm_decision(...)
--   public.cancel_labor_norm_decision(...)
--
-- Grain (one ACTIVE row):
--   project_code + facility_building + construction_discipline + boq_code
--
-- Decision codes:
--   APPROVED_PROVISIONAL | MANUAL_PROVISIONAL | REJECTED
--
-- Status:
--   ACTIVE | CANCELLED
--
-- Replace semantics:
--   existing ACTIVE → CANCELLED (row retained)
--   new decision → INSERT ACTIVE
--   Partial unique index enforces at most one ACTIVE per grain.
--
-- Historical P50/P80 are UI hints only. This table NEVER stores VALIDATED.
-- Idempotent where possible (IF NOT EXISTS / CREATE OR REPLACE).
-- =============================================================================

create table if not exists public.labor_norm_decisions (
    decision_id uuid primary key default gen_random_uuid(),

    project_code text not null,
    facility_building text not null,
    construction_discipline text not null,
    boq_code text not null,
    boq_name text,
    unit_of_measure text not null,

    suggested_norm numeric,
    suggested_source text,
    sample_count bigint,
    confidence text,

    decision text not null,
    decision_status text not null default 'ACTIVE',

    approved_norm numeric,
    comment text,
    source_reference text,

    approved_by text not null,
    approved_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    cancelled_by text,
    cancelled_at timestamptz,

    source_page text not null default 'PAGE_13_LABOR_NORM_DECISION',
    created_at timestamptz not null default now(),

    constraint labor_norm_decisions_decision_chk
        check (decision in (
            'APPROVED_PROVISIONAL',
            'MANUAL_PROVISIONAL',
            'REJECTED'
        )),

    constraint labor_norm_decisions_status_chk
        check (decision_status in ('ACTIVE', 'CANCELLED')),

    constraint labor_norm_decisions_source_page_chk
        check (source_page in ('PAGE_13_LABOR_NORM_DECISION')),

    constraint labor_norm_decisions_approved_norm_chk
        check (
            (
                decision in ('APPROVED_PROVISIONAL', 'MANUAL_PROVISIONAL')
                and approved_norm is not null
                and approved_norm > 0
            )
            or (
                decision = 'REJECTED'
                and approved_norm is null
            )
        )
);

-- At most one ACTIVE decision per grain; CANCELLED history retained.
create unique index if not exists labor_norm_decisions_active_grain_uidx
    on public.labor_norm_decisions (
        project_code,
        facility_building,
        construction_discipline,
        boq_code
    )
    where decision_status = 'ACTIVE';

create index if not exists labor_norm_decisions_scope_status_idx
    on public.labor_norm_decisions (
        project_code,
        facility_building,
        construction_discipline,
        decision_status
    );

create index if not exists labor_norm_decisions_boq_idx
    on public.labor_norm_decisions (boq_code);

comment on table public.labor_norm_decisions is
    'LND-R1: durable human labor-norm decisions. '
    'ACTIVE grain = project + facility + discipline + boq. '
    'Never VALIDATED. Historical P50/P80 are hints only.';

comment on column public.labor_norm_decisions.decision is
    'APPROVED_PROVISIONAL | MANUAL_PROVISIONAL | REJECTED. Never VALIDATED.';

comment on column public.labor_norm_decisions.suggested_norm is
    'Optional historical hint snapshot (e.g. P50). Not authoritative.';

comment on column public.labor_norm_decisions.approved_norm is
    'Human-approved provisional planning norm (чел·ч / unit). Null when REJECTED.';

-- updated_at helper
create or replace function public.set_labor_norm_decisions_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_labor_norm_decisions_updated_at
  on public.labor_norm_decisions;

create trigger trg_labor_norm_decisions_updated_at
before update on public.labor_norm_decisions
for each row
execute function public.set_labor_norm_decisions_updated_at();

-- Apply: cancel previous ACTIVE + insert new ACTIVE (history-preserving)
create or replace function public.apply_labor_norm_decision(
    p_project_code text,
    p_facility_building text,
    p_construction_discipline text,
    p_boq_code text,
    p_unit_of_measure text,
    p_decision text,
    p_approved_by text,
    p_payload jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_project text := nullif(trim(coalesce(p_project_code, '')), '');
  v_facility text := nullif(trim(coalesce(p_facility_building, '')), '');
  v_discipline text := nullif(trim(coalesce(p_construction_discipline, '')), '');
  v_boq text := nullif(upper(trim(coalesce(p_boq_code, ''))), '');
  v_unit text := nullif(trim(coalesce(p_unit_of_measure, '')), '');
  v_decision text := upper(trim(coalesce(p_decision, '')));
  v_by text := nullif(trim(coalesce(p_approved_by, '')), '');
  v_payload jsonb := coalesce(p_payload, '{}'::jsonb);
  v_now timestamptz := now();
  v_comment text;
  v_approved_norm numeric;
  v_old public.labor_norm_decisions%rowtype;
  v_row public.labor_norm_decisions%rowtype;
  v_cancelled_id uuid;
begin
  if v_project is null then
    raise exception 'apply_labor_norm_decision: project_code is required';
  end if;
  if v_facility is null then
    raise exception 'apply_labor_norm_decision: facility_building is required';
  end if;
  if v_discipline is null then
    raise exception 'apply_labor_norm_decision: construction_discipline is required';
  end if;
  if v_boq is null then
    raise exception 'apply_labor_norm_decision: boq_code is required';
  end if;
  if v_unit is null then
    raise exception 'apply_labor_norm_decision: unit_of_measure is required';
  end if;
  if v_by is null then
    raise exception 'apply_labor_norm_decision: approved_by is required';
  end if;
  if v_decision not in ('APPROVED_PROVISIONAL', 'MANUAL_PROVISIONAL', 'REJECTED') then
    raise exception 'apply_labor_norm_decision: invalid decision=%', v_decision;
  end if;

  v_comment := nullif(trim(coalesce(v_payload->>'comment', '')), '');
  if v_comment is null then
    raise exception 'apply_labor_norm_decision: comment is required';
  end if;

  if v_decision in ('APPROVED_PROVISIONAL', 'MANUAL_PROVISIONAL') then
    begin
      v_approved_norm := nullif(trim(coalesce(v_payload->>'approved_norm', '')), '')::numeric;
    exception when others then
      raise exception 'apply_labor_norm_decision: approved_norm must be numeric';
    end;
    if v_approved_norm is null or v_approved_norm <= 0 then
      raise exception
        'apply_labor_norm_decision: approved_norm must be finite and > 0';
    end if;
  else
    v_approved_norm := null;
  end if;

  -- Cancel any current ACTIVE for the grain (retain history)
  update public.labor_norm_decisions d
  set
    decision_status = 'CANCELLED',
    cancelled_by = v_by,
    cancelled_at = v_now,
    updated_by = v_by,
    updated_at = v_now
  where d.project_code = v_project
    and d.facility_building = v_facility
    and d.construction_discipline = v_discipline
    and d.boq_code = v_boq
    and d.decision_status = 'ACTIVE'
  returning d.decision_id into v_cancelled_id;

  if v_cancelled_id is not null then
    select * into v_old
    from public.labor_norm_decisions
    where decision_id = v_cancelled_id;
  end if;

  insert into public.labor_norm_decisions (
    project_code,
    facility_building,
    construction_discipline,
    boq_code,
    boq_name,
    unit_of_measure,
    suggested_norm,
    suggested_source,
    sample_count,
    confidence,
    decision,
    decision_status,
    approved_norm,
    comment,
    source_reference,
    approved_by,
    approved_at,
    updated_by,
    updated_at,
    source_page
  ) values (
    v_project,
    v_facility,
    v_discipline,
    v_boq,
    nullif(trim(coalesce(v_payload->>'boq_name', '')), ''),
    v_unit,
    case
      when nullif(trim(coalesce(v_payload->>'suggested_norm', '')), '') is null then null
      else (v_payload->>'suggested_norm')::numeric
    end,
    nullif(trim(coalesce(v_payload->>'suggested_source', '')), ''),
    case
      when nullif(trim(coalesce(v_payload->>'sample_count', '')), '') is null then null
      else (v_payload->>'sample_count')::bigint
    end,
    nullif(trim(coalesce(v_payload->>'confidence', '')), ''),
    v_decision,
    'ACTIVE',
    v_approved_norm,
    v_comment,
    nullif(trim(coalesce(v_payload->>'source_reference', '')), ''),
    v_by,
    v_now,
    v_by,
    v_now,
    coalesce(
      nullif(trim(coalesce(v_payload->>'source_page', '')), ''),
      'PAGE_13_LABOR_NORM_DECISION'
    )
  )
  returning * into v_row;

  return jsonb_build_object(
    'status', case when v_cancelled_id is null then 'inserted' else 'replaced' end,
    'decision_id', v_row.decision_id,
    'cancelled_decision_id', v_cancelled_id,
    'project_code', v_row.project_code,
    'facility_building', v_row.facility_building,
    'construction_discipline', v_row.construction_discipline,
    'boq_code', v_row.boq_code,
    'unit_of_measure', v_row.unit_of_measure,
    'decision', v_row.decision,
    'decision_status', v_row.decision_status,
    'approved_norm', v_row.approved_norm,
    'approved_by', v_row.approved_by,
    'approved_at', v_row.approved_at
  );
end;
$$;

comment on function public.apply_labor_norm_decision(text, text, text, text, text, text, text, jsonb) is
  'LND-R1: cancel prior ACTIVE labor-norm decision for grain, insert new ACTIVE. '
  'Never VALIDATED. History-preserving replace.';

-- Soft-cancel ACTIVE without inserting a replacement
create or replace function public.cancel_labor_norm_decision(
    p_project_code text,
    p_facility_building text,
    p_construction_discipline text,
    p_boq_code text,
    p_cancelled_by text,
    p_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_project text := nullif(trim(coalesce(p_project_code, '')), '');
  v_facility text := nullif(trim(coalesce(p_facility_building, '')), '');
  v_discipline text := nullif(trim(coalesce(p_construction_discipline, '')), '');
  v_boq text := nullif(upper(trim(coalesce(p_boq_code, ''))), '');
  v_by text := nullif(trim(coalesce(p_cancelled_by, '')), '');
  v_reason text := nullif(trim(coalesce(p_reason, '')), '');
  v_row public.labor_norm_decisions%rowtype;
begin
  if v_project is null or v_facility is null or v_discipline is null or v_boq is null then
    raise exception 'cancel_labor_norm_decision: grain fields are required';
  end if;
  if v_by is null then
    raise exception 'cancel_labor_norm_decision: cancelled_by is required';
  end if;

  select * into v_row
  from public.labor_norm_decisions d
  where d.project_code = v_project
    and d.facility_building = v_facility
    and d.construction_discipline = v_discipline
    and d.boq_code = v_boq
    and d.decision_status = 'ACTIVE'
  for update;

  if not found then
    return jsonb_build_object(
      'status', 'not_found',
      'project_code', v_project,
      'facility_building', v_facility,
      'construction_discipline', v_discipline,
      'boq_code', v_boq
    );
  end if;

  update public.labor_norm_decisions d
  set
    decision_status = 'CANCELLED',
    cancelled_by = v_by,
    cancelled_at = now(),
    updated_by = v_by,
    updated_at = now(),
    comment = coalesce(v_reason, d.comment)
  where d.decision_id = v_row.decision_id
  returning * into v_row;

  return jsonb_build_object(
    'status', 'cancelled',
    'decision_id', v_row.decision_id,
    'decision', v_row.decision,
    'decision_status', v_row.decision_status,
    'cancelled_by', v_row.cancelled_by,
    'cancelled_at', v_row.cancelled_at
  );
end;
$$;

comment on function public.cancel_labor_norm_decision(text, text, text, text, text, text) is
  'LND-R1 soft-cancel of ACTIVE labor-norm decision for grain. Row retained.';

-- Privileges (R1 security lockdown):
-- writes/reads ONLY via service_role calling SECURITY DEFINER RPCs / table.
-- anon and authenticated must not SELECT or EXECUTE (public anon key exposure).
revoke all on function public.apply_labor_norm_decision(text, text, text, text, text, text, text, jsonb)
  from public, anon, authenticated;
revoke all on function public.cancel_labor_norm_decision(text, text, text, text, text, text)
  from public, anon, authenticated;
revoke all on table public.labor_norm_decisions
  from public, anon, authenticated;

grant execute on function public.apply_labor_norm_decision(text, text, text, text, text, text, text, jsonb)
  to service_role;

grant execute on function public.cancel_labor_norm_decision(text, text, text, text, text, text)
  to service_role;

grant select, insert, update, delete on public.labor_norm_decisions
  to service_role;

-- RLS note (R1): deferred — table/RPC accessible only to service_role
-- (Streamlit server with SUPABASE_SECRET_KEY). No anon surface.
-- Project-scoped RLS + Auth identity remain a later increment.
-- approved_by is a free-text operator label, not cryptographic identity.
