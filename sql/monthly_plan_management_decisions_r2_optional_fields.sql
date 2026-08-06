-- =============================================================================
-- Monthly Plan Management Decisions R2 — optional review_deadline / comment
-- =============================================================================
-- File:    sql/monthly_plan_management_decisions_r2_optional_fields.sql
-- Deploy:  Schema/function changes ONLY. Use this file OR _DEPLOY.sql (identical).
--          Expected: Success. No rows returned.
-- Tests:   sql/tests/monthly_plan_management_decisions_r2_optional_fields_tests.sql
--          Run ONLY after successful deploy.
-- =============================================================================

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
  'R2: War Room management decision upsert. review_deadline and decision_comment optional. '
  'INCLUDE_RISK risk protocol remains required.';

revoke all on function public.apply_monthly_plan_management_decision(text, text, uuid, text, text, jsonb)
  from public;

grant execute on function public.apply_monthly_plan_management_decision(text, text, uuid, text, text, jsonb)
  to anon, authenticated, service_role;

notify pgrst, 'reload schema';
