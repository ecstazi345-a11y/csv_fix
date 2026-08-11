-- =============================================================================
-- Tests: monthly_plan_constraint_registry_r2
-- =============================================================================
-- File:   sql/tests/monthly_plan_constraint_registry_r2_tests.sql
-- Deploy: run ONLY on sandbox / after applying
--         sql/monthly_plan_constraint_registry_r2.sql
-- DO NOT run on production without review.
--
-- All fixtures: project_code = TEST_REG_R2, synthetic UUIDs.
-- Single transaction → ROLLBACK. No product residue.
-- =============================================================================

begin;

do $$
declare
  v_open uuid := 'bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1001'::uuid;
  v_prog uuid := 'bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1002'::uuid;
  v_resolved uuid := 'bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1003'::uuid;
  v_cancelled uuid := 'bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1004'::uuid;
  v_open2 uuid := 'bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1005'::uuid;
  v_line uuid := 'bbbbbbbb-bbbb-cccc-dddd-eeeeeeee0001'::uuid;

  v_res jsonb;
  v_res2 jsonb;
  v_event_count integer;
  v_event_count_before integer;
  v_passport_before integer;
  v_passport_after integer;
  v_product_before integer;
  v_product_after integer;
  v_exc text;
  v_ok boolean;
  v_row public.monthly_plan_constraints%rowtype;
  v_days integer;
  v_updated_at_before timestamptz;
begin
  if to_regprocedure(
    'public.update_monthly_plan_constraint(uuid,text,text,jsonb)'
  ) is null then
    raise exception 'TEST ABORT: update RPC missing — apply registry_r2 migration first';
  end if;
  if to_regclass('public.monthly_plan_constraint_events') is null then
    raise exception 'TEST ABORT: events table missing';
  end if;

  select count(*)::integer into v_passport_before
  from public.monthly_plan_passports;

  select count(*)::integer into v_product_before
  from public.monthly_plan_constraints
  where project_code is distinct from 'TEST_REG_R2';

  -- cleanup leftovers inside txn
  delete from public.monthly_plan_constraints
  where constraint_id in (v_open, v_prog, v_resolved, v_cancelled, v_open2)
     or project_code = 'TEST_REG_R2';

  insert into public.monthly_plan_constraints (
    constraint_id, line_id, project_code, month_key,
    facility_building, construction_discipline, boq_code, boq_name,
    gate_layer, responsible_department, check_name,
    check_status, resolution_status,
    block_reason, root_cause, owner_name, problem_owner, required_action,
    constraint_created_at, constraint_occurred_at,
    target_resolution_date, next_control_date,
    deadline_status, deadline_source, constraint_priority,
    value_at_risk
  ) values
  (v_open, v_line, 'TEST_REG_R2', 'test-r2-2026', 'T-FIXTURE', 'D', 'BOQ-R2-01', 'R2 open',
   'EXECUTABILITY', 'МТО', 'Материалы и оборудование',
   'HOLD', 'OPEN',
   'Не согласован TEQ', 'TEQ', 'ПИ Иванов', 'Заказчик', 'Выдать TEQ',
   timestamptz '2026-07-01 10:00:00+00', date '2026-06-20',
   date '2026-07-15', date '2026-07-10',
   'ESTIMATED', 'CUSTOMER', 'HIGH',
   50000),
  (v_prog, v_line, 'TEST_REG_R2', 'test-r2-2026', 'T-FIXTURE', 'D', 'BOQ-R2-02', 'R2 progress',
   'EXECUTABILITY', 'ПТО', 'РД / IWP / исполнительность',
   'WARNING', 'IN_PROGRESS',
   'РД', 'РД', 'ПТО', 'Генподрядчик', 'Выпустить РД',
   timestamptz '2026-07-02 10:00:00+00', null,
   date '2026-08-01', null,
   'NOT_SET', null, 'NORMAL',
   10000),
  (v_resolved, v_line, 'TEST_REG_R2', 'test-r2-2026', 'T-FIXTURE', 'D', 'BOQ-R2-03', 'R2 resolved',
   'EXECUTABILITY', 'Участок', 'Фронт физически открыт',
   'PASS', 'RESOLVED',
   null, null, 'A', null, null,
   timestamptz '2026-06-01 10:00:00+00', date '2026-05-01',
   date '2026-06-10', null,
   'CONFIRMED', 'LETTER', 'LOW',
   0),
  (v_cancelled, v_line, 'TEST_REG_R2', 'test-r2-2026', 'T-FIXTURE', 'D', 'BOQ-R2-04', 'R2 cancelled',
   'EXECUTABILITY', 'ОТиТБ', 'Наряды / безопасность',
   'HOLD', 'CANCELLED',
   'X', 'X', 'A', null, null,
   timestamptz '2026-06-01 10:00:00+00', null,
   null, null,
   'NOT_SET', null, 'NORMAL',
   0),
  (v_open2, v_line, 'TEST_REG_R2', 'test-r2-2026', 'T-FIXTURE', 'D', 'BOQ-R2-05', 'R2 open2',
   'EXECUTABILITY', 'QAQC', 'Контроль качества / приёмка',
   'HOLD', 'OPEN',
   'QA', 'QA', 'QAQC', 'Субподрядчик', 'Исправить',
   timestamptz '2026-07-03 10:00:00+00', date '2026-07-01',
   date '2026-07-05', date '2026-07-04',
   'REQUESTED', 'TEQ', 'CRITICAL',
   20000);

  -- =========================================================================
  -- T1 update OPEN with several patch fields
  -- =========================================================================
  v_res := public.update_monthly_plan_constraint(
    v_open,
    'R2 Tester',
    'Обновление OPEN: роли и описание',
    jsonb_build_object(
      'problem_owner', 'Заказчик',
      'owner_name', 'Проектный институт',
      'subcontractor_coordinator', 'Иван Аршавский',
      'problem_description', 'Заказчиком не подтверждена применимость МТР по вентиляции',
      'problem_impact', 'Закупка и монтаж невозможны; BOQ удерживается',
      'required_action', 'Выдать письменное согласование TEQ',
      'deadline_status', 'confirmed',
      'deadline_source', 'teq',
      'target_resolution_date', '2026-08-20',
      'next_control_date', '2026-08-10',
      'constraint_priority', 'critical',
      'constraint_occurred_at', '2026-06-15'
    )
  );

  if v_res->>'status' <> 'updated' then
    raise exception 'T1 fail: status=%', v_res->>'status';
  end if;
  if v_res->>'check_status' <> 'HOLD' then
    raise exception 'T1 fail: check_status changed unexpectedly';
  end if;
  if v_res->>'resolution_status' <> 'OPEN' then
    raise exception 'T1 fail: resolution_status changed unexpectedly';
  end if;

  select * into v_row from public.monthly_plan_constraints where constraint_id = v_open;
  if v_row.owner_name <> 'Проектный институт' then
    raise exception 'T1 fail: owner_name=%', v_row.owner_name;
  end if;
  if v_row.subcontractor_coordinator <> 'Иван Аршавский' then
    raise exception 'T1 fail: coordinator';
  end if;
  if v_row.deadline_status <> 'CONFIRMED' then
    raise exception 'T1 fail: deadline_status=%', v_row.deadline_status;
  end if;
  if v_row.deadline_source <> 'TEQ' then
    raise exception 'T1 fail: deadline_source=%', v_row.deadline_source;
  end if;
  if v_row.constraint_priority <> 'CRITICAL' then
    raise exception 'T1 fail: priority=%', v_row.constraint_priority;
  end if;
  if v_row.constraint_occurred_at <> date '2026-06-15' then
    raise exception 'T1 fail: occurred_at';
  end if;
  if v_row.constraint_created_at::date <> date '2026-07-01' then
    raise exception 'T1 fail: constraint_created_at was mutated';
  end if;
  if v_row.updated_by <> 'R2 Tester' then
    raise exception 'T1 fail: updated_by';
  end if;
  if v_row.last_action_at is null then
    raise exception 'T1 fail: last_action_at null';
  end if;

  -- =========================================================================
  -- T2 UPDATED event created
  -- =========================================================================
  select count(*) into v_event_count
  from public.monthly_plan_constraint_events
  where constraint_id = v_open and event_type = 'UPDATED';
  if v_event_count <> 1 then
    raise exception 'T2 fail: UPDATED events=%', v_event_count;
  end if;

  -- =========================================================================
  -- T3 old/new/changed_fields correct
  -- =========================================================================
  if not exists (
    select 1
    from public.monthly_plan_constraint_events e
    where e.constraint_id = v_open
      and e.event_type = 'UPDATED'
      and e.event_payload->>'source_page' = 'PAGE_24_CONSTRAINT_REGISTRY'
      and e.event_payload->'changed_fields' ?| array[
        'owner_name', 'subcontractor_coordinator', 'deadline_status'
      ]
      and e.event_payload->'old_values' ? 'owner_name'
      and e.event_payload->'new_values'->>'owner_name' = 'Проектный институт'
      and e.old_check_status = 'HOLD'
      and e.new_check_status = 'HOLD'
      and e.old_resolution_status = 'OPEN'
      and e.new_resolution_status = 'OPEN'
  ) then
    raise exception 'T3 fail: event payload mismatch';
  end if;

  -- =========================================================================
  -- T4 missing key does not change field
  -- =========================================================================
  v_res := public.update_monthly_plan_constraint(
    v_open,
    'R2 Tester',
    'Только impact',
    jsonb_build_object('problem_impact', 'Новое последствие')
  );
  if v_res->>'status' <> 'updated' then
    raise exception 'T4 fail: status=%', v_res->>'status';
  end if;
  select * into v_row from public.monthly_plan_constraints where constraint_id = v_open;
  if v_row.owner_name <> 'Проектный институт' then
    raise exception 'T4 fail: owner_name changed without key';
  end if;
  if v_row.problem_impact <> 'Новое последствие' then
    raise exception 'T4 fail: impact not updated';
  end if;

  -- =========================================================================
  -- T5 patch null clears field
  -- =========================================================================
  v_res := public.update_monthly_plan_constraint(
    v_open,
    'R2 Tester',
    'Очистка координатора',
    jsonb_build_object('subcontractor_coordinator', null)
  );
  if v_res->>'status' <> 'updated' then
    raise exception 'T5 fail: status=%', v_res->>'status';
  end if;
  select * into v_row from public.monthly_plan_constraints where constraint_id = v_open;
  if v_row.subcontractor_coordinator is not null then
    raise exception 'T5 fail: coordinator not cleared';
  end if;

  -- =========================================================================
  -- T6 no_changes → no event, updated_at unchanged
  -- =========================================================================
  select updated_at into v_updated_at_before
  from public.monthly_plan_constraints where constraint_id = v_open;

  select count(*) into v_event_count_before
  from public.monthly_plan_constraint_events
  where constraint_id = v_open and event_type = 'UPDATED';

  v_res := public.update_monthly_plan_constraint(
    v_open,
    'R2 Tester',
    'Повтор без изменений',
    jsonb_build_object('owner_name', 'Проектный институт')
  );
  if v_res->>'status' <> 'no_changes' then
    raise exception 'T6 fail: status=%', v_res->>'status';
  end if;
  if v_res->>'event_id' is not null and v_res->>'event_id' <> '' then
    raise exception 'T6 fail: event_id present on no_changes';
  end if;

  select count(*) into v_event_count
  from public.monthly_plan_constraint_events
  where constraint_id = v_open and event_type = 'UPDATED';
  if v_event_count <> v_event_count_before then
    raise exception 'T6 fail: event created on no_changes';
  end if;

  select * into v_row from public.monthly_plan_constraints where constraint_id = v_open;
  if v_row.updated_at is distinct from v_updated_at_before then
    raise exception 'T6 fail: updated_at changed on no_changes';
  end if;

  -- =========================================================================
  -- T7 invalid deadline_status
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', 'bad status',
      jsonb_build_object('deadline_status', 'OVERDUE')
    );
  exception
    when others then
      v_ok := true;
      v_exc := sqlerrm;
  end;
  if not v_ok then
    raise exception 'T7 fail: OVERDUE accepted';
  end if;
  if position('deadline_status' in v_exc) = 0 then
    raise exception 'T7 fail: unexpected error=%', v_exc;
  end if;

  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', 'bad status2',
      jsonb_build_object('deadline_status', 'FOO')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T7b fail: invalid status accepted';
  end if;

  -- =========================================================================
  -- T8 invalid deadline_source
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', 'bad source',
      jsonb_build_object('deadline_source', 'WHATSAPP')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T8 fail: invalid source accepted';
  end if;

  -- =========================================================================
  -- T9 invalid priority
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', 'bad priority',
      jsonb_build_object('constraint_priority', 'URGENT')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T9 fail: invalid priority accepted';
  end if;

  -- =========================================================================
  -- T10 invalid date
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', 'bad date',
      jsonb_build_object('target_resolution_date', 'not-a-date')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T10 fail: invalid date accepted';
  end if;

  -- =========================================================================
  -- T11 empty updated_by
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, '  ', 'comment ok',
      jsonb_build_object('required_action', 'x')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T11 fail: empty updated_by accepted';
  end if;

  -- =========================================================================
  -- T12 empty update_comment
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', '—',
      jsonb_build_object('required_action', 'x')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T12 fail: empty comment accepted';
  end if;

  -- =========================================================================
  -- T13 RESOLVED cannot update
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_resolved, 'R2 Tester', 'try resolve edit',
      jsonb_build_object('required_action', 'nope')
    );
  exception
    when others then
      v_ok := true;
      v_exc := sqlerrm;
  end;
  if not v_ok then
    raise exception 'T13 fail: RESOLVED update allowed';
  end if;
  if position('OPEN/IN_PROGRESS' in v_exc) = 0
     and position('RESOLVED' in v_exc) = 0 then
    raise exception 'T13 fail: unexpected error=%', v_exc;
  end if;

  -- =========================================================================
  -- T14 CANCELLED cannot update
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_cancelled, 'R2 Tester', 'try cancel edit',
      jsonb_build_object('required_action', 'nope')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T14 fail: CANCELLED update allowed';
  end if;

  -- =========================================================================
  -- T15 check_status / resolution_status / resolution_basis forbidden in patch
  -- =========================================================================
  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', 'forbidden check',
      jsonb_build_object('check_status', 'PASS')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T15a fail: check_status patch allowed';
  end if;

  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', 'forbidden resolution',
      jsonb_build_object('resolution_status', 'RESOLVED')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T15b fail: resolution_status patch allowed';
  end if;

  v_ok := false;
  begin
    perform public.update_monthly_plan_constraint(
      v_prog, 'R2 Tester', 'forbidden basis',
      jsonb_build_object('resolution_basis', 'letter XYZ')
    );
  exception
    when others then
      v_ok := true;
  end;
  if not v_ok then
    raise exception 'T15c fail: resolution_basis patch allowed';
  end if;

  -- =========================================================================
  -- T16 passport counts unchanged
  -- =========================================================================
  select count(*)::integer into v_passport_after
  from public.monthly_plan_passports;
  if v_passport_after <> v_passport_before then
    raise exception 'T16 fail: passport count % → %', v_passport_before, v_passport_after;
  end if;

  -- =========================================================================
  -- T17 product constraints outside fixture unchanged count
  -- =========================================================================
  select count(*)::integer into v_product_after
  from public.monthly_plan_constraints
  where project_code is distinct from 'TEST_REG_R2';
  if v_product_after <> v_product_before then
    raise exception 'T17 fail: product constraints % → %', v_product_before, v_product_after;
  end if;

  -- =========================================================================
  -- T19 days_open_real fallback (occurred null → created_at)
  -- =========================================================================
  if to_regclass('public.monthly_plan_constraints_dashboard_v2') is not null then
    select days_open_real into v_days
    from public.monthly_plan_constraints_dashboard_v2
    where constraint_id = v_prog;
    if v_days is null then
      raise exception 'T19 fail: days_open_real null';
    end if;
    -- occurred null → use created_at date 2026-07-02; open → current_date - 2026-07-02
    if v_days <> (current_date - date '2026-07-02') then
      raise exception 'T19 fail: days_open_real=% expected=%',
        v_days, (current_date - date '2026-07-02');
    end if;

    -- with occurred set
    select days_open_real into v_days
    from public.monthly_plan_constraints_dashboard_v2
    where constraint_id = v_open2;
    if v_days <> (current_date - date '2026-07-01') then
      raise exception 'T19b fail: days_open_real=%', v_days;
    end if;

    -- =========================================================================
    -- T20 overdue / control computed fields + effective_deadline_status
    -- =========================================================================
    -- open2 target 2026-07-05 and next_control 2026-07-04 are in the past
    if not exists (
      select 1
      from public.monthly_plan_constraints_dashboard_v2 d
      where d.constraint_id = v_open2
        and d.is_deadline_overdue = true
        and d.is_next_control_overdue = true
        and d.effective_deadline_status = 'OVERDUE'
        and d.deadline_days_overdue = (current_date - date '2026-07-05')
    ) then
      raise exception 'T20 fail: overdue/control fields mismatch for open2';
    end if;

    if not exists (
      select 1
      from public.monthly_plan_constraints_dashboard_v2 d
      where d.constraint_id = v_resolved
        and d.effective_deadline_status = 'RESOLVED'
        and d.is_deadline_overdue = false
    ) then
      raise exception 'T20b fail: resolved effective status';
    end if;
  else
    raise notice 'T19/T20 skipped: dashboard_v2 missing';
  end if;

  -- IN_PROGRESS update allowed
  v_res2 := public.update_monthly_plan_constraint(
    v_prog,
    'R2 Tester',
    'IN_PROGRESS patch',
    jsonb_build_object('deadline_status', 'REQUESTED')
  );
  if v_res2->>'status' <> 'updated' then
    raise exception 'T1b fail: IN_PROGRESS update status=%', v_res2->>'status';
  end if;

  -- resolve basis via evidence payload (signature unchanged)
  if to_regprocedure(
    'public.resolve_monthly_plan_constraint(uuid,date,text,text,jsonb)'
  ) is not null then
    v_res := public.resolve_monthly_plan_constraint(
      v_open2,
      date '2026-08-06',
      'Снято по письму',
      'R2 Closer',
      jsonb_build_object('resolution_basis', 'Письмо Заказчика №12')
    );
    if v_res->>'status' <> 'resolved' then
      raise exception 'resolve-basis fail: status=%', v_res->>'status';
    end if;
    select * into v_row from public.monthly_plan_constraints where constraint_id = v_open2;
    if v_row.resolution_basis <> 'Письмо Заказчика №12' then
      raise exception 'resolve-basis fail: basis=%', v_row.resolution_basis;
    end if;
  end if;

  raise notice 'TEST_REG_R2: all assertions passed (will ROLLBACK)';
end $$;

-- T18 ROLLBACK cleanup
rollback;
