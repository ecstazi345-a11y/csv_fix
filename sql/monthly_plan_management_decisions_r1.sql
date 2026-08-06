-- =============================================================================
-- Monthly Plan Management Decisions R1 — durable War Room decisions
-- =============================================================================
-- File:    sql/monthly_plan_management_decisions_r1.sql
-- Deploy:  Supabase SQL Editor MANUALLY after review. Do NOT auto-run on prod.
-- Scope:   SQL contract only for this stage.
--          Does NOT change Page 23 / Python / session_state / passport RPC.
--          Does NOT modify replace_monthly_passport.
--
-- Adds:
--   public.monthly_plan_management_decisions
--   public.apply_monthly_plan_management_decision(...)
--   public.cancel_monthly_plan_management_decision(...)
--
-- Grain (active state):
--   one row per (project_code, month_key, plan_line_id)
--   = latest management decision for that plan line in the month.
--
-- Decision codes (DB):
--   INCLUDE | INCLUDE_RISK | EXCLUDE | DEFER
-- UI mapping (Page 23, next stage):
--   INCLUDE      ↔ «Включить в паспорт»
--   INCLUDE_RISK ↔ «Включить с риском»
--   EXCLUDE      ↔ «Исключить» / remove-from-draft
--   DEFER        ↔ «Отложить»
--
-- Status values (R1 minimal):
--   ACTIVE | CANCELLED
--
-- No FK to monthly_plan_lines_v2 in R1 (plan_line_id may be deleted by cleanups).
-- No event/audit table in R1 (add later if needed).
-- No automatic backfill from passport_lines.
-- Idempotent where possible (IF NOT EXISTS / CREATE OR REPLACE).
-- =============================================================================

-- 0) Preconditions
do $$
begin
  if to_regclass('public.monthly_plan_lines_v2') is null then
    raise exception
      'ABORT: public.monthly_plan_lines_v2 not found — apply v2 plan lines first';
  end if;
end $$;

-- 1) Canonical current-state table
create table if not exists public.monthly_plan_management_decisions (
    decision_id uuid primary key default gen_random_uuid(),

    project_code text not null,
    month_key text not null,
    plan_line_id uuid not null,

    -- Display cache (nullable; UI may re-join from read model)
    boq_code text,
    boq_name text,
    facility_building text,
    construction_discipline text,

    decision text not null,
    decision_status text not null default 'ACTIVE',

    -- Snapshot of live admission outcome at apply time (not live truth)
    admission_outcome_at_decision text,
    management_override boolean not null default false,

    -- Decision protocol (maps from wr2_build_decision_record)
    decision_basis text,
    decision_comment text,
    responsible_person text,
    review_deadline text,

    -- INCLUDE_RISK protocol (required to rehydrate risk inclusion rules)
    risk_description text,
    risk_impact text,
    risk_mitigation_owner text,
    risk_mitigation_deadline text,
    risk_acceptance_basis text,
    risk_manager_comment text,
    risk_blocker text,

    decided_by text not null,
    decided_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),

    source_page text not null default 'PAGE_23_WAR_ROOM',
    created_at timestamptz not null default now(),

    constraint monthly_plan_mgmt_decisions_decision_chk
        check (decision in ('INCLUDE', 'INCLUDE_RISK', 'EXCLUDE', 'DEFER')),

    constraint monthly_plan_mgmt_decisions_status_chk
        check (decision_status in ('ACTIVE', 'CANCELLED')),

    constraint monthly_plan_mgmt_decisions_source_chk
        check (source_page in ('PAGE_23_WAR_ROOM'))
);

-- Unique grain for upsert (one current row per plan line in month)
create unique index if not exists monthly_plan_mgmt_decisions_grain_uidx
    on public.monthly_plan_management_decisions (project_code, month_key, plan_line_id);

create index if not exists monthly_plan_mgmt_decisions_scope_status_idx
    on public.monthly_plan_management_decisions (project_code, month_key, decision_status);

create index if not exists monthly_plan_mgmt_decisions_plan_line_idx
    on public.monthly_plan_management_decisions (plan_line_id);

create index if not exists monthly_plan_mgmt_decisions_decision_idx
    on public.monthly_plan_management_decisions (decision)
    where decision_status = 'ACTIVE';

comment on table public.monthly_plan_management_decisions is
    'R1: durable current-state management decisions for War Room (Page 23). '
    'Grain: project_code + month_key + plan_line_id. Not passport composition.';

comment on column public.monthly_plan_management_decisions.decision is
    'INCLUDE | INCLUDE_RISK | EXCLUDE | DEFER. UI maps Russian labels on Page 23.';

comment on column public.monthly_plan_management_decisions.decision_status is
    'ACTIVE = current working decision; CANCELLED = cleared / voided. '
    'R1 does not use SUPERSEDED / CONSUMED_IN_PASSPORT.';

comment on column public.monthly_plan_management_decisions.admission_outcome_at_decision is
    'Admission outcome snapshot at apply time (e.g. Допущено / Заблокировано). '
    'Not live READY_WITH_RISK and not passport admission_status.';

comment on column public.monthly_plan_management_decisions.management_override is
    'True when INCLUDE_RISK applied over non-clean admission outcome. '
    'Distinct from passport_lines.management_override until passport form.';

comment on column public.monthly_plan_management_decisions.plan_line_id is
    'Logical link to monthly_plan_lines_v2.plan_line_id. No FK in R1.';

-- 2) updated_at helper (idempotent)
create or replace function public.set_monthly_plan_mgmt_decisions_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_monthly_plan_mgmt_decisions_updated_at
  on public.monthly_plan_management_decisions;

create trigger trg_monthly_plan_mgmt_decisions_updated_at
before update on public.monthly_plan_management_decisions
for each row
execute function public.set_monthly_plan_mgmt_decisions_updated_at();

-- 3) Apply / upsert RPC
-- Payload keys (all optional except where CHECK/business rules require):
--   boq_code, boq_name, facility_building, construction_discipline,
--   admission_outcome_at_decision, management_override,
--   decision_basis, decision_comment, responsible_person, review_deadline,
--   risk_description, risk_impact, risk_mitigation_owner, risk_mitigation_deadline,
--   risk_acceptance_basis, risk_manager_comment, risk_blocker,
--   source_page
create or replace function public.apply_monthly_plan_management_decision(
    p_project_code text,
    p_month_key text,
    p_plan_line_id uuid,
    p_decision text,
    p_decided_by text,
    p_payload jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_decision text := upper(trim(coalesce(p_decision, '')));
  v_by text := nullif(trim(coalesce(p_decided_by, '')), '');
  v_payload jsonb := coalesce(p_payload, '{}'::jsonb);
  v_now timestamptz := now();
  v_old public.monthly_plan_management_decisions%rowtype;
  v_row public.monthly_plan_management_decisions%rowtype;
  v_override boolean;
  v_basis text;
  v_comment text;
  v_responsible text;
  v_review_deadline text;
begin
  if nullif(trim(coalesce(p_project_code, '')), '') is null then
    raise exception 'apply_monthly_plan_management_decision: project_code is required';
  end if;
  if nullif(trim(coalesce(p_month_key, '')), '') is null then
    raise exception 'apply_monthly_plan_management_decision: month_key is required';
  end if;
  if p_plan_line_id is null then
    raise exception 'apply_monthly_plan_management_decision: plan_line_id is required';
  end if;
  if v_by is null then
    raise exception 'apply_monthly_plan_management_decision: decided_by is required';
  end if;
  if v_decision not in ('INCLUDE', 'INCLUDE_RISK', 'EXCLUDE', 'DEFER') then
    raise exception
      'apply_monthly_plan_management_decision: invalid decision=%', v_decision;
  end if;

  v_basis := nullif(trim(coalesce(v_payload->>'decision_basis', '')), '');
  v_comment := nullif(trim(coalesce(v_payload->>'decision_comment', '')), '');
  v_responsible := nullif(trim(coalesce(v_payload->>'responsible_person', '')), '');
  v_review_deadline := nullif(trim(coalesce(v_payload->>'review_deadline', '')), '');

  if v_decision in ('INCLUDE', 'INCLUDE_RISK', 'EXCLUDE', 'DEFER') then
    if v_basis is null then
      raise exception 'apply_monthly_plan_management_decision: decision_basis is required';
    end if;
    if v_responsible is null then
      raise exception 'apply_monthly_plan_management_decision: responsible_person is required';
    end if;
    if v_review_deadline is null then
      raise exception 'apply_monthly_plan_management_decision: review_deadline is required';
    end if;
    if v_comment is null then
      raise exception 'apply_monthly_plan_management_decision: decision_comment is required';
    end if;
  end if;

  if v_decision = 'INCLUDE_RISK' then
    if nullif(trim(coalesce(v_payload->>'risk_description', '')), '') is null then
      raise exception 'apply_monthly_plan_management_decision: risk_description is required';
    end if;
    if nullif(trim(coalesce(v_payload->>'risk_impact', '')), '') is null then
      raise exception 'apply_monthly_plan_management_decision: risk_impact is required';
    end if;
    if nullif(trim(coalesce(v_payload->>'risk_mitigation_owner', '')), '') is null then
      raise exception 'apply_monthly_plan_management_decision: risk_mitigation_owner is required';
    end if;
    if nullif(trim(coalesce(v_payload->>'risk_mitigation_deadline', '')), '') is null then
      raise exception 'apply_monthly_plan_management_decision: risk_mitigation_deadline is required';
    end if;
    if nullif(trim(coalesce(v_payload->>'risk_acceptance_basis', '')), '') is null then
      raise exception 'apply_monthly_plan_management_decision: risk_acceptance_basis is required';
    end if;
    if nullif(trim(coalesce(v_payload->>'risk_manager_comment', '')), '') is null then
      raise exception 'apply_monthly_plan_management_decision: risk_manager_comment is required';
    end if;
  end if;

  select * into v_old
  from public.monthly_plan_management_decisions d
  where d.project_code = trim(p_project_code)
    and d.month_key = trim(p_month_key)
    and d.plan_line_id = p_plan_line_id
  for update;

  -- INCLUDE_RISK always marks override; other decisions use payload/default false
  if v_decision = 'INCLUDE_RISK' then
    v_override := true;
  else
    v_override := coalesce((v_payload->>'management_override')::boolean, false);
  end if;

  insert into public.monthly_plan_management_decisions as t (
    project_code,
    month_key,
    plan_line_id,
    boq_code,
    boq_name,
    facility_building,
    construction_discipline,
    decision,
    decision_status,
    admission_outcome_at_decision,
    management_override,
    decision_basis,
    decision_comment,
    responsible_person,
    review_deadline,
    risk_description,
    risk_impact,
    risk_mitigation_owner,
    risk_mitigation_deadline,
    risk_acceptance_basis,
    risk_manager_comment,
    risk_blocker,
    decided_by,
    decided_at,
    updated_by,
    updated_at,
    source_page
  ) values (
    trim(p_project_code),
    trim(p_month_key),
    p_plan_line_id,
    nullif(trim(coalesce(v_payload->>'boq_code', '')), ''),
    nullif(trim(coalesce(v_payload->>'boq_name', '')), ''),
    nullif(trim(coalesce(v_payload->>'facility_building', '')), ''),
    nullif(trim(coalesce(v_payload->>'construction_discipline', '')), ''),
    v_decision,
    'ACTIVE',
    nullif(trim(coalesce(v_payload->>'admission_outcome_at_decision', '')), ''),
    v_override,
    v_basis,
    v_comment,
    v_responsible,
    v_review_deadline,
    nullif(trim(coalesce(v_payload->>'risk_description', '')), ''),
    nullif(trim(coalesce(v_payload->>'risk_impact', '')), ''),
    nullif(trim(coalesce(v_payload->>'risk_mitigation_owner', '')), ''),
    nullif(trim(coalesce(v_payload->>'risk_mitigation_deadline', '')), ''),
    nullif(trim(coalesce(v_payload->>'risk_acceptance_basis', '')), ''),
    nullif(trim(coalesce(v_payload->>'risk_manager_comment', '')), ''),
    nullif(trim(coalesce(v_payload->>'risk_blocker', '')), ''),
    v_by,
    v_now,
    v_by,
    v_now,
    coalesce(nullif(trim(coalesce(v_payload->>'source_page', '')), ''), 'PAGE_23_WAR_ROOM')
  )
  on conflict (project_code, month_key, plan_line_id)
  do update set
    boq_code = excluded.boq_code,
    boq_name = excluded.boq_name,
    facility_building = excluded.facility_building,
    construction_discipline = excluded.construction_discipline,
    decision = excluded.decision,
    decision_status = 'ACTIVE',
    admission_outcome_at_decision = excluded.admission_outcome_at_decision,
    management_override = excluded.management_override,
    decision_basis = excluded.decision_basis,
    decision_comment = excluded.decision_comment,
    responsible_person = excluded.responsible_person,
    review_deadline = excluded.review_deadline,
    risk_description = excluded.risk_description,
    risk_impact = excluded.risk_impact,
    risk_mitigation_owner = excluded.risk_mitigation_owner,
    risk_mitigation_deadline = excluded.risk_mitigation_deadline,
    risk_acceptance_basis = excluded.risk_acceptance_basis,
    risk_manager_comment = excluded.risk_manager_comment,
    risk_blocker = excluded.risk_blocker,
    decided_by = excluded.decided_by,
    decided_at = excluded.decided_at,
    updated_by = excluded.updated_by,
    updated_at = excluded.updated_at,
    source_page = excluded.source_page
  returning * into v_row;

  return jsonb_build_object(
    'status', case when v_old.decision_id is null then 'inserted' else 'updated' end,
    'decision_id', v_row.decision_id,
    'project_code', v_row.project_code,
    'month_key', v_row.month_key,
    'plan_line_id', v_row.plan_line_id,
    'old_decision', v_old.decision,
    'old_decision_status', v_old.decision_status,
    'new_decision', v_row.decision,
    'new_decision_status', v_row.decision_status,
    'decided_by', v_row.decided_by,
    'decided_at', v_row.decided_at
  );
end;
$$;

comment on function public.apply_monthly_plan_management_decision(text, text, uuid, text, text, jsonb) is
  'R1 upsert of War Room management decision for one plan_line_id in project+month. '
  'Replaces previous decision on the same grain; sets decision_status=ACTIVE.';

-- 4) Cancel RPC (clear from draft / void decision without deleting grain)
create or replace function public.cancel_monthly_plan_management_decision(
    p_project_code text,
    p_month_key text,
    p_plan_line_id uuid,
    p_cancelled_by text,
    p_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_by text := nullif(trim(coalesce(p_cancelled_by, '')), '');
  v_row public.monthly_plan_management_decisions%rowtype;
  v_reason text := nullif(trim(coalesce(p_reason, '')), '');
begin
  if nullif(trim(coalesce(p_project_code, '')), '') is null
     or nullif(trim(coalesce(p_month_key, '')), '') is null
     or p_plan_line_id is null
     or v_by is null then
    raise exception
      'cancel_monthly_plan_management_decision: project_code, month_key, plan_line_id, cancelled_by required';
  end if;

  select * into v_row
  from public.monthly_plan_management_decisions d
  where d.project_code = trim(p_project_code)
    and d.month_key = trim(p_month_key)
    and d.plan_line_id = p_plan_line_id
  for update;

  if v_row.decision_id is null then
    return jsonb_build_object(
      'status', 'not_found',
      'project_code', trim(p_project_code),
      'month_key', trim(p_month_key),
      'plan_line_id', p_plan_line_id
    );
  end if;

  if v_row.decision_status = 'CANCELLED' then
    return jsonb_build_object(
      'status', 'already_cancelled',
      'decision_id', v_row.decision_id,
      'project_code', v_row.project_code,
      'month_key', v_row.month_key,
      'plan_line_id', v_row.plan_line_id,
      'decision', v_row.decision,
      'decision_status', v_row.decision_status,
      'updated_by', v_row.updated_by,
      'updated_at', v_row.updated_at
    );
  end if;

  update public.monthly_plan_management_decisions d
  set
    decision_status = 'CANCELLED',
    updated_by = v_by,
    updated_at = now(),
    decision_comment = coalesce(v_reason, d.decision_comment)
  where d.decision_id = v_row.decision_id
  returning * into v_row;

  return jsonb_build_object(
    'status', 'cancelled',
    'decision_id', v_row.decision_id,
    'project_code', v_row.project_code,
    'month_key', v_row.month_key,
    'plan_line_id', v_row.plan_line_id,
    'decision', v_row.decision,
    'decision_status', v_row.decision_status,
    'updated_by', v_row.updated_by,
    'updated_at', v_row.updated_at
  );
end;
$$;

comment on function public.cancel_monthly_plan_management_decision(text, text, uuid, text, text) is
  'R1 soft-cancel of a management decision grain (decision_status=CANCELLED). '
  'Idempotent: already CANCELLED → status already_cancelled. Row is not deleted.';

-- 5) Privileges (R1 minimal-safe)
-- Writes go through SECURITY DEFINER RPCs only.
-- Direct INSERT/UPDATE revoked from anon/authenticated.
-- SELECT kept for rehydrate queries from Page 23 (anon key app pattern).
-- RLS not enabled in R1; gate = grants + RPC validation.

revoke all on function public.apply_monthly_plan_management_decision(text, text, uuid, text, text, jsonb)
  from public;
revoke all on function public.cancel_monthly_plan_management_decision(text, text, uuid, text, text)
  from public;
revoke all on table public.monthly_plan_management_decisions from public;

grant execute on function public.apply_monthly_plan_management_decision(text, text, uuid, text, text, jsonb)
  to anon, authenticated, service_role;

grant execute on function public.cancel_monthly_plan_management_decision(text, text, uuid, text, text)
  to anon, authenticated, service_role;

grant select on public.monthly_plan_management_decisions
  to anon, authenticated, service_role;

grant insert, update, delete on public.monthly_plan_management_decisions
  to service_role;
