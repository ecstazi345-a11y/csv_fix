-- =============================================================================
-- Tests: monthly_plan_constraint_registry_r1
-- =============================================================================
-- File:   sql/tests/monthly_plan_constraint_registry_r1_tests.sql
-- Deploy: run ONLY on sandbox / local Postgres AFTER applying
--         sql/monthly_plan_constraint_registry_r1.sql
-- DO NOT run on production.
--
-- All fixtures run inside a single transaction and ROLLBACK.
-- Requires: monthly_plan_constraints (+ R1 columns), resolve RPC, events table.
-- =============================================================================

begin;

do $$
declare
  v_line uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0001'::uuid;
  v_hold uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1001'::uuid;
  v_hold2 uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1002'::uuid;
  v_warn uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1003'::uuid;
  v_wait uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1004'::uuid;
  v_pass_u uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1005'::uuid;
  v_pass_p uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1006'::uuid;
  v_pass_m uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1007'::uuid;
  v_pass_h uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1008'::uuid;
  v_pass_q uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1009'::uuid;
  v_pass_k uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1010'::uuid;
  v_pass_r uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1011'::uuid;
  v_cancel uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1012'::uuid;
  v_line_ready uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0002'::uuid;
  v_line_block uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0003'::uuid;
  v_line_risk uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0004'::uuid;
  v_line_wait uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0005'::uuid;
  v_line_cancel uuid := 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0006'::uuid;

  v_res jsonb;
  v_res2 jsonb;
  v_event_count integer;
  v_event_count2 integer;
  v_passport_before integer;
  v_passport_after integer;
  v_ok boolean;
  v_exc text;
begin
  -- Preconditions
  if to_regclass('public.monthly_plan_constraint_events') is null then
    raise exception 'TEST ABORT: events table missing — apply registry_r1 migration first';
  end if;
  if to_regprocedure(
    'public.resolve_monthly_plan_constraint(uuid,date,text,text,jsonb)'
  ) is null then
    raise exception 'TEST ABORT: resolve RPC missing — apply registry_r1 migration first';
  end if;

  -- Snapshot passport row count (must be unchanged by resolve)
  select count(*)::integer into v_passport_before
  from public.monthly_plan_passports;

  -- -------------------------------------------------------------------------
  -- Fixtures: delete any leftover test ids (safe inside txn)
  -- -------------------------------------------------------------------------
  delete from public.monthly_plan_constraints
  where constraint_id in (
    v_hold, v_hold2, v_warn, v_wait,
    v_pass_u, v_pass_p, v_pass_m, v_pass_h, v_pass_q, v_pass_k, v_pass_r,
    v_cancel
  )
  or line_id in (v_line, v_line_ready, v_line_block, v_line_risk, v_line_wait, v_line_cancel);

  -- Helper insert function via repeated inserts
  -- Line READY: 6 PASS + 1 HOLD (to resolve)
  insert into public.monthly_plan_constraints (
    constraint_id, line_id, project_code, month_key,
    facility_building, construction_discipline, boq_code, boq_name,
    gate_layer, responsible_department, check_name,
    check_status, resolution_status, block_reason, root_cause,
    owner_name, problem_owner, required_action, value_at_risk
  ) values
  (v_pass_u, v_line_ready, 'TEST_REG', 'test-2026', 'T', 'D', 'BOQ-R', 'Ready line',
   'EXECUTABILITY', 'Участок', 'Фронт физически открыт', 'PASS', 'RESOLVED', null, null, 'A', null, null, 0),
  (v_pass_p, v_line_ready, 'TEST_REG', 'test-2026', 'T', 'D', 'BOQ-R', 'Ready line',
   'EXECUTABILITY', 'ПТО', 'РД / IWP / исполнительность', 'PASS', 'RESOLVED', null, null, 'A', null, null, 0),
  (v_hold, v_line_ready, 'TEST_REG', 'test-2026', 'T', 'D', 'BOQ-R', 'Ready line',
   'EXECUTABILITY', 'МТО', 'Материалы и оборудование', 'HOLD', 'OPEN',
   'МТР не поставлены', 'МТР не поставлены', 'МТО Иванов', 'Заказчик', 'Поставить МТР', 100000),
  (v_pass_h, v_line_ready, 'TEST_REG', 'test-2026', 'T', 'D', 'BOQ-R', 'Ready line',
   'EXECUTABILITY', 'ОТиТБ', 'Наряды / безопасность', 'PASS', 'RESOLVED', null, null, 'A', null, null, 0),
  (v_pass_q, v_line_ready, 'TEST_REG', 'test-2026', 'T', 'D', 'BOQ-R', 'Ready line',
   'EXECUTABILITY', 'QAQC', 'Контроль качества / приёмка', 'PASS', 'RESOLVED', null, null, 'A', null, null, 0),
  (v_pass_k, v_line_ready, 'TEST_REG', 'test-2026', 'T', 'D', 'BOQ-R', 'Ready line',
   'ACCEPTABILITY', 'Коммерческий отдел', 'Возможность предъявления', 'PASS', 'RESOLVED', null, null, 'A', null, null, 0),
  (v_pass_r, v_line_ready, 'TEST_REG', 'test-2026', 'T', 'D', 'BOQ-R', 'Ready line',
   'CREW_ECONOMICS', 'Руководство', 'Экономика звена', 'PASS', 'RESOLVED', null, null, 'A', null, null, 0);

  -- =========================================================================
  -- 1) HOLD → resolve → PASS + READY (all 7 depts present, others PASS)
  -- =========================================================================
  v_res := public.resolve_monthly_plan_constraint(
    v_hold,
    date '2026-08-04',
    'МТР поставлены, комплект подтверждён',
    'МТО Тестов',
    '{"note":"delivery confirmed"}'::jsonb
  );

  if v_res->>'status' <> 'resolved' then
    raise exception 'T1 fail: status=%', v_res->>'status';
  end if;
  if v_res->>'new_check_status' <> 'PASS' then
    raise exception 'T1 fail: new_check_status=%', v_res->>'new_check_status';
  end if;
  if v_res->>'new_resolution_status' <> 'RESOLVED' then
    raise exception 'T1 fail: new_resolution_status=%', v_res->>'new_resolution_status';
  end if;
  if v_res#>>'{line_summary,admission_outcome}' <> 'READY' then
    raise exception 'T1 fail: outcome=% summary=%',
      v_res#>>'{line_summary,admission_outcome}', v_res->'line_summary';
  end if;
  if (v_res->>'actual_resolution_date')::date <> date '2026-08-04' then
    raise exception 'T1 fail: actual_resolution_date';
  end if;

  select count(*) into v_event_count
  from public.monthly_plan_constraint_events
  where constraint_id = v_hold and event_type = 'RESOLVED';
  if v_event_count <> 1 then
    raise exception 'T1/T14 fail: expected 1 RESOLVED event, got %', v_event_count;
  end if;

  if not exists (
    select 1 from public.monthly_plan_constraint_events e
    where e.constraint_id = v_hold
      and e.old_check_status = 'HOLD'
      and e.new_check_status = 'PASS'
      and e.old_resolution_status = 'OPEN'
      and e.new_resolution_status = 'RESOLVED'
      and e.event_payload ? 'note'
  ) then
    raise exception 'T14 fail: event old/new/payload mismatch';
  end if;

  -- =========================================================================
  -- 6+7) Idempotent re-resolve: already_resolved, no second event
  -- =========================================================================
  v_res2 := public.resolve_monthly_plan_constraint(
    v_hold,
    date '2026-08-05',
    'повтор',
    'МТО Тестов',
    null
  );
  if v_res2->>'status' <> 'already_resolved' then
    raise exception 'T6 fail: status=%', v_res2->>'status';
  end if;
  -- actual date must remain original
  if (v_res2->>'actual_resolution_date')::date <> date '2026-08-04' then
    raise exception 'T6 fail: actual_resolution_date changed on idempotent call';
  end if;

  select count(*) into v_event_count2
  from public.monthly_plan_constraint_events
  where constraint_id = v_hold and event_type = 'RESOLVED';
  if v_event_count2 <> 1 then
    raise exception 'T7 fail: second RESOLVED event created (% )', v_event_count2;
  end if;

  -- =========================================================================
  -- 2) HOLD resolve, other HOLD remains → BLOCKED
  -- =========================================================================
  delete from public.monthly_plan_constraints where line_id = v_line_block;
  insert into public.monthly_plan_constraints (
    constraint_id, line_id, project_code, month_key, boq_code,
    gate_layer, responsible_department, check_name,
    check_status, resolution_status, block_reason, owner_name
  ) values
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee2001'::uuid, v_line_block, 'TEST_REG', 'test-2026', 'BOQ-B',
   'EXECUTABILITY', 'МТО', 'Материалы и оборудование', 'HOLD', 'OPEN', 'МТР', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee2002'::uuid, v_line_block, 'TEST_REG', 'test-2026', 'BOQ-B',
   'EXECUTABILITY', 'ПТО', 'РД / IWP / исполнительность', 'HOLD', 'OPEN', 'РД', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee2003'::uuid, v_line_block, 'TEST_REG', 'test-2026', 'BOQ-B',
   'EXECUTABILITY', 'Участок', 'Фронт физически открыт', 'PASS', 'RESOLVED', null, 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee2004'::uuid, v_line_block, 'TEST_REG', 'test-2026', 'BOQ-B',
   'EXECUTABILITY', 'ОТиТБ', 'Наряды / безопасность', 'PASS', 'RESOLVED', null, 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee2005'::uuid, v_line_block, 'TEST_REG', 'test-2026', 'BOQ-B',
   'EXECUTABILITY', 'QAQC', 'Контроль качества / приёмка', 'PASS', 'RESOLVED', null, 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee2006'::uuid, v_line_block, 'TEST_REG', 'test-2026', 'BOQ-B',
   'ACCEPTABILITY', 'Коммерческий отдел', 'Возможность предъявления', 'PASS', 'RESOLVED', null, 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee2007'::uuid, v_line_block, 'TEST_REG', 'test-2026', 'BOQ-B',
   'CREW_ECONOMICS', 'Руководство', 'Экономика звена', 'PASS', 'RESOLVED', null, 'A');

  v_res := public.resolve_monthly_plan_constraint(
    'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee2001'::uuid,
    date '2026-08-04',
    'МТО снято',
    'tester',
    null
  );
  if v_res#>>'{line_summary,admission_outcome}' <> 'BLOCKED' then
    raise exception 'T2 fail: outcome=%', v_res#>>'{line_summary,admission_outcome}';
  end if;
  if jsonb_array_length(v_res->'remaining_blockers') < 1 then
    raise exception 'T13 fail: remaining_blockers empty on BLOCKED';
  end if;
  if not exists (
    select 1
    from jsonb_array_elements(v_res->'remaining_blockers') x
    where x->>'responsible_department' = 'ПТО'
      and x->>'check_status' = 'HOLD'
  ) then
    raise exception 'T13 fail: PTO HOLD missing from remaining_blockers';
  end if;

  -- =========================================================================
  -- 3) HOLD resolve, WARNING remains → READY_WITH_RISK
  -- =========================================================================
  delete from public.monthly_plan_constraints where line_id = v_line_risk;
  insert into public.monthly_plan_constraints (
    constraint_id, line_id, project_code, month_key, boq_code,
    gate_layer, responsible_department, check_name,
    check_status, resolution_status, owner_name
  ) values
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee3001'::uuid, v_line_risk, 'TEST_REG', 'test-2026', 'BOQ-W',
   'EXECUTABILITY', 'МТО', 'Материалы и оборудование', 'HOLD', 'OPEN', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee3002'::uuid, v_line_risk, 'TEST_REG', 'test-2026', 'BOQ-W',
   'EXECUTABILITY', 'ПТО', 'РД / IWP / исполнительность', 'WARNING', 'IN_PROGRESS', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee3003'::uuid, v_line_risk, 'TEST_REG', 'test-2026', 'BOQ-W',
   'EXECUTABILITY', 'Участок', 'Фронт физически открыт', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee3004'::uuid, v_line_risk, 'TEST_REG', 'test-2026', 'BOQ-W',
   'EXECUTABILITY', 'ОТиТБ', 'Наряды / безопасность', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee3005'::uuid, v_line_risk, 'TEST_REG', 'test-2026', 'BOQ-W',
   'EXECUTABILITY', 'QAQC', 'Контроль качества / приёмка', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee3006'::uuid, v_line_risk, 'TEST_REG', 'test-2026', 'BOQ-W',
   'ACCEPTABILITY', 'Коммерческий отдел', 'Возможность предъявления', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee3007'::uuid, v_line_risk, 'TEST_REG', 'test-2026', 'BOQ-W',
   'CREW_ECONOMICS', 'Руководство', 'Экономика звена', 'PASS', 'RESOLVED', 'A');

  v_res := public.resolve_monthly_plan_constraint(
    'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee3001'::uuid,
    date '2026-08-04', 'ok', 'tester', null
  );
  if v_res#>>'{line_summary,admission_outcome}' <> 'READY_WITH_RISK' then
    raise exception 'T3 fail: outcome=%', v_res#>>'{line_summary,admission_outcome}';
  end if;

  -- =========================================================================
  -- 4) WAITING remains → WAITING
  -- =========================================================================
  delete from public.monthly_plan_constraints where line_id = v_line_wait;
  insert into public.monthly_plan_constraints (
    constraint_id, line_id, project_code, month_key, boq_code,
    gate_layer, responsible_department, check_name,
    check_status, resolution_status, owner_name
  ) values
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee4001'::uuid, v_line_wait, 'TEST_REG', 'test-2026', 'BOQ-Q',
   'EXECUTABILITY', 'МТО', 'Материалы и оборудование', 'HOLD', 'OPEN', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee4002'::uuid, v_line_wait, 'TEST_REG', 'test-2026', 'BOQ-Q',
   'EXECUTABILITY', 'ПТО', 'РД / IWP / исполнительность', 'ОЖИДАЕТ', 'OPEN', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee4003'::uuid, v_line_wait, 'TEST_REG', 'test-2026', 'BOQ-Q',
   'EXECUTABILITY', 'Участок', 'Фронт физически открыт', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee4004'::uuid, v_line_wait, 'TEST_REG', 'test-2026', 'BOQ-Q',
   'EXECUTABILITY', 'ОТиТБ', 'Наряды / безопасность', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee4005'::uuid, v_line_wait, 'TEST_REG', 'test-2026', 'BOQ-Q',
   'EXECUTABILITY', 'QAQC', 'Контроль качества / приёмка', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee4006'::uuid, v_line_wait, 'TEST_REG', 'test-2026', 'BOQ-Q',
   'ACCEPTABILITY', 'Коммерческий отдел', 'Возможность предъявления', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee4007'::uuid, v_line_wait, 'TEST_REG', 'test-2026', 'BOQ-Q',
   'CREW_ECONOMICS', 'Руководство', 'Экономика звена', 'PASS', 'RESOLVED', 'A');

  v_res := public.resolve_monthly_plan_constraint(
    'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee4001'::uuid,
    date '2026-08-04', 'ok', 'tester', null
  );
  if v_res#>>'{line_summary,admission_outcome}' <> 'WAITING' then
    raise exception 'T4 fail: outcome=%', v_res#>>'{line_summary,admission_outcome}';
  end if;

  -- =========================================================================
  -- 5 already covered by T1 READY
  -- Anti false READY: single resolved row without all depts → WAITING
  -- =========================================================================
  delete from public.monthly_plan_constraints
  where constraint_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee5001'::uuid
     or line_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0007'::uuid;

  insert into public.monthly_plan_constraints (
    constraint_id, line_id, project_code, month_key, boq_code,
    gate_layer, responsible_department, check_name,
    check_status, resolution_status, owner_name
  ) values (
    'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee5001'::uuid,
    'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0007'::uuid,
    'TEST_REG', 'test-2026', 'BOQ-1',
    'EXECUTABILITY', 'МТО', 'Материалы и оборудование',
    'HOLD', 'OPEN', 'A'
  );

  v_res := public.resolve_monthly_plan_constraint(
    'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee5001'::uuid,
    date '2026-08-04', 'ok', 'tester', null
  );
  if v_res#>>'{line_summary,admission_outcome}' <> 'WAITING' then
    raise exception 'T5b anti-false-READY fail: outcome=% (expected WAITING)',
      v_res#>>'{line_summary,admission_outcome}';
  end if;
  if (v_res#>>'{line_summary,missing_department_count}')::int < 1 then
    raise exception 'T5b fail: missing_department_count should be > 0';
  end if;

  -- =========================================================================
  -- 8) unknown constraint_id → exception
  -- =========================================================================
  begin
    perform public.resolve_monthly_plan_constraint(
      'ffffffff-ffff-ffff-ffff-ffffffffffff'::uuid,
      date '2026-08-04', 'x', 'y', null
    );
    raise exception 'T8 fail: expected exception for missing id';
  exception
    when others then
      if sqlerrm not like '%not found%' then
        raise exception 'T8 fail: unexpected error: %', sqlerrm;
      end if;
  end;

  -- =========================================================================
  -- 9) empty closed_by
  -- =========================================================================
  begin
    perform public.resolve_monthly_plan_constraint(
      v_hold, date '2026-08-04', 'comment', '  ', null
    );
    raise exception 'T9 fail: expected exception for empty closed_by';
  exception
    when others then
      if sqlerrm not like '%p_closed_by%' then
        raise exception 'T9 fail: unexpected error: %', sqlerrm;
      end if;
  end;

  -- =========================================================================
  -- 10) empty comment
  -- =========================================================================
  begin
    perform public.resolve_monthly_plan_constraint(
      v_hold, date '2026-08-04', '   ', 'user', null
    );
    raise exception 'T10 fail: expected exception for empty comment';
  exception
    when others then
      if sqlerrm not like '%p_resolution_comment%' then
        raise exception 'T10 fail: unexpected error: %', sqlerrm;
      end if;
  end;

  -- =========================================================================
  -- 11) null actual date
  -- =========================================================================
  begin
    perform public.resolve_monthly_plan_constraint(
      v_hold, null, 'comment', 'user', null
    );
    raise exception 'T11 fail: expected exception for null date';
  exception
    when others then
      if sqlerrm not like '%p_actual_resolution_date%' then
        raise exception 'T11 fail: unexpected error: %', sqlerrm;
      end if;
  end;

  -- =========================================================================
  -- 12) CANCELLED does not block
  -- =========================================================================
  delete from public.monthly_plan_constraints where line_id = v_line_cancel;
  insert into public.monthly_plan_constraints (
    constraint_id, line_id, project_code, month_key, boq_code,
    gate_layer, responsible_department, check_name,
    check_status, resolution_status, owner_name
  ) values
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee6001'::uuid, v_line_cancel, 'TEST_REG', 'test-2026', 'BOQ-C',
   'EXECUTABILITY', 'МТО', 'Материалы и оборудование', 'HOLD', 'OPEN', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee6002'::uuid, v_line_cancel, 'TEST_REG', 'test-2026', 'BOQ-C',
   'EXECUTABILITY', 'ПТО', 'РД / IWP / исполнительность', 'HOLD', 'CANCELLED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee6003'::uuid, v_line_cancel, 'TEST_REG', 'test-2026', 'BOQ-C',
   'EXECUTABILITY', 'Участок', 'Фронт физически открыт', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee6004'::uuid, v_line_cancel, 'TEST_REG', 'test-2026', 'BOQ-C',
   'EXECUTABILITY', 'ОТиТБ', 'Наряды / безопасность', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee6005'::uuid, v_line_cancel, 'TEST_REG', 'test-2026', 'BOQ-C',
   'EXECUTABILITY', 'QAQC', 'Контроль качества / приёмка', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee6006'::uuid, v_line_cancel, 'TEST_REG', 'test-2026', 'BOQ-C',
   'ACCEPTABILITY', 'Коммерческий отдел', 'Возможность предъявления', 'PASS', 'RESOLVED', 'A'),
  ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee6007'::uuid, v_line_cancel, 'TEST_REG', 'test-2026', 'BOQ-C',
   'CREW_ECONOMICS', 'Руководство', 'Экономика звена', 'PASS', 'RESOLVED', 'A');

  v_res := public.resolve_monthly_plan_constraint(
    'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee6001'::uuid,
    date '2026-08-04', 'ok', 'tester', null
  );
  if v_res#>>'{line_summary,admission_outcome}' <> 'READY' then
    raise exception 'T12 fail: CANCELLED should not block, got %',
      v_res#>>'{line_summary,admission_outcome}';
  end if;

  -- =========================================================================
  -- 15) Passport tables unchanged
  -- =========================================================================
  select count(*)::integer into v_passport_after
  from public.monthly_plan_passports;
  if v_passport_after <> v_passport_before then
    raise exception 'T15 fail: monthly_plan_passports row count changed';
  end if;

  raise notice 'ALL monthly_plan_constraint_registry_r1 TESTS PASSED';
end $$;

rollback;
