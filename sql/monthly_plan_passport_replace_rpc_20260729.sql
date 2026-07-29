-- =============================================================================
-- Monthly Plan Passport — atomic replace / rebuild (Release 1)
-- =============================================================================
-- Function: public.replace_monthly_passport
-- Tables:   public.monthly_plan_passports
--           public.monthly_plan_passport_lines
--
-- Purpose: one transactional create-or-rebuild for (project_code, month_key).
-- Deploy:  Supabase SQL Editor (manual). Do not run against prod without review.
-- Service: services/monthly_passport_service.py
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1) Partial unique: at most one active passport per project + month
--    Pre-check: no duplicates for statuses NOT IN (SUPERSEDED, CANCELLED).
-- -----------------------------------------------------------------------------

do $$
declare
  v_dup_count int;
begin
  select count(*) into v_dup_count
  from (
    select project_code, month_key
    from public.monthly_plan_passports
    where passport_status not in ('SUPERSEDED', 'CANCELLED')
      and project_code is not null
      and month_key is not null
    group by project_code, month_key
    having count(*) > 1
  ) d;

  if v_dup_count > 0 then
    raise exception
      'ABORT: found % active duplicate (project_code, month_key) group(s); resolve before unique index',
      v_dup_count;
  end if;
end $$;

create unique index if not exists monthly_plan_passports_active_project_month_uidx
  on public.monthly_plan_passports (project_code, month_key)
  where passport_status not in ('SUPERSEDED', 'CANCELLED')
    and project_code is not null
    and month_key is not null;

comment on index public.monthly_plan_passports_active_project_month_uidx is
  'At most one active (non-SUPERSEDED/CANCELLED) passport per project_code + month_key.';

-- -----------------------------------------------------------------------------
-- 2) Atomic RPC
-- -----------------------------------------------------------------------------

create or replace function public.replace_monthly_passport(
  p_project_code text,
  p_month_key text,
  p_draft_id uuid,
  p_created_by text,
  p_lines jsonb,
  p_header_totals jsonb,
  p_expected_rows integer
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_line_count integer;
  v_passport_id uuid;
  v_status text;
  v_previous_rows integer := 0;
  v_current_rows integer := 0;
  v_active_passport_ids uuid[];
  v_previous_line_ids uuid[];
  v_new_line_ids uuid[];
  v_added integer := 0;
  v_removed integer := 0;
  v_updated integer := 0;
  v_now timestamptz := now();
  v_passport_name text;
  v_total_plan_value numeric;
  v_total_required_hours numeric;
  v_total_labor_cost numeric;
  v_admission_summary jsonb;
  v_actual_rows integer;
begin
  if p_project_code is null or btrim(p_project_code) = '' then
    raise exception 'replace_monthly_passport: p_project_code is required';
  end if;
  if p_month_key is null or btrim(p_month_key) = '' then
    raise exception 'replace_monthly_passport: p_month_key is required';
  end if;
  if p_lines is null or jsonb_typeof(p_lines) <> 'array' then
    raise exception 'replace_monthly_passport: p_lines must be a JSON array';
  end if;
  if p_expected_rows is null or p_expected_rows < 1 then
    raise exception 'replace_monthly_passport: p_expected_rows must be >= 1';
  end if;

  v_line_count := jsonb_array_length(p_lines);
  if v_line_count <> p_expected_rows then
    raise exception
      'replace_monthly_passport: jsonb_array_length(p_lines)=% <> p_expected_rows=%',
      v_line_count, p_expected_rows;
  end if;

  -- Required keys + project/month consistency (defense in depth; Python also validates)
  if exists (
    select 1
    from jsonb_array_elements(p_lines) as elem
    where coalesce(elem->>'line_id', '') = ''
       or coalesce(elem->>'boq_code', '') = ''
       or (
            elem ? 'project_code'
            and nullif(btrim(elem->>'project_code'), '') is not null
            and elem->>'project_code' is distinct from p_project_code
          )
       or (
            elem ? 'month_key'
            and nullif(btrim(elem->>'month_key'), '') is not null
            and elem->>'month_key' is distinct from p_month_key
          )
  ) then
    raise exception
      'replace_monthly_passport: each line requires line_id and boq_code; project/month must match args when present';
  end if;

  -- Duplicate source line_id in payload
  if exists (
    select 1
    from (
      select elem->>'line_id' as lid
      from jsonb_array_elements(p_lines) as elem
      group by 1
      having count(*) > 1
    ) d
  ) then
    raise exception 'replace_monthly_passport: duplicate line_id in p_lines';
  end if;

  -- Exactly one active passport, or none.
  -- Release 1: APPROVED is used as ACTIVE WORKING PASSPORT (rebuildable).
  -- Final CLOSE/LOCK status will be added later; do not treat APPROVED as immutable.
  select array_agg(passport_id)
  into v_active_passport_ids
  from public.monthly_plan_passports
  where project_code = p_project_code
    and month_key = p_month_key
    and passport_status not in ('SUPERSEDED', 'CANCELLED');

  if v_active_passport_ids is not null and cardinality(v_active_passport_ids) > 1 then
    raise exception
      'replace_monthly_passport: % active passports for % / %; resolve duplicates first',
      cardinality(v_active_passport_ids), p_project_code, p_month_key;
  end if;

  v_passport_name := coalesce(
    nullif(p_header_totals->>'passport_name', ''),
    format('Monthly Plan Passport | %s | %s', p_project_code, p_month_key)
  );
  v_total_plan_value := coalesce((p_header_totals->>'total_plan_value')::numeric, 0);
  v_total_required_hours := coalesce((p_header_totals->>'total_required_hours')::numeric, 0);
  v_total_labor_cost := coalesce((p_header_totals->>'total_labor_cost')::numeric, 0);
  v_admission_summary := case
    when p_header_totals ? 'admission_summary'
      then p_header_totals->'admission_summary'
    else null
  end;

  if v_active_passport_ids is null or cardinality(v_active_passport_ids) = 0 then
    v_status := 'created';
    v_previous_rows := 0;
    v_previous_line_ids := array[]::uuid[];

    insert into public.monthly_plan_passports (
      draft_id,
      project_code,
      month_key,
      passport_status,
      passport_name,
      created_by,
      approved_by,
      approved_at,
      total_plan_value,
      total_required_hours,
      total_labor_cost,
      rows_count,
      admission_summary,
      updated_at
    ) values (
      p_draft_id,
      p_project_code,
      p_month_key,
      'APPROVED',
      v_passport_name,
      coalesce(nullif(p_created_by, ''), 'Пользователь Streamlit'),
      coalesce(nullif(p_created_by, ''), 'Пользователь Streamlit'),
      v_now,
      v_total_plan_value,
      v_total_required_hours,
      v_total_labor_cost,
      p_expected_rows,
      v_admission_summary,
      v_now
    )
    returning passport_id into v_passport_id;
  else
    v_status := 'rebuilt';
    v_passport_id := v_active_passport_ids[1];

    select count(*)::integer
    into v_previous_rows
    from public.monthly_plan_passport_lines
    where passport_id = v_passport_id;

    select coalesce(array_agg(line_id), array[]::uuid[])
    into v_previous_line_ids
    from public.monthly_plan_passport_lines
    where passport_id = v_passport_id
      and line_id is not null;

    delete from public.monthly_plan_passport_lines
    where passport_id = v_passport_id;

    update public.monthly_plan_passports
    set
      draft_id = coalesce(p_draft_id, draft_id),
      passport_status = 'APPROVED',
      passport_name = v_passport_name,
      approved_by = coalesce(nullif(p_created_by, ''), approved_by),
      approved_at = v_now,
      total_plan_value = v_total_plan_value,
      total_required_hours = v_total_required_hours,
      total_labor_cost = v_total_labor_cost,
      rows_count = p_expected_rows,
      admission_summary = v_admission_summary,
      updated_at = v_now
    where passport_id = v_passport_id;
  end if;

  insert into public.monthly_plan_passport_lines (
    passport_id,
    draft_id,
    line_id,
    review_id,
    project_code,
    month_key,
    facility_building,
    construction_discipline,
    boq_code,
    boq_name,
    unit_of_measure,
    crew_id,
    planned_qty,
    unit_price,
    plan_value,
    required_hours,
    labor_rate_per_hour,
    labor_cost,
    admission_status,
    constraints_total,
    constraints_pass,
    constraints_warning,
    constraints_hold,
    constraints_fail,
    week_plan_status,
    comment,
    management_override,
    override_by,
    override_at,
    override_reason,
    override_risk_comment,
    override_basis,
    updated_at
  )
  select
    v_passport_id,
    nullif(elem->>'draft_id', '')::uuid,
    nullif(elem->>'line_id', '')::uuid,
    nullif(elem->>'review_id', '')::uuid,
    coalesce(nullif(elem->>'project_code', ''), p_project_code),
    coalesce(nullif(elem->>'month_key', ''), p_month_key),
    elem->>'facility_building',
    elem->>'construction_discipline',
    elem->>'boq_code',
    elem->>'boq_name',
    elem->>'unit_of_measure',
    elem->>'crew_id',
    nullif(elem->>'planned_qty', '')::numeric,
    nullif(elem->>'unit_price', '')::numeric,
    nullif(elem->>'plan_value', '')::numeric,
    nullif(elem->>'required_hours', '')::numeric,
    nullif(elem->>'labor_rate_per_hour', '')::numeric,
    nullif(elem->>'labor_cost', '')::numeric,
    elem->>'admission_status',
    coalesce(nullif(elem->>'constraints_total', '')::integer, 0),
    coalesce(nullif(elem->>'constraints_pass', '')::integer, 0),
    coalesce(nullif(elem->>'constraints_warning', '')::integer, 0),
    coalesce(nullif(elem->>'constraints_hold', '')::integer, 0),
    coalesce(nullif(elem->>'constraints_fail', '')::integer, 0),
    coalesce(nullif(elem->>'week_plan_status', ''), 'NOT_DECOMPOSED'),
    elem->>'comment',
    coalesce((elem->>'management_override')::boolean, false),
    elem->>'override_by',
    nullif(elem->>'override_at', '')::timestamptz,
    elem->>'override_reason',
    elem->>'override_risk_comment',
    elem->>'override_basis',
    v_now
  from jsonb_array_elements(p_lines) as elem;

  select count(*)::integer
  into v_actual_rows
  from public.monthly_plan_passport_lines
  where passport_id = v_passport_id;

  if v_actual_rows <> p_expected_rows then
    raise exception
      'replace_monthly_passport: inserted rows=% <> p_expected_rows=%',
      v_actual_rows, p_expected_rows;
  end if;

  -- Keep header rows_count aligned (already set; re-assert)
  update public.monthly_plan_passports
  set rows_count = v_actual_rows,
      updated_at = v_now
  where passport_id = v_passport_id;

  v_current_rows := v_actual_rows;

  select coalesce(array_agg((elem->>'line_id')::uuid), array[]::uuid[])
  into v_new_line_ids
  from jsonb_array_elements(p_lines) as elem
  where nullif(elem->>'line_id', '') is not null;

  if v_status = 'created' then
    v_added := v_current_rows;
    v_removed := 0;
    v_updated := 0;
  else
    select
      (
        select count(*)
        from unnest(v_new_line_ids) n(id)
        where n.id is not null
          and not (n.id = any (coalesce(v_previous_line_ids, array[]::uuid[])))
      ),
      (
        select count(*)
        from unnest(coalesce(v_previous_line_ids, array[]::uuid[])) o(id)
        where o.id is not null
          and not (o.id = any (v_new_line_ids))
      ),
      (
        select count(*)
        from unnest(v_new_line_ids) n(id)
        where n.id is not null
          and n.id = any (coalesce(v_previous_line_ids, array[]::uuid[]))
      )
    into v_added, v_removed, v_updated;
  end if;

  return jsonb_build_object(
    'status', v_status,
    'passport_id', v_passport_id,
    'previous_rows', v_previous_rows,
    'current_rows', v_current_rows,
    'added_count', v_added,
    'removed_count', v_removed,
    'updated_count', v_updated
  );
end;
$$;

comment on function public.replace_monthly_passport(text, text, uuid, text, jsonb, jsonb, integer) is
  'Atomic create-or-rebuild of monthly_plan_passports + lines for one project/month.';

revoke all on function public.replace_monthly_passport(text, text, uuid, text, jsonb, jsonb, integer)
  from public;

grant execute on function public.replace_monthly_passport(text, text, uuid, text, jsonb, jsonb, integer)
  to service_role;

grant execute on function public.replace_monthly_passport(text, text, uuid, text, jsonb, jsonb, integer)
  to authenticated;
