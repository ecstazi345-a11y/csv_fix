-- Monthly Plan Constraint Registry R1 — columns + audit + resolve RPC
-- File:    sql/monthly_plan_constraint_registry_r1.sql
-- Depends: public.monthly_plan_constraints (v1+v2)
--          public.monthly_plan_constraints_dashboard_v2 (evidence_v1)
-- Deploy:  Supabase SQL Editor MANUALLY after review. Do NOT auto-run on prod.
-- Scope:   Stage 1 only — no Streamlit page, no page 21/23, no passport changes.
--
-- Adds:
--   monthly_plan_constraints.actual_resolution_date
--   monthly_plan_constraints.required_action
--   monthly_plan_constraints.problem_owner
--   public.monthly_plan_constraint_events
--   public.resolve_monthly_plan_constraint(...)
--
-- Idempotent where possible (IF NOT EXISTS / CREATE OR REPLACE).
-- Does NOT insert into monthly_plan_constraint_evidence (payload → events only).
-- Does NOT touch monthly_plan_passports / passport_lines / replace_monthly_passport.

-- 0) Preconditions
do $$
begin
  if to_regclass('public.monthly_plan_constraints') is null then
    raise exception
      'ABORT: public.monthly_plan_constraints not found — apply constraints v1/v2 first';
  end if;
end $$;

-- 1) New nullable columns on monthly_plan_constraints
alter table public.monthly_plan_constraints
  add column if not exists actual_resolution_date date;

alter table public.monthly_plan_constraints
  add column if not exists required_action text;

alter table public.monthly_plan_constraints
  add column if not exists problem_owner text;

comment on column public.monthly_plan_constraints.actual_resolution_date is
  'Фактическая бизнес-дата устранения причины ограничения. Не заменяет технический resolved_at.';

comment on column public.monthly_plan_constraints.required_action is
  'Конкретное действие, необходимое для снятия ограничения.';

comment on column public.monthly_plan_constraints.problem_owner is
  'Сторона, породившая или контролирующая причину ограничения (Заказчик, Генподрядчик, Проектировщик, Поставщик, Субподрядчик и т.д.). Не путать с owner_name (исполнитель отработки).';

-- 2) Refresh dashboard views after new table columns.
-- CRITICAL: do NOT use SELECT c.* with CREATE OR REPLACE VIEW.
-- After ALTER TABLE adds columns, c.* shifts positions and PostgreSQL
-- tries to rename existing view columns (e.g. days_open -> actual_resolution_date).
-- Safe approach: DROP VIEW + CREATE VIEW with an explicit column list.
-- Order: pre-R1 table columns (stable) -> R1 columns -> computed columns.
-- No CASCADE (no known SQL dependents; app reads views by name).

drop view if exists public.monthly_plan_constraints_dashboard_v1;

create view public.monthly_plan_constraints_dashboard_v1 as
select
    c.constraint_id,
    c.created_at,
    c.updated_at,
    c.draft_id,
    c.line_id,
    c.review_id,
    c.project_code,
    c.month_key,
    c.facility_building,
    c.construction_discipline,
    c.boq_code,
    c.boq_name,
    c.crew_id,
    c.gate_layer,
    c.responsible_department,
    c.check_name,
    c.check_status,
    c.block_reason,
    c.owner_name,
    c.due_date,
    c.resolution_status,
    c.comment,
    c.plan_value,
    c.required_hours,
    c.constraint_created_at,
    c.created_by,
    c.created_role,
    c.owner_role,
    c.owner_department,
    c.target_resolution_date,
    c.resolved_at,
    c.resolved_by,
    c.severity,
    c.constraint_category,
    c.root_cause,
    c.value_at_risk,
    c.last_comment_at,
    c.updated_by,
    c.updated_role,
    c.last_action_at,
    c.actual_resolution_date,
    c.required_action,
    c.problem_owner,
    case
        when c.resolved_at is null then
            (current_date - coalesce(c.constraint_created_at, c.created_at)::date)::integer
        else
            (c.resolved_at::date - coalesce(c.constraint_created_at, c.created_at)::date)::integer
    end as days_open,
    case
        when c.resolution_status not in ('RESOLVED', 'CANCELLED')
            and c.target_resolution_date is not null
            and c.target_resolution_date < current_date
        then (current_date - c.target_resolution_date)::integer
        else 0
    end as days_overdue,
    (
        c.resolution_status not in ('RESOLVED', 'CANCELLED')
        and c.target_resolution_date is not null
        and c.target_resolution_date < current_date
    ) as is_overdue
from public.monthly_plan_constraints c;

comment on view public.monthly_plan_constraints_dashboard_v1 is
  'Дашборд ограничений v1: lifecycle days_open / days_overdue / is_overdue + registry R1 columns.';

do $$
begin
  if to_regclass('public.monthly_plan_constraint_evidence') is null then
    raise notice
      'monthly_plan_constraint_evidence missing — skip dashboard_v2 refresh';
    return;
  end if;

  execute 'drop view if exists public.monthly_plan_constraints_dashboard_v2';

  execute $view$
    create view public.monthly_plan_constraints_dashboard_v2 as
    with evidence_promise as (
        select
            e.constraint_id,
            coalesce(
                max(e.promised_date) filter (
                    where e.is_key_evidence and e.promised_date is not null
                ),
                max(e.promised_date) filter (where e.promised_date is not null)
            ) as effective_promised_date,
            count(*)::bigint as evidence_count
        from public.monthly_plan_constraint_evidence e
        group by e.constraint_id
    )
    select
        c.constraint_id,
        c.created_at,
        c.updated_at,
        c.draft_id,
        c.line_id,
        c.review_id,
        c.project_code,
        c.month_key,
        c.facility_building,
        c.construction_discipline,
        c.boq_code,
        c.boq_name,
        c.crew_id,
        c.gate_layer,
        c.responsible_department,
        c.check_name,
        c.check_status,
        c.block_reason,
        c.owner_name,
        c.due_date,
        c.resolution_status,
        c.comment,
        c.plan_value,
        c.required_hours,
        c.constraint_created_at,
        c.created_by,
        c.created_role,
        c.owner_role,
        c.owner_department,
        c.target_resolution_date,
        c.resolved_at,
        c.resolved_by,
        c.severity,
        c.constraint_category,
        c.root_cause,
        c.value_at_risk,
        c.last_comment_at,
        c.updated_by,
        c.updated_role,
        c.last_action_at,
        c.actual_resolution_date,
        c.required_action,
        c.problem_owner,
        ep.effective_promised_date,
        ep.evidence_count,
        case
            when c.resolution_status not in ('RESOLVED', 'CANCELLED')
                and ep.effective_promised_date is not null
                and ep.effective_promised_date < current_date
            then (current_date - ep.effective_promised_date)::integer
            else 0
        end as days_since_promise,
        (
            c.resolution_status not in ('RESOLVED', 'CANCELLED')
            and ep.effective_promised_date is not null
            and ep.effective_promised_date < current_date
        ) as is_promise_overdue
    from public.monthly_plan_constraints c
    left join evidence_promise ep
        on ep.constraint_id = c.constraint_id
  $view$;

  execute $c$
    comment on view public.monthly_plan_constraints_dashboard_v2 is
      'Дашборд ограничений v2: promise/evidence + registry R1 columns (actual_resolution_date, required_action, problem_owner).'
  $c$;
end $$;

-- 3) Audit / event log
create table if not exists public.monthly_plan_constraint_events (
    event_id uuid primary key default gen_random_uuid(),

    constraint_id uuid not null
        references public.monthly_plan_constraints (constraint_id)
        on delete cascade,

    line_id uuid,

    project_code text,
    month_key text,

    event_type text not null,

    old_check_status text,
    new_check_status text,

    old_resolution_status text,
    new_resolution_status text,

    event_comment text,

    event_payload jsonb not null default '{}'::jsonb,

    performed_by text,
    performed_at timestamptz not null default now()
);

create index if not exists idx_monthly_plan_constraint_events_constraint_id
  on public.monthly_plan_constraint_events (constraint_id);

create index if not exists idx_monthly_plan_constraint_events_line_id
  on public.monthly_plan_constraint_events (line_id);

create index if not exists idx_monthly_plan_constraint_events_performed_at
  on public.monthly_plan_constraint_events (performed_at desc);

create index if not exists idx_monthly_plan_constraint_events_project_month
  on public.monthly_plan_constraint_events (project_code, month_key);

comment on table public.monthly_plan_constraint_events is
  'Журнал событий ограничений допуска месячного плана (CREATED/UPDATED/RESOLVED/REOPENED/CANCELLED). Неизменяемый audit trail для реестра ограничений.';

comment on column public.monthly_plan_constraint_events.event_id is
  'Уникальный идентификатор события';
comment on column public.monthly_plan_constraint_events.constraint_id is
  'Ссылка на monthly_plan_constraints.constraint_id';
comment on column public.monthly_plan_constraint_events.line_id is
  'plan_line_id / line_id строки плана на момент события';
comment on column public.monthly_plan_constraint_events.event_type is
  'Тип события: CREATED, UPDATED, RESOLVED, REOPENED, CANCELLED (text, без ENUM)';
comment on column public.monthly_plan_constraint_events.event_payload is
  'Доп. payload (например evidence_payload при resolve без insert в evidence table на R1)';
comment on column public.monthly_plan_constraint_events.performed_by is
  'Кто выполнил действие';
comment on column public.monthly_plan_constraint_events.performed_at is
  'Когда выполнено действие';

-- 4) Atomic resolve RPC
-- Department completeness: same 7 seed departments as
-- services/constraints_service.get_constraint_templates / War Room WR2_DEPT_COLUMNS.
-- Missing department ⇒ WAITING (never READY from a single resolved row).
-- Passport writer still computes live at rebuild; this RPC does not write passport.

create or replace function public.resolve_monthly_plan_constraint(
  p_constraint_id uuid,
  p_actual_resolution_date date,
  p_resolution_comment text,
  p_closed_by text,
  p_evidence_payload jsonb default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_closed_by text := nullif(btrim(coalesce(p_closed_by, '')), '');
  v_comment text := nullif(btrim(coalesce(p_resolution_comment, '')), '');
  v_now timestamptz := now();

  v_row public.monthly_plan_constraints%rowtype;

  v_old_check text;
  v_old_resolution text;
  v_old_resolved_at timestamptz;
  v_old_resolved_by text;
  v_old_actual date;

  v_new_comment text;
  v_status text := 'resolved';
  v_event_id uuid;

  v_required_depts text[] := array[
    'Участок',
    'ПТО',
    'МТО',
    'ОТиТБ',
    'QAQC',
    'Коммерческий отдел',
    'Руководство'
  ];

  v_total_count integer := 0;
  v_pass_count integer := 0;
  v_open_hold_count integer := 0;
  v_open_fail_count integer := 0;
  v_open_warning_count integer := 0;
  v_waiting_count integer := 0;
  v_cancelled_count integer := 0;
  v_present_dept_count integer := 0;
  v_missing_dept_count integer := 0;
  v_admission_outcome text;

  v_remaining_blockers jsonb := '[]'::jsonb;
  v_line_summary jsonb;
  v_payload jsonb;
begin
  -- 1) Validate arguments
  if p_constraint_id is null then
    raise exception 'resolve_monthly_plan_constraint: p_constraint_id is required';
  end if;
  if p_actual_resolution_date is null then
    raise exception 'resolve_monthly_plan_constraint: p_actual_resolution_date is required';
  end if;
  if v_closed_by is null then
    raise exception 'resolve_monthly_plan_constraint: p_closed_by is required';
  end if;
  if v_comment is null then
    raise exception 'resolve_monthly_plan_constraint: p_resolution_comment is required';
  end if;

  -- 2) Lock target row
  select *
    into v_row
  from public.monthly_plan_constraints
  where constraint_id = p_constraint_id
  for update;

  if not found then
    raise exception
      'resolve_monthly_plan_constraint: constraint_id % not found',
      p_constraint_id;
  end if;

  v_old_check := v_row.check_status;
  v_old_resolution := v_row.resolution_status;
  v_old_resolved_at := v_row.resolved_at;
  v_old_resolved_by := v_row.resolved_by;
  v_old_actual := v_row.actual_resolution_date;

  -- 4) Idempotent already_resolved
  if v_row.check_status = 'PASS'
     and v_row.resolution_status = 'RESOLVED' then
    v_status := 'already_resolved';
  else
    -- 5) Update constraint
    v_new_comment := coalesce(v_row.comment, '');
    if v_new_comment <> '' then
      v_new_comment := v_new_comment || E'\n';
    end if;
    v_new_comment := v_new_comment
      || '[RESOLVED '
      || to_char(p_actual_resolution_date, 'YYYY-MM-DD')
      || ' / '
      || v_closed_by
      || ']'
      || E'\n'
      || v_comment;

    update public.monthly_plan_constraints
    set
      check_status = 'PASS',
      resolution_status = 'RESOLVED',
      actual_resolution_date = p_actual_resolution_date,
      resolved_at = v_now,
      resolved_by = v_closed_by,
      updated_by = v_closed_by,
      updated_at = v_now,
      last_action_at = v_now,
      last_comment_at = v_now,
      comment = v_new_comment
    where constraint_id = p_constraint_id;

    -- reload after update
    select *
      into v_row
    from public.monthly_plan_constraints
    where constraint_id = p_constraint_id;

    -- 6) Evidence: R1 stores payload on event only (no insert into evidence table)
    v_payload := coalesce(p_evidence_payload, '{}'::jsonb);
    if jsonb_typeof(v_payload) <> 'object' then
      v_payload := jsonb_build_object('evidence_payload', p_evidence_payload);
    end if;

    -- 7) Audit event (single RESOLVED)
    insert into public.monthly_plan_constraint_events (
      constraint_id,
      line_id,
      project_code,
      month_key,
      event_type,
      old_check_status,
      new_check_status,
      old_resolution_status,
      new_resolution_status,
      event_comment,
      event_payload,
      performed_by,
      performed_at
    ) values (
      p_constraint_id,
      v_row.line_id,
      v_row.project_code,
      v_row.month_key,
      'RESOLVED',
      v_old_check,
      'PASS',
      v_old_resolution,
      'RESOLVED',
      v_comment,
      v_payload,
      v_closed_by,
      v_now
    )
    returning event_id into v_event_id;
  end if;

  -- 8) Recalc ALL constraints for same line_id (CANCELLED excluded from active)
  if v_row.line_id is null then
    -- Isolated constraint without line: counts from this row only
    select
      count(*)::integer,
      count(*) filter (where c.resolution_status = 'CANCELLED')::integer,
      count(*) filter (
        where c.resolution_status is distinct from 'CANCELLED'
          and c.check_status = 'PASS'
      )::integer,
      count(*) filter (
        where c.resolution_status not in ('RESOLVED', 'CANCELLED')
          and c.check_status = 'HOLD'
      )::integer,
      count(*) filter (
        where c.resolution_status not in ('RESOLVED', 'CANCELLED')
          and c.check_status = 'FAIL'
      )::integer,
      count(*) filter (
        where c.resolution_status not in ('RESOLVED', 'CANCELLED')
          and c.check_status = 'WARNING'
      )::integer,
      count(*) filter (
        where c.resolution_status not in ('RESOLVED', 'CANCELLED')
          and c.check_status not in ('PASS', 'HOLD', 'FAIL', 'WARNING')
      )::integer
    into
      v_total_count,
      v_cancelled_count,
      v_pass_count,
      v_open_hold_count,
      v_open_fail_count,
      v_open_warning_count,
      v_waiting_count
    from public.monthly_plan_constraints c
    where c.constraint_id = p_constraint_id;

    v_present_dept_count := case
      when v_row.responsible_department = any (v_required_depts) then 1
      else 0
    end;
    v_missing_dept_count := greatest(array_length(v_required_depts, 1) - v_present_dept_count, 0);
    v_remaining_blockers := '[]'::jsonb;
  else
    select
      count(*)::integer,
      count(*) filter (where c.resolution_status = 'CANCELLED')::integer,
      count(*) filter (
        where c.resolution_status is distinct from 'CANCELLED'
          and c.check_status = 'PASS'
      )::integer,
      count(*) filter (
        where c.resolution_status not in ('RESOLVED', 'CANCELLED')
          and c.check_status = 'HOLD'
      )::integer,
      count(*) filter (
        where c.resolution_status not in ('RESOLVED', 'CANCELLED')
          and c.check_status = 'FAIL'
      )::integer,
      count(*) filter (
        where c.resolution_status not in ('RESOLVED', 'CANCELLED')
          and c.check_status = 'WARNING'
      )::integer,
      count(*) filter (
        where c.resolution_status not in ('RESOLVED', 'CANCELLED')
          and c.check_status not in ('PASS', 'HOLD', 'FAIL', 'WARNING')
      )::integer,
      count(distinct c.responsible_department) filter (
        where c.responsible_department = any (v_required_depts)
      )::integer
    into
      v_total_count,
      v_cancelled_count,
      v_pass_count,
      v_open_hold_count,
      v_open_fail_count,
      v_open_warning_count,
      v_waiting_count,
      v_present_dept_count
    from public.monthly_plan_constraints c
    where c.line_id = v_row.line_id;

    -- CANCELLED rows still mark a department as seeded/present (do not invent WAITING).
    -- Active blockers ignore CANCELLED via resolution_status filters above.

    v_missing_dept_count := greatest(
      coalesce(array_length(v_required_depts, 1), 0) - coalesce(v_present_dept_count, 0),
      0
    );

    -- Missing mandatory departments behave as WAITING for admission_outcome
    if v_missing_dept_count > 0 then
      v_waiting_count := v_waiting_count + v_missing_dept_count;
    end if;

    select coalesce(jsonb_agg(to_jsonb(b) order by b.check_status, b.responsible_department), '[]'::jsonb)
      into v_remaining_blockers
    from (
      select
        c.constraint_id,
        c.responsible_department,
        c.check_name,
        c.check_status,
        c.resolution_status,
        c.block_reason,
        c.root_cause,
        c.problem_owner,
        c.owner_name,
        c.target_resolution_date,
        c.value_at_risk
      from public.monthly_plan_constraints c
      where c.line_id = v_row.line_id
        and c.resolution_status not in ('RESOLVED', 'CANCELLED')
        and c.check_status in ('HOLD', 'FAIL', 'WARNING', 'ОЖИДАЕТ')
    ) b;
  end if;

  -- 9) Admission outcome (live summary only — not written to plan lines / passport)
  if coalesce(v_open_hold_count, 0) > 0 or coalesce(v_open_fail_count, 0) > 0 then
    v_admission_outcome := 'BLOCKED';
  elsif coalesce(v_open_warning_count, 0) > 0 then
    v_admission_outcome := 'READY_WITH_RISK';
  elsif coalesce(v_waiting_count, 0) > 0 or coalesce(v_missing_dept_count, 0) > 0 then
    v_admission_outcome := 'WAITING';
  elsif coalesce(v_pass_count, 0) > 0
        and coalesce(v_missing_dept_count, 0) = 0
        and coalesce(v_open_hold_count, 0) = 0
        and coalesce(v_open_fail_count, 0) = 0
        and coalesce(v_open_warning_count, 0) = 0 then
    v_admission_outcome := 'READY';
  else
    -- No active checks / empty line → do not invent READY
    v_admission_outcome := 'WAITING';
  end if;

  v_line_summary := jsonb_build_object(
    'total_count', coalesce(v_total_count, 0),
    'pass_count', coalesce(v_pass_count, 0),
    'open_hold_count', coalesce(v_open_hold_count, 0),
    'open_fail_count', coalesce(v_open_fail_count, 0),
    'open_warning_count', coalesce(v_open_warning_count, 0),
    'waiting_count', coalesce(v_waiting_count, 0),
    'cancelled_count', coalesce(v_cancelled_count, 0),
    'required_department_count', coalesce(array_length(v_required_depts, 1), 0),
    'present_department_count', coalesce(v_present_dept_count, 0),
    'missing_department_count', coalesce(v_missing_dept_count, 0),
    'admission_outcome', v_admission_outcome
  );

  -- 11) Return payload
  return jsonb_build_object(
    'status', v_status,
    'constraint_id', p_constraint_id,
    'line_id', v_row.line_id,
    'project_code', v_row.project_code,
    'month_key', v_row.month_key,
    'old_check_status', v_old_check,
    'new_check_status', case
      when v_status = 'already_resolved' then v_old_check
      else 'PASS'
    end,
    'old_resolution_status', v_old_resolution,
    'new_resolution_status', case
      when v_status = 'already_resolved' then v_old_resolution
      else 'RESOLVED'
    end,
    'actual_resolution_date', case
      when v_status = 'already_resolved' then v_old_actual
      else p_actual_resolution_date
    end,
    'resolved_by', case
      when v_status = 'already_resolved' then v_old_resolved_by
      else v_closed_by
    end,
    'resolved_at', case
      when v_status = 'already_resolved' then v_old_resolved_at
      else v_now
    end,
    'event_id', v_event_id,
    'line_summary', v_line_summary,
    'remaining_blockers', coalesce(v_remaining_blockers, '[]'::jsonb)
  );
end;
$$;

comment on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb) is
  'Atomic resolve of one monthly_plan_constraint: PASS+RESOLVED, audit event, line summary. No passport writes. Evidence payload stored on event only (R1).';

revoke all on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb)
  from public;

grant execute on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb)
  to service_role;

grant execute on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb)
  to authenticated;

-- Explicit: anon must not execute (ignore if role absent)
do $$
begin
  revoke execute on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb)
    from anon;
exception
  when undefined_object then
    raise notice 'role anon not found — skip revoke';
end $$;
