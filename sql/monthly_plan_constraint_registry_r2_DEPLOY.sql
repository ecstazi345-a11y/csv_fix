-- =============================================================================
-- Monthly Plan Constraint Registry R2.1 — operational / evidentiary memory
-- =============================================================================
-- File:    sql/monthly_plan_constraint_registry_r2.sql
-- Depends: public.monthly_plan_constraints (v1+v2+R1)
--          public.monthly_plan_constraint_events (R1)
--          public.resolve_monthly_plan_constraint (R1)
--          public.monthly_plan_constraint_evidence (optional; for dashboard_v2)
-- Deploy:  Supabase SQL Editor MANUALLY after review. Do NOT auto-run on prod.
-- Scope:   SQL foundation only — no Page 21/23/24, no Python, no passport writes.
--
-- Adds:
--   constraint_occurred_at, subcontractor_coordinator, problem_description,
--   problem_impact, deadline_status, deadline_source, next_control_date,
--   constraint_priority, resolution_basis
--   public.update_monthly_plan_constraint(uuid, text, text, jsonb)
--   resolve R2: optional resolution_basis via p_evidence_payload (same signature)
--   refresh dashboard_v1 / dashboard_v2 with computed deadline fields
--
-- Does NOT:
--   create resolution_executor / second audit table / due_date revival
--   store OVERDUE / RESOLVED in deadline_status
--   backfill constraint_created_at or occurrence dates
--   add CHECK on constraint_category (live free-text RU values incompatible)
--   write passport / monthly_plan_lines_v2
-- =============================================================================

-- 0) Preconditions
do $$
begin
  if to_regclass('public.monthly_plan_constraints') is null then
    raise exception
      'ABORT: public.monthly_plan_constraints not found — apply constraints v1/v2/R1 first';
  end if;
  if to_regclass('public.monthly_plan_constraint_events') is null then
    raise exception
      'ABORT: public.monthly_plan_constraint_events not found — apply registry R1 first';
  end if;
end $$;

-- =============================================================================
-- 1) New columns (idempotent)
-- =============================================================================

alter table public.monthly_plan_constraints
  add column if not exists constraint_occurred_at date;

alter table public.monthly_plan_constraints
  add column if not exists subcontractor_coordinator text;

alter table public.monthly_plan_constraints
  add column if not exists problem_description text;

alter table public.monthly_plan_constraints
  add column if not exists problem_impact text;

alter table public.monthly_plan_constraints
  add column if not exists deadline_status text;

alter table public.monthly_plan_constraints
  add column if not exists deadline_source text;

alter table public.monthly_plan_constraints
  add column if not exists next_control_date date;

alter table public.monthly_plan_constraints
  add column if not exists constraint_priority text;

alter table public.monthly_plan_constraints
  add column if not exists resolution_basis text;

-- Defaults for existing + new rows (safe; does not touch constraint_created_at)
update public.monthly_plan_constraints
set deadline_status = 'NOT_SET'
where deadline_status is null;

update public.monthly_plan_constraints
set constraint_priority = 'NORMAL'
where constraint_priority is null;

alter table public.monthly_plan_constraints
  alter column deadline_status set default 'NOT_SET';

alter table public.monthly_plan_constraints
  alter column constraint_priority set default 'NORMAL';

-- Prefer NOT NULL after backfill of nulls
do $$
begin
  alter table public.monthly_plan_constraints
    alter column deadline_status set not null;
exception
  when others then
    raise notice 'deadline_status NOT NULL skipped: %', sqlerrm;
end $$;

do $$
begin
  alter table public.monthly_plan_constraints
    alter column constraint_priority set not null;
exception
  when others then
    raise notice 'constraint_priority NOT NULL skipped: %', sqlerrm;
end $$;

comment on column public.monthly_plan_constraints.constraint_occurred_at is
  'Дата фактического возникновения проблемы на проекте. Не путать с constraint_created_at (дата регистрации).';
comment on column public.monthly_plan_constraints.constraint_created_at is
  'Дата регистрации ограничения в системе (lifecycle start). Не перезаписывать датой возникновения.';
comment on column public.monthly_plan_constraints.subcontractor_coordinator is
  'Координатор от субподрядчика: сопровождает, фиксирует, напоминает и эскалирует.';
comment on column public.monthly_plan_constraints.problem_description is
  'Подробное фактическое описание проблемы (доказательная память). block_reason остаётся короткой причиной для таблицы.';
comment on column public.monthly_plan_constraints.problem_impact is
  'Последствия для выполнения, срока, стоимости, фронта, закупок.';
comment on column public.monthly_plan_constraints.deadline_status is
  'Качество/источник планового срока: NOT_SET|REQUESTED|ESTIMATED|CONFIRMED|RESCHEDULED. OVERDUE/RESOLVED вычисляются live.';
comment on column public.monthly_plan_constraints.deadline_source is
  'Источник планового срока: CUSTOMER|GENERAL_CONTRACTOR|DESIGN_INSTITUTE|SUPPLIER|SUBCONTRACTOR_ESTIMATE|MEETING_PROTOCOL|LETTER|TEQ|OTHER.';
comment on column public.monthly_plan_constraints.next_control_date is
  'Дата следующего контроля / эскалации координатором.';
comment on column public.monthly_plan_constraints.constraint_priority is
  'Приоритет ограничения: CRITICAL|HIGH|NORMAL|LOW.';
comment on column public.monthly_plan_constraints.resolution_basis is
  'Основание снятия ограничения. Заполняется при resolve (не через OPEN update).';
comment on column public.monthly_plan_constraints.problem_owner is
  'Владелец проблемы (чья зона ответственности). Не путать с owner_name (исполнитель устранения).';
comment on column public.monthly_plan_constraints.owner_name is
  'Исполнитель устранения: кто должен выдать решение / поставить МТР / выпустить РД.';
comment on column public.monthly_plan_constraints.constraint_category is
  'Свободная категория ограничения (RU free-text из Page 21). R2.1 не вводит ENUM CHECK — live values incompatible.';

-- =============================================================================
-- 2) CHECKs (safe). NO CHECK on constraint_category (live RU free-text).
-- =============================================================================

alter table public.monthly_plan_constraints
  drop constraint if exists monthly_plan_constraints_deadline_status_chk;

alter table public.monthly_plan_constraints
  add constraint monthly_plan_constraints_deadline_status_chk
  check (
    deadline_status in (
      'NOT_SET',
      'REQUESTED',
      'ESTIMATED',
      'CONFIRMED',
      'RESCHEDULED'
    )
  );

alter table public.monthly_plan_constraints
  drop constraint if exists monthly_plan_constraints_deadline_source_chk;

alter table public.monthly_plan_constraints
  add constraint monthly_plan_constraints_deadline_source_chk
  check (
    deadline_source is null
    or deadline_source in (
      'CUSTOMER',
      'GENERAL_CONTRACTOR',
      'DESIGN_INSTITUTE',
      'SUPPLIER',
      'SUBCONTRACTOR_ESTIMATE',
      'MEETING_PROTOCOL',
      'LETTER',
      'TEQ',
      'OTHER'
    )
  );

alter table public.monthly_plan_constraints
  drop constraint if exists monthly_plan_constraints_constraint_priority_chk;

alter table public.monthly_plan_constraints
  add constraint monthly_plan_constraints_constraint_priority_chk
  check (
    constraint_priority in ('CRITICAL', 'HIGH', 'NORMAL', 'LOW')
  );

-- =============================================================================
-- 3) Indexes (composite filters only — avoid unused single-column noise)
-- =============================================================================

create index if not exists idx_mpc_r2_project_month_resolution
  on public.monthly_plan_constraints (project_code, month_key, resolution_status);

create index if not exists idx_mpc_r2_project_month_problem_owner
  on public.monthly_plan_constraints (project_code, month_key, problem_owner);

create index if not exists idx_mpc_r2_project_month_target_date
  on public.monthly_plan_constraints (project_code, month_key, target_resolution_date);

create index if not exists idx_mpc_r2_project_month_next_control
  on public.monthly_plan_constraints (project_code, month_key, next_control_date);

create index if not exists idx_mpc_r2_project_month_deadline_status
  on public.monthly_plan_constraints (project_code, month_key, deadline_status);

create index if not exists idx_mpc_r2_project_month_priority
  on public.monthly_plan_constraints (project_code, month_key, constraint_priority);

-- =============================================================================
-- 4) update_monthly_plan_constraint RPC
-- =============================================================================
-- resolution_basis intentionally NOT in OPEN patch whitelist — set via resolve.

create or replace function public.update_monthly_plan_constraint(
  p_constraint_id uuid,
  p_updated_by text,
  p_update_comment text,
  p_patch jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_by text := nullif(btrim(coalesce(p_updated_by, '')), '');
  v_comment text := nullif(btrim(coalesce(p_update_comment, '')), '');
  v_patch jsonb := coalesce(p_patch, '{}'::jsonb);
  v_now timestamptz := now();

  v_row public.monthly_plan_constraints%rowtype;

  v_key text;
  v_allowed text[] := array[
    'constraint_occurred_at',
    'problem_owner',
    'owner_name',
    'subcontractor_coordinator',
    'constraint_category',
    'constraint_priority',
    'problem_description',
    'problem_impact',
    'required_action',
    'deadline_status',
    'deadline_source',
    'target_resolution_date',
    'next_control_date'
  ];

  v_new_occurred date;
  v_new_problem_owner text;
  v_new_owner_name text;
  v_new_coordinator text;
  v_new_category text;
  v_new_priority text;
  v_new_description text;
  v_new_impact text;
  v_new_required_action text;
  v_new_deadline_status text;
  v_new_deadline_source text;
  v_new_target date;
  v_new_next_control date;

  v_chg_occurred boolean := false;
  v_chg_problem_owner boolean := false;
  v_chg_owner_name boolean := false;
  v_chg_coordinator boolean := false;
  v_chg_category boolean := false;
  v_chg_priority boolean := false;
  v_chg_description boolean := false;
  v_chg_impact boolean := false;
  v_chg_required_action boolean := false;
  v_chg_deadline_status boolean := false;
  v_chg_deadline_source boolean := false;
  v_chg_target boolean := false;
  v_chg_next_control boolean := false;

  v_changed text[] := '{}';
  v_old_values jsonb := '{}'::jsonb;
  v_new_values jsonb := '{}'::jsonb;
  v_event_id uuid;
  v_has_change boolean := false;
begin
  if p_constraint_id is null then
    raise exception 'update_monthly_plan_constraint: p_constraint_id is required';
  end if;
  if v_by is null then
    raise exception 'update_monthly_plan_constraint: p_updated_by is required';
  end if;
  if v_comment is null or v_comment in ('—', '-', '–') then
    raise exception 'update_monthly_plan_constraint: p_update_comment is required';
  end if;
  if jsonb_typeof(v_patch) <> 'object' then
    raise exception 'update_monthly_plan_constraint: p_patch must be a jsonb object';
  end if;

  -- Reject unknown / forbidden keys (incl. check_status, resolution_status, resolution_basis)
  for v_key in select jsonb_object_keys(v_patch)
  loop
    if not (v_key = any (v_allowed)) then
      raise exception
        'update_monthly_plan_constraint: unknown or forbidden patch key=%',
        v_key;
    end if;
  end loop;

  select *
    into v_row
  from public.monthly_plan_constraints
  where constraint_id = p_constraint_id
  for update;

  if not found then
    raise exception
      'update_monthly_plan_constraint: constraint_id % not found',
      p_constraint_id;
  end if;

  if v_row.resolution_status not in ('OPEN', 'IN_PROGRESS') then
    raise exception
      'update_monthly_plan_constraint: cannot update resolution_status=% (only OPEN/IN_PROGRESS)',
      v_row.resolution_status;
  end if;

  -- Seed proposed values from current row
  v_new_occurred := v_row.constraint_occurred_at;
  v_new_problem_owner := v_row.problem_owner;
  v_new_owner_name := v_row.owner_name;
  v_new_coordinator := v_row.subcontractor_coordinator;
  v_new_category := v_row.constraint_category;
  v_new_priority := v_row.constraint_priority;
  v_new_description := v_row.problem_description;
  v_new_impact := v_row.problem_impact;
  v_new_required_action := v_row.required_action;
  v_new_deadline_status := v_row.deadline_status;
  v_new_deadline_source := v_row.deadline_source;
  v_new_target := v_row.target_resolution_date;
  v_new_next_control := v_row.next_control_date;

  -- ---- helpers inline: text normalize ----
  if v_patch ? 'problem_owner' then
    if v_patch->'problem_owner' = 'null'::jsonb then
      v_new_problem_owner := null;
    else
      v_new_problem_owner := nullif(btrim(coalesce(v_patch->>'problem_owner', '')), '');
      if v_new_problem_owner in ('—', '-', '–') then
        v_new_problem_owner := null;
      end if;
    end if;
  end if;

  if v_patch ? 'owner_name' then
    if v_patch->'owner_name' = 'null'::jsonb then
      v_new_owner_name := null;
    else
      v_new_owner_name := nullif(btrim(coalesce(v_patch->>'owner_name', '')), '');
      if v_new_owner_name in ('—', '-', '–') then
        v_new_owner_name := null;
      end if;
    end if;
  end if;

  if v_patch ? 'subcontractor_coordinator' then
    if v_patch->'subcontractor_coordinator' = 'null'::jsonb then
      v_new_coordinator := null;
    else
      v_new_coordinator := nullif(btrim(coalesce(v_patch->>'subcontractor_coordinator', '')), '');
      if v_new_coordinator in ('—', '-', '–') then
        v_new_coordinator := null;
      end if;
    end if;
  end if;

  if v_patch ? 'constraint_category' then
    if v_patch->'constraint_category' = 'null'::jsonb then
      v_new_category := null;
    else
      v_new_category := nullif(btrim(coalesce(v_patch->>'constraint_category', '')), '');
      if v_new_category in ('—', '-', '–') then
        v_new_category := null;
      end if;
    end if;
  end if;

  if v_patch ? 'problem_description' then
    if v_patch->'problem_description' = 'null'::jsonb then
      v_new_description := null;
    else
      v_new_description := nullif(btrim(coalesce(v_patch->>'problem_description', '')), '');
      if v_new_description in ('—', '-', '–') then
        v_new_description := null;
      end if;
    end if;
  end if;

  if v_patch ? 'problem_impact' then
    if v_patch->'problem_impact' = 'null'::jsonb then
      v_new_impact := null;
    else
      v_new_impact := nullif(btrim(coalesce(v_patch->>'problem_impact', '')), '');
      if v_new_impact in ('—', '-', '–') then
        v_new_impact := null;
      end if;
    end if;
  end if;

  if v_patch ? 'required_action' then
    if v_patch->'required_action' = 'null'::jsonb then
      v_new_required_action := null;
    else
      v_new_required_action := nullif(btrim(coalesce(v_patch->>'required_action', '')), '');
      if v_new_required_action in ('—', '-', '–') then
        v_new_required_action := null;
      end if;
    end if;
  end if;

  if v_patch ? 'constraint_priority' then
    if v_patch->'constraint_priority' = 'null'::jsonb then
      raise exception 'update_monthly_plan_constraint: constraint_priority cannot be null';
    end if;
    v_new_priority := upper(btrim(coalesce(v_patch->>'constraint_priority', '')));
    if v_new_priority not in ('CRITICAL', 'HIGH', 'NORMAL', 'LOW') then
      raise exception
        'update_monthly_plan_constraint: invalid constraint_priority=%',
        v_new_priority;
    end if;
  end if;

  if v_patch ? 'deadline_status' then
    if v_patch->'deadline_status' = 'null'::jsonb then
      raise exception 'update_monthly_plan_constraint: deadline_status cannot be null';
    end if;
    v_new_deadline_status := upper(btrim(coalesce(v_patch->>'deadline_status', '')));
    if v_new_deadline_status in ('OVERDUE', 'RESOLVED') then
      raise exception
        'update_monthly_plan_constraint: deadline_status=% is computed live and must not be stored',
        v_new_deadline_status;
    end if;
    if v_new_deadline_status not in (
      'NOT_SET', 'REQUESTED', 'ESTIMATED', 'CONFIRMED', 'RESCHEDULED'
    ) then
      raise exception
        'update_monthly_plan_constraint: invalid deadline_status=%',
        v_new_deadline_status;
    end if;
  end if;

  if v_patch ? 'deadline_source' then
    if v_patch->'deadline_source' = 'null'::jsonb then
      v_new_deadline_source := null;
    else
      v_new_deadline_source := upper(btrim(coalesce(v_patch->>'deadline_source', '')));
      if v_new_deadline_source = '' or v_new_deadline_source in ('—', '-', '–') then
        v_new_deadline_source := null;
      elsif v_new_deadline_source not in (
        'CUSTOMER', 'GENERAL_CONTRACTOR', 'DESIGN_INSTITUTE', 'SUPPLIER',
        'SUBCONTRACTOR_ESTIMATE', 'MEETING_PROTOCOL', 'LETTER', 'TEQ', 'OTHER'
      ) then
        raise exception
          'update_monthly_plan_constraint: invalid deadline_source=%',
          v_new_deadline_source;
      end if;
    end if;
  end if;

  if v_patch ? 'constraint_occurred_at' then
    if v_patch->'constraint_occurred_at' = 'null'::jsonb
       or nullif(btrim(coalesce(v_patch->>'constraint_occurred_at', '')), '') is null
       or btrim(coalesce(v_patch->>'constraint_occurred_at', '')) in ('—', '-', '–') then
      v_new_occurred := null;
    else
      begin
        v_new_occurred := (v_patch->>'constraint_occurred_at')::date;
      exception
        when others then
          raise exception
            'update_monthly_plan_constraint: invalid date for constraint_occurred_at=%',
            v_patch->>'constraint_occurred_at';
      end;
    end if;
  end if;

  if v_patch ? 'target_resolution_date' then
    if v_patch->'target_resolution_date' = 'null'::jsonb
       or nullif(btrim(coalesce(v_patch->>'target_resolution_date', '')), '') is null
       or btrim(coalesce(v_patch->>'target_resolution_date', '')) in ('—', '-', '–') then
      v_new_target := null;
    else
      begin
        v_new_target := (v_patch->>'target_resolution_date')::date;
      exception
        when others then
          raise exception
            'update_monthly_plan_constraint: invalid date for target_resolution_date=%',
            v_patch->>'target_resolution_date';
      end;
    end if;
  end if;

  if v_patch ? 'next_control_date' then
    if v_patch->'next_control_date' = 'null'::jsonb
       or nullif(btrim(coalesce(v_patch->>'next_control_date', '')), '') is null
       or btrim(coalesce(v_patch->>'next_control_date', '')) in ('—', '-', '–') then
      v_new_next_control := null;
    else
      begin
        v_new_next_control := (v_patch->>'next_control_date')::date;
      exception
        when others then
          raise exception
            'update_monthly_plan_constraint: invalid date for next_control_date=%',
            v_patch->>'next_control_date';
      end;
    end if;
  end if;

  -- Detect real changes (IS DISTINCT FROM)
  if v_patch ? 'constraint_occurred_at'
     and v_new_occurred is distinct from v_row.constraint_occurred_at then
    v_chg_occurred := true;
    v_changed := array_append(v_changed, 'constraint_occurred_at');
    v_old_values := v_old_values || jsonb_build_object('constraint_occurred_at', v_row.constraint_occurred_at);
    v_new_values := v_new_values || jsonb_build_object('constraint_occurred_at', v_new_occurred);
  end if;
  if v_patch ? 'problem_owner'
     and v_new_problem_owner is distinct from v_row.problem_owner then
    v_chg_problem_owner := true;
    v_changed := array_append(v_changed, 'problem_owner');
    v_old_values := v_old_values || jsonb_build_object('problem_owner', v_row.problem_owner);
    v_new_values := v_new_values || jsonb_build_object('problem_owner', v_new_problem_owner);
  end if;
  if v_patch ? 'owner_name'
     and v_new_owner_name is distinct from v_row.owner_name then
    v_chg_owner_name := true;
    v_changed := array_append(v_changed, 'owner_name');
    v_old_values := v_old_values || jsonb_build_object('owner_name', v_row.owner_name);
    v_new_values := v_new_values || jsonb_build_object('owner_name', v_new_owner_name);
  end if;
  if v_patch ? 'subcontractor_coordinator'
     and v_new_coordinator is distinct from v_row.subcontractor_coordinator then
    v_chg_coordinator := true;
    v_changed := array_append(v_changed, 'subcontractor_coordinator');
    v_old_values := v_old_values || jsonb_build_object('subcontractor_coordinator', v_row.subcontractor_coordinator);
    v_new_values := v_new_values || jsonb_build_object('subcontractor_coordinator', v_new_coordinator);
  end if;
  if v_patch ? 'constraint_category'
     and v_new_category is distinct from v_row.constraint_category then
    v_chg_category := true;
    v_changed := array_append(v_changed, 'constraint_category');
    v_old_values := v_old_values || jsonb_build_object('constraint_category', v_row.constraint_category);
    v_new_values := v_new_values || jsonb_build_object('constraint_category', v_new_category);
  end if;
  if v_patch ? 'constraint_priority'
     and v_new_priority is distinct from v_row.constraint_priority then
    v_chg_priority := true;
    v_changed := array_append(v_changed, 'constraint_priority');
    v_old_values := v_old_values || jsonb_build_object('constraint_priority', v_row.constraint_priority);
    v_new_values := v_new_values || jsonb_build_object('constraint_priority', v_new_priority);
  end if;
  if v_patch ? 'problem_description'
     and v_new_description is distinct from v_row.problem_description then
    v_chg_description := true;
    v_changed := array_append(v_changed, 'problem_description');
    v_old_values := v_old_values || jsonb_build_object('problem_description', v_row.problem_description);
    v_new_values := v_new_values || jsonb_build_object('problem_description', v_new_description);
  end if;
  if v_patch ? 'problem_impact'
     and v_new_impact is distinct from v_row.problem_impact then
    v_chg_impact := true;
    v_changed := array_append(v_changed, 'problem_impact');
    v_old_values := v_old_values || jsonb_build_object('problem_impact', v_row.problem_impact);
    v_new_values := v_new_values || jsonb_build_object('problem_impact', v_new_impact);
  end if;
  if v_patch ? 'required_action'
     and v_new_required_action is distinct from v_row.required_action then
    v_chg_required_action := true;
    v_changed := array_append(v_changed, 'required_action');
    v_old_values := v_old_values || jsonb_build_object('required_action', v_row.required_action);
    v_new_values := v_new_values || jsonb_build_object('required_action', v_new_required_action);
  end if;
  if v_patch ? 'deadline_status'
     and v_new_deadline_status is distinct from v_row.deadline_status then
    v_chg_deadline_status := true;
    v_changed := array_append(v_changed, 'deadline_status');
    v_old_values := v_old_values || jsonb_build_object('deadline_status', v_row.deadline_status);
    v_new_values := v_new_values || jsonb_build_object('deadline_status', v_new_deadline_status);
  end if;
  if v_patch ? 'deadline_source'
     and v_new_deadline_source is distinct from v_row.deadline_source then
    v_chg_deadline_source := true;
    v_changed := array_append(v_changed, 'deadline_source');
    v_old_values := v_old_values || jsonb_build_object('deadline_source', v_row.deadline_source);
    v_new_values := v_new_values || jsonb_build_object('deadline_source', v_new_deadline_source);
  end if;
  if v_patch ? 'target_resolution_date'
     and v_new_target is distinct from v_row.target_resolution_date then
    v_chg_target := true;
    v_changed := array_append(v_changed, 'target_resolution_date');
    v_old_values := v_old_values || jsonb_build_object('target_resolution_date', v_row.target_resolution_date);
    v_new_values := v_new_values || jsonb_build_object('target_resolution_date', v_new_target);
  end if;
  if v_patch ? 'next_control_date'
     and v_new_next_control is distinct from v_row.next_control_date then
    v_chg_next_control := true;
    v_changed := array_append(v_changed, 'next_control_date');
    v_old_values := v_old_values || jsonb_build_object('next_control_date', v_row.next_control_date);
    v_new_values := v_new_values || jsonb_build_object('next_control_date', v_new_next_control);
  end if;

  v_has_change := coalesce(array_length(v_changed, 1), 0) > 0;

  if not v_has_change then
    return jsonb_build_object(
      'status', 'no_changes',
      'constraint_id', p_constraint_id,
      'event_id', null,
      'changed_fields', '[]'::jsonb,
      'line_id', v_row.line_id,
      'project_code', v_row.project_code,
      'month_key', v_row.month_key,
      'resolution_status', v_row.resolution_status,
      'check_status', v_row.check_status
    );
  end if;

  update public.monthly_plan_constraints
  set
    constraint_occurred_at = case when v_chg_occurred then v_new_occurred else constraint_occurred_at end,
    problem_owner = case when v_chg_problem_owner then v_new_problem_owner else problem_owner end,
    owner_name = case when v_chg_owner_name then v_new_owner_name else owner_name end,
    subcontractor_coordinator = case when v_chg_coordinator then v_new_coordinator else subcontractor_coordinator end,
    constraint_category = case when v_chg_category then v_new_category else constraint_category end,
    constraint_priority = case when v_chg_priority then v_new_priority else constraint_priority end,
    problem_description = case when v_chg_description then v_new_description else problem_description end,
    problem_impact = case when v_chg_impact then v_new_impact else problem_impact end,
    required_action = case when v_chg_required_action then v_new_required_action else required_action end,
    deadline_status = case when v_chg_deadline_status then v_new_deadline_status else deadline_status end,
    deadline_source = case when v_chg_deadline_source then v_new_deadline_source else deadline_source end,
    target_resolution_date = case when v_chg_target then v_new_target else target_resolution_date end,
    next_control_date = case when v_chg_next_control then v_new_next_control else next_control_date end,
    updated_by = v_by,
    updated_at = v_now,
    last_action_at = v_now
  where constraint_id = p_constraint_id;

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
    'UPDATED',
    v_row.check_status,
    v_row.check_status,
    v_row.resolution_status,
    v_row.resolution_status,
    v_comment,
    jsonb_build_object(
      'source_page', 'PAGE_24_CONSTRAINT_REGISTRY',
      'changed_fields', to_jsonb(v_changed),
      'old_values', v_old_values,
      'new_values', v_new_values
    ),
    v_by,
    v_now
  )
  returning event_id into v_event_id;

  -- reload
  select *
    into v_row
  from public.monthly_plan_constraints
  where constraint_id = p_constraint_id;

  return jsonb_build_object(
    'status', 'updated',
    'constraint_id', p_constraint_id,
    'event_id', v_event_id,
    'changed_fields', to_jsonb(v_changed),
    'old_values', v_old_values,
    'new_values', v_new_values,
    'line_id', v_row.line_id,
    'project_code', v_row.project_code,
    'month_key', v_row.month_key,
    'resolution_status', v_row.resolution_status,
    'check_status', v_row.check_status,
    'updated_by', v_row.updated_by,
    'updated_at', v_row.updated_at,
    'last_action_at', v_row.last_action_at
  );
end;
$$;

comment on function public.update_monthly_plan_constraint(uuid, text, text, jsonb) is
  'Atomic OPEN/IN_PROGRESS patch update for monthly_plan_constraints + UPDATED audit event. No check_status/resolution changes. No passport writes. resolution_basis via resolve only.';

revoke all on function public.update_monthly_plan_constraint(uuid, text, text, jsonb)
  from public;

grant execute on function public.update_monthly_plan_constraint(uuid, text, text, jsonb)
  to service_role;

grant execute on function public.update_monthly_plan_constraint(uuid, text, text, jsonb)
  to authenticated;

do $$
begin
  revoke execute on function public.update_monthly_plan_constraint(uuid, text, text, jsonb)
    from anon;
exception
  when undefined_object then
    raise notice 'role anon not found — skip revoke update RPC';
end $$;

-- =============================================================================
-- 5) resolve_monthly_plan_constraint R2 — same signature; resolution_basis via payload
-- =============================================================================
-- If p_evidence_payload ? resolution_basis (non-empty) → set column.
-- Else keep existing resolution_basis. Never clear via absent key.

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
  v_old_basis text;

  v_new_comment text;
  v_status text := 'resolved';
  v_event_id uuid;
  v_payload jsonb;
  v_basis text;

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
begin
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
  v_old_basis := v_row.resolution_basis;

  v_payload := coalesce(p_evidence_payload, '{}'::jsonb);
  if jsonb_typeof(v_payload) <> 'object' then
    v_payload := jsonb_build_object('evidence_payload', p_evidence_payload);
  end if;

  v_basis := nullif(btrim(coalesce(v_payload->>'resolution_basis', '')), '');
  if v_basis in ('—', '-', '–') then
    v_basis := null;
  end if;
  -- Keep existing if payload omits / empty
  v_basis := coalesce(v_basis, v_old_basis);

  if v_row.check_status = 'PASS'
     and v_row.resolution_status = 'RESOLVED' then
    v_status := 'already_resolved';
  else
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
      resolution_basis = v_basis,
      resolved_at = v_now,
      resolved_by = v_closed_by,
      updated_by = v_closed_by,
      updated_at = v_now,
      last_action_at = v_now,
      last_comment_at = v_now,
      comment = v_new_comment
    where constraint_id = p_constraint_id;

    select *
      into v_row
    from public.monthly_plan_constraints
    where constraint_id = p_constraint_id;

    if v_basis is not null then
      v_payload := v_payload || jsonb_build_object('resolution_basis', v_basis);
    end if;

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

  if v_row.line_id is null then
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

    v_missing_dept_count := greatest(
      coalesce(array_length(v_required_depts, 1), 0) - coalesce(v_present_dept_count, 0),
      0
    );

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
    'resolution_basis', case
      when v_status = 'already_resolved' then v_old_basis
      else v_basis
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
  'Atomic resolve (R2): PASS+RESOLVED, optional resolution_basis via p_evidence_payload, audit event, line summary. No passport writes.';

revoke all on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb)
  from public;

grant execute on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb)
  to service_role;

grant execute on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb)
  to authenticated;

do $$
begin
  revoke execute on function public.resolve_monthly_plan_constraint(uuid, date, text, text, jsonb)
    from anon;
exception
  when undefined_object then
    raise notice 'role anon not found — skip revoke resolve RPC';
end $$;

-- =============================================================================
-- 6) Refresh dashboard views (DROP + CREATE, explicit columns — no c.*)
-- =============================================================================

do $$
declare
  v_deps text;
begin
  select string_agg(dependent_name, ', ' order by dependent_name)
    into v_deps
  from (
    select distinct
      dependent_ns.nspname || '.' || dependent_view.relname as dependent_name
    from pg_depend
    join pg_rewrite
      on pg_depend.objid = pg_rewrite.oid
    join pg_class as dependent_view
      on pg_rewrite.ev_class = dependent_view.oid
    join pg_class as source_view
      on pg_depend.refobjid = source_view.oid
    join pg_namespace dependent_ns
      on dependent_ns.oid = dependent_view.relnamespace
    join pg_namespace source_ns
      on source_ns.oid = source_view.relnamespace
    where source_ns.nspname = 'public'
      and source_view.relname = 'monthly_plan_constraints_dashboard_v2'
      and dependent_view.relname <> 'monthly_plan_constraints_dashboard_v2'
      and pg_depend.deptype = 'n'
  ) d;

  if v_deps is not null then
    raise exception
      'ABORT: monthly_plan_constraints_dashboard_v2 has dependents (%). Refusing DROP without CASCADE.',
      v_deps;
  end if;
end $$;

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
    c.constraint_occurred_at,
    c.subcontractor_coordinator,
    c.problem_description,
    c.problem_impact,
    c.deadline_status,
    c.deadline_source,
    c.next_control_date,
    c.constraint_priority,
    c.resolution_basis,
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
    ) as is_overdue,
    (
        coalesce(c.actual_resolution_date, current_date)
        - coalesce(c.constraint_occurred_at, c.constraint_created_at::date, c.created_at::date)
    )::integer as days_open_real,
    case
        when c.resolution_status not in ('RESOLVED', 'CANCELLED')
            and c.target_resolution_date is not null
            and c.target_resolution_date < current_date
        then (current_date - c.target_resolution_date)::integer
        else 0
    end as deadline_days_overdue,
    (
        c.resolution_status not in ('RESOLVED', 'CANCELLED')
        and c.target_resolution_date is not null
        and c.target_resolution_date < current_date
    ) as is_deadline_overdue,
    (
        c.resolution_status not in ('RESOLVED', 'CANCELLED')
        and c.next_control_date is not null
        and c.next_control_date < current_date
    ) as is_next_control_overdue,
    case
        when c.resolution_status = 'RESOLVED' then 'RESOLVED'
        when c.resolution_status not in ('RESOLVED', 'CANCELLED')
             and c.target_resolution_date is not null
             and c.target_resolution_date < current_date
        then 'OVERDUE'
        else c.deadline_status
    end as effective_deadline_status
from public.monthly_plan_constraints c;

comment on view public.monthly_plan_constraints_dashboard_v1 is
  'Дашборд ограничений v1 (R2): lifecycle + deadline computed fields.';

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
        c.constraint_occurred_at,
        c.subcontractor_coordinator,
        c.problem_description,
        c.problem_impact,
        c.deadline_status,
        c.deadline_source,
        c.next_control_date,
        c.constraint_priority,
        c.resolution_basis,
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
        ) as is_promise_overdue,
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
        ) as is_overdue,
        (
            coalesce(c.actual_resolution_date, current_date)
            - coalesce(c.constraint_occurred_at, c.constraint_created_at::date, c.created_at::date)
        )::integer as days_open_real,
        case
            when c.resolution_status not in ('RESOLVED', 'CANCELLED')
                and c.target_resolution_date is not null
                and c.target_resolution_date < current_date
            then (current_date - c.target_resolution_date)::integer
            else 0
        end as deadline_days_overdue,
        (
            c.resolution_status not in ('RESOLVED', 'CANCELLED')
            and c.target_resolution_date is not null
            and c.target_resolution_date < current_date
        ) as is_deadline_overdue,
        (
            c.resolution_status not in ('RESOLVED', 'CANCELLED')
            and c.next_control_date is not null
            and c.next_control_date < current_date
        ) as is_next_control_overdue,
        case
            when c.resolution_status = 'RESOLVED' then 'RESOLVED'
            when c.resolution_status not in ('RESOLVED', 'CANCELLED')
                 and c.target_resolution_date is not null
                 and c.target_resolution_date < current_date
            then 'OVERDUE'
            else c.deadline_status
        end as effective_deadline_status
    from public.monthly_plan_constraints c
    left join evidence_promise ep
        on ep.constraint_id = c.constraint_id
  $view$;

  execute $c$
    comment on view public.monthly_plan_constraints_dashboard_v2 is
      'Дашборд ограничений v2 (R2): evidence/promise + R2 fields + deadline computed columns.'
  $c$;
end $$;

-- =============================================================================
-- 7) PostgREST schema reload hint
-- =============================================================================
notify pgrst, 'reload schema';
