-- =============================================================================
-- Monthly Plan Management Decisions R1.6 — additive commitment qty snapshots
-- =============================================================================
-- File:    sql/monthly_plan_management_decisions_r16_commitment_qty.sql
-- Deploy:  Supabase SQL Editor MANUALLY after review.
-- Scope:   Additive nullable columns + backward-compatible RPC payload keys.
--          Does NOT UPDATE existing rows.
--          Does NOT backfill planned_qty / commitment.
--          Does NOT change decision codes or status semantics.
--          Does NOT touch passport tables / replace_monthly_passport.
--
-- New payload keys (all optional; omit = leave existing qty columns unchanged):
--   requested_qty_snapshot
--   feasible_qty_snapshot
--   approved_commitment_qty
--   committed_work_value
--   committed_required_hours
--   committed_labor_cost
--
-- Old apply() without these keys MUST keep working and MUST NOT null out
-- previously saved commitment snapshots on later INCLUDE/EXCLUDE updates.
-- =============================================================================

do $$
begin
  if to_regclass('public.monthly_plan_management_decisions') is null then
    raise exception
      'ABORT: public.monthly_plan_management_decisions not found — apply R1 first';
  end if;
end $$;

alter table public.monthly_plan_management_decisions
    add column if not exists requested_qty_snapshot numeric,
    add column if not exists feasible_qty_snapshot numeric,
    add column if not exists approved_commitment_qty numeric,
    add column if not exists committed_work_value numeric,
    add column if not exists committed_required_hours numeric,
    add column if not exists committed_labor_cost numeric;

comment on column public.monthly_plan_management_decisions.requested_qty_snapshot is
    'R1.6 snapshot of monthly_plan_lines_v2.planned_qty at commitment save. NULL = not set.';
comment on column public.monthly_plan_management_decisions.feasible_qty_snapshot is
    'R1.6 snapshot of theoretical_feasible_qty at commitment save. NULL = not set.';
comment on column public.monthly_plan_management_decisions.approved_commitment_qty is
    'R1.6 human approved monthly obligation qty. NULL = composition only, qty not accepted.';
comment on column public.monthly_plan_management_decisions.committed_work_value is
    'R1.6 snapshot: commitment_qty × unit_price (or scaled plan_value).';
comment on column public.monthly_plan_management_decisions.committed_required_hours is
    'R1.6 snapshot: labor_hours × commitment_qty / requested_qty.';
comment on column public.monthly_plan_management_decisions.committed_labor_cost is
    'R1.6 snapshot: committed_required_hours × labor_rate_per_hour.';

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
  v_has_commitment boolean;
  v_requested_qty numeric;
  v_feasible_qty numeric;
  v_commitment_qty numeric;
  v_committed_value numeric;
  v_committed_hours numeric;
  v_committed_labor numeric;
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

  if v_comment in ('—', '-', '–') then
    v_comment := null;
  end if;
  if v_review_deadline in ('—', '-', '–') then
    v_review_deadline := null;
  end if;

  if v_decision in ('INCLUDE', 'INCLUDE_RISK', 'EXCLUDE', 'DEFER') then
    if v_basis is null then
      raise exception 'apply_monthly_plan_management_decision: decision_basis is required';
    end if;
    if v_responsible is null then
      raise exception 'apply_monthly_plan_management_decision: responsible_person is required';
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

  v_has_commitment := (v_payload ? 'approved_commitment_qty');
  if v_has_commitment then
    v_requested_qty := nullif(trim(coalesce(v_payload->>'requested_qty_snapshot', '')), '')::numeric;
    v_feasible_qty := nullif(trim(coalesce(v_payload->>'feasible_qty_snapshot', '')), '')::numeric;
    v_commitment_qty := nullif(trim(coalesce(v_payload->>'approved_commitment_qty', '')), '')::numeric;
    v_committed_value := nullif(trim(coalesce(v_payload->>'committed_work_value', '')), '')::numeric;
    v_committed_hours := nullif(trim(coalesce(v_payload->>'committed_required_hours', '')), '')::numeric;
    v_committed_labor := nullif(trim(coalesce(v_payload->>'committed_labor_cost', '')), '')::numeric;
  else
    v_requested_qty := null;
    v_feasible_qty := null;
    v_commitment_qty := null;
    v_committed_value := null;
    v_committed_hours := null;
    v_committed_labor := null;
  end if;

  select * into v_old
  from public.monthly_plan_management_decisions d
  where d.project_code = trim(p_project_code)
    and d.month_key = trim(p_month_key)
    and d.plan_line_id = p_plan_line_id
  for update;

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
    requested_qty_snapshot,
    feasible_qty_snapshot,
    approved_commitment_qty,
    committed_work_value,
    committed_required_hours,
    committed_labor_cost,
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
    v_requested_qty,
    v_feasible_qty,
    v_commitment_qty,
    v_committed_value,
    v_committed_hours,
    v_committed_labor,
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
    requested_qty_snapshot = case
      when v_has_commitment then excluded.requested_qty_snapshot
      else t.requested_qty_snapshot
    end,
    feasible_qty_snapshot = case
      when v_has_commitment then excluded.feasible_qty_snapshot
      else t.feasible_qty_snapshot
    end,
    approved_commitment_qty = case
      when v_has_commitment then excluded.approved_commitment_qty
      else t.approved_commitment_qty
    end,
    committed_work_value = case
      when v_has_commitment then excluded.committed_work_value
      else t.committed_work_value
    end,
    committed_required_hours = case
      when v_has_commitment then excluded.committed_required_hours
      else t.committed_required_hours
    end,
    committed_labor_cost = case
      when v_has_commitment then excluded.committed_labor_cost
      else t.committed_labor_cost
    end,
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
  'R1.6: War Room management decision upsert. Qty snapshot keys optional. '
  'Omitting approved_commitment_qty preserves existing commitment columns.';

revoke all on function public.apply_monthly_plan_management_decision(text, text, uuid, text, text, jsonb)
  from public;

grant execute on function public.apply_monthly_plan_management_decision(text, text, uuid, text, text, jsonb)
  to anon, authenticated, service_role;

notify pgrst, 'reload schema';
