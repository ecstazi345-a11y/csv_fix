-- =============================================================================
-- Tests: monthly_plan_management_decisions_r1
-- =============================================================================
-- File:   sql/tests/monthly_plan_management_decisions_r1_tests.sql
-- Deploy: run ONLY on sandbox / local Postgres AFTER applying
--         sql/monthly_plan_management_decisions_r1.sql
-- DO NOT run on production.
--
-- All fixtures use project_code = TEST_MGMT and synthetic UUIDs.
-- No product project_code / real plan_line_id.
-- No passport / constraints writes.
-- Single transaction + ROLLBACK.
-- =============================================================================

begin;

do $$
declare
  v_line_1 uuid := 'bbbbbbbb-cccc-dddd-eeee-000000000001'::uuid;
  v_line_2 uuid := 'bbbbbbbb-cccc-dddd-eeee-000000000002'::uuid;
  v_line_3 uuid := 'bbbbbbbb-cccc-dddd-eeee-000000000003'::uuid;

  v_res jsonb;
  v_res2 jsonb;
  v_cnt integer;
  v_active_cnt integer;
  v_decision text;
  v_status text;
  v_override boolean;
  v_by text;
  v_decided_at timestamptz;
  v_decided_at2 timestamptz;
  v_passport_before integer;
  v_passport_after integer;
  v_passport_lines_before integer;
  v_passport_lines_after integer;
  v_constraints_before integer;
  v_constraints_after integer;
begin
  if to_regclass('public.monthly_plan_management_decisions') is null then
    raise exception
      'TEST ABORT: table missing — apply monthly_plan_management_decisions_r1.sql first';
  end if;
  if to_regprocedure(
    'public.apply_monthly_plan_management_decision(text,text,uuid,text,text,jsonb)'
  ) is null then
    raise exception 'TEST ABORT: apply RPC missing';
  end if;
  if to_regprocedure(
    'public.cancel_monthly_plan_management_decision(text,text,uuid,text,text)'
  ) is null then
    raise exception 'TEST ABORT: cancel RPC missing';
  end if;

  select count(*)::integer into v_passport_before
  from public.monthly_plan_passports;
  select count(*)::integer into v_passport_lines_before
  from public.monthly_plan_passport_lines;
  select count(*)::integer into v_constraints_before
  from public.monthly_plan_constraints;

  delete from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
     or plan_line_id in (v_line_1, v_line_2, v_line_3);

  -- =========================================================================
  -- T1 INSERT INCLUDE
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line_1,
    'INCLUDE',
    'Tester A',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-01',
      'boq_name', 'Test include line',
      'admission_outcome_at_decision', 'Допущено',
      'management_override', false,
      'decision_basis', 'Чистый допуск',
      'decision_comment', 'Включаем в драфт',
      'responsible_person', 'Иванов',
      'review_deadline', '2026-08-20'
    )
  );
  if v_res->>'status' <> 'inserted' or v_res->>'new_decision' <> 'INCLUDE' then
    raise exception 'T1 fail: %', v_res;
  end if;

  -- =========================================================================
  -- T2 повторный INCLUDE → 1 строка
  -- =========================================================================
  v_res2 := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line_1,
    'INCLUDE',
    'Tester A',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-01',
      'decision_basis', 'Повтор',
      'decision_comment', 'Тот же INCLUDE',
      'responsible_person', 'Иванов',
      'review_deadline', '2026-08-21',
      'admission_outcome_at_decision', 'Допущено'
    )
  );
  if v_res2->>'status' <> 'updated' then
    raise exception 'T2 fail status: %', v_res2;
  end if;
  select count(*)::integer into v_cnt
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and plan_line_id = v_line_1;
  if v_cnt <> 1 then
    raise exception 'T2 fail: duplicates=%', v_cnt;
  end if;

  -- =========================================================================
  -- T3 INCLUDE → INCLUDE_RISK
  -- =========================================================================
  select decided_at into v_decided_at
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and plan_line_id = v_line_1;

  perform pg_sleep(0.05);

  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line_1,
    'INCLUDE_RISK',
    'Tester B',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-01',
      'admission_outcome_at_decision', 'Заблокировано',
      'management_override', false, -- must be forced true by RPC
      'decision_basis', 'Нужен риск-протокол',
      'decision_comment', 'Принимаем риск',
      'responsible_person', 'Петров',
      'review_deadline', '2026-08-25',
      'risk_description', 'МТР задержаны',
      'risk_impact', 'Сдвиг графика',
      'risk_mitigation_owner', 'МТО',
      'risk_mitigation_deadline', '2026-08-22',
      'risk_acceptance_basis', 'Критичный путь',
      'risk_manager_comment', 'Согласовано руководством',
      'risk_blocker', 'МТО'
    )
  );
  if v_res->>'old_decision' <> 'INCLUDE' or v_res->>'new_decision' <> 'INCLUDE_RISK' then
    raise exception 'T3 fail: %', v_res;
  end if;

  select decision, decision_status, management_override, decided_by, decided_at
    into v_decision, v_status, v_override, v_by, v_decided_at2
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and plan_line_id = v_line_1;

  if v_decision <> 'INCLUDE_RISK' or v_status <> 'ACTIVE' or v_override is not true then
    raise exception 'T3 fail row: decision=% status=% override=%',
      v_decision, v_status, v_override;
  end if;
  if v_by <> 'Tester B' or v_decided_at2 < v_decided_at then
    raise exception 'T3 fail decided_by/at';
  end if;

  -- =========================================================================
  -- T4 INCLUDE_RISK → EXCLUDE
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line_1,
    'EXCLUDE',
    'Tester C',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-01',
      'decision_basis', 'Убрать из драфта',
      'decision_comment', 'Не входит в обязательство',
      'responsible_person', 'Сидоров',
      'review_deadline', '2026-08-30',
      'admission_outcome_at_decision', 'Заблокировано'
    )
  );
  if v_res->>'new_decision' <> 'EXCLUDE' then
    raise exception 'T4 fail: %', v_res;
  end if;
  select count(*)::integer into v_cnt
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT' and plan_line_id = v_line_1
    and month_key = 'test-2026-08';
  if v_cnt <> 1 then
    raise exception 'T4 fail duplicates=%', v_cnt;
  end if;

  -- =========================================================================
  -- T5 EXCLUDE → DEFER
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line_1,
    'DEFER',
    'Tester C',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-01',
      'decision_basis', 'Отложить',
      'decision_comment', 'Ждём данные',
      'responsible_person', 'Сидоров',
      'review_deadline', '2026-09-01',
      'admission_outcome_at_decision', 'Ожидает проверки'
    )
  );
  if v_res->>'old_decision' <> 'EXCLUDE' or v_res->>'new_decision' <> 'DEFER' then
    raise exception 'T5 fail: %', v_res;
  end if;

  -- =========================================================================
  -- T6 CANCEL
  -- =========================================================================
  v_res := public.cancel_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line_1,
    'Tester C',
    'Очистка состава'
  );
  if v_res->>'status' <> 'cancelled' then
    raise exception 'T6 fail: %', v_res;
  end if;
  select decision_status into v_status
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and plan_line_id = v_line_1;
  if v_status <> 'CANCELLED' then
    raise exception 'T6 fail status=%', v_status;
  end if;

  -- =========================================================================
  -- T7 повторный CANCEL — идемпотентность
  -- =========================================================================
  v_res2 := public.cancel_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line_1,
    'Tester C',
    null
  );
  if v_res2->>'status' <> 'already_cancelled' then
    raise exception 'T7 fail: %', v_res2;
  end if;

  -- =========================================================================
  -- T8 CANCELLED → APPLY → ACTIVE
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line_1,
    'INCLUDE',
    'Tester A',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-01',
      'decision_basis', 'Вернули',
      'decision_comment', 'Снова ACTIVE',
      'responsible_person', 'Иванов',
      'review_deadline', '2026-09-05',
      'admission_outcome_at_decision', 'Допущено'
    )
  );
  if v_res->>'status' <> 'updated'
     or v_res->>'new_decision' <> 'INCLUDE'
     or v_res->>'new_decision_status' <> 'ACTIVE' then
    raise exception 'T8 fail: %', v_res;
  end if;

  -- =========================================================================
  -- T9 неизвестный decision → ошибка
  -- =========================================================================
  begin
    perform public.apply_monthly_plan_management_decision(
      'TEST_MGMT', 'test-2026-08', v_line_3, 'READY_WITH_RISK', 'Tester A',
      jsonb_build_object(
        'decision_basis', 'x', 'decision_comment', 'x',
        'responsible_person', 'x', 'review_deadline', 'x'
      )
    );
    raise exception 'T9 fail: invalid decision accepted';
  exception
    when others then
      if sqlerrm not like '%invalid decision%' then
        raise;
      end if;
  end;

  -- =========================================================================
  -- T10 пустой decided_by → ошибка
  -- =========================================================================
  begin
    perform public.apply_monthly_plan_management_decision(
      'TEST_MGMT', 'test-2026-08', v_line_3, 'INCLUDE', '   ',
      jsonb_build_object(
        'decision_basis', 'x', 'decision_comment', 'x',
        'responsible_person', 'x', 'review_deadline', 'x'
      )
    );
    raise exception 'T10 fail: empty decided_by accepted';
  exception
    when others then
      if sqlerrm not like '%decided_by is required%' then
        raise;
      end if;
  end;

  -- =========================================================================
  -- T11 INCLUDE_RISK без risk protocol → ошибка
  -- =========================================================================
  begin
    perform public.apply_monthly_plan_management_decision(
      'TEST_MGMT', 'test-2026-08', v_line_3, 'INCLUDE_RISK', 'Tester A',
      jsonb_build_object(
        'decision_basis', 'x', 'decision_comment', 'x',
        'responsible_person', 'x', 'review_deadline', 'x'
      )
    );
    raise exception 'T11 fail: INCLUDE_RISK without protocol accepted';
  exception
    when others then
      if sqlerrm not like '%risk_description%' then
        raise;
      end if;
  end;

  -- =========================================================================
  -- T12 уникальность — дублей нет (second line + month isolation)
  -- =========================================================================
  perform public.apply_monthly_plan_management_decision(
    'TEST_MGMT', 'test-2026-08', v_line_2, 'INCLUDE_RISK', 'Tester A',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-02',
      'decision_basis', 'risk',
      'decision_comment', 'risk comment',
      'responsible_person', 'Иванов',
      'review_deadline', '2026-09-01',
      'risk_description', 'd',
      'risk_impact', 'i',
      'risk_mitigation_owner', 'o',
      'risk_mitigation_deadline', '2026-09-02',
      'risk_acceptance_basis', 'b',
      'risk_manager_comment', 'c'
    )
  );
  perform public.apply_monthly_plan_management_decision(
    'TEST_MGMT', 'test-2026-09', v_line_1, 'DEFER', 'Tester A',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-01',
      'decision_basis', 'other month',
      'decision_comment', 'ok',
      'responsible_person', 'Иванов',
      'review_deadline', '2026-09-10'
    )
  );

  select count(*)::integer into v_cnt
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT';
  -- line1 aug ACTIVE INCLUDE + line2 aug INCLUDE_RISK + line1 sep DEFER = 3
  if v_cnt <> 3 then
    raise exception 'T12 fail: expected 3 TEST_MGMT rows, got %', v_cnt;
  end if;

  select count(*)::integer into v_cnt
  from (
    select project_code, month_key, plan_line_id
    from public.monthly_plan_management_decisions
    where project_code = 'TEST_MGMT'
    group by 1, 2, 3
    having count(*) > 1
  ) dups;
  if v_cnt <> 0 then
    raise exception 'T12 fail: grain duplicates present';
  end if;

  -- =========================================================================
  -- T13 rehydrate query returns only ACTIVE
  -- =========================================================================
  -- cancel line2 so ACTIVE set shrinks
  perform public.cancel_monthly_plan_management_decision(
    'TEST_MGMT', 'test-2026-08', v_line_2, 'Tester A', 'hide from rehydrate'
  );

  select count(*)::integer into v_active_cnt
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and decision_status = 'ACTIVE';

  if v_active_cnt <> 1 then
    raise exception 'T13 fail: expected 1 ACTIVE in aug, got %', v_active_cnt;
  end if;

  select decision into v_decision
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and decision_status = 'ACTIVE'
    and plan_line_id = v_line_1;
  if v_decision <> 'INCLUDE' then
    raise exception 'T13 fail: unexpected ACTIVE decision=%', v_decision;
  end if;

  -- confirm CANCELLED not returned by ACTIVE filter
  select count(*)::integer into v_cnt
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and decision_status = 'ACTIVE'
    and decision in ('EXCLUDE', 'DEFER');
  if v_cnt <> 0 then
    raise exception 'T13 fail: EXCLUDE/DEFER leaked into ACTIVE rehydrate set';
  end if;

  -- =========================================================================
  -- T14 passport / constraints counts unchanged
  -- =========================================================================
  select count(*)::integer into v_passport_after
  from public.monthly_plan_passports;
  select count(*)::integer into v_passport_lines_after
  from public.monthly_plan_passport_lines;
  select count(*)::integer into v_constraints_after
  from public.monthly_plan_constraints;

  if v_passport_after <> v_passport_before then
    raise exception 'T14 fail: passport count changed % → %',
      v_passport_before, v_passport_after;
  end if;
  if v_passport_lines_after <> v_passport_lines_before then
    raise exception 'T14 fail: passport_lines count changed % → %',
      v_passport_lines_before, v_passport_lines_after;
  end if;
  if v_constraints_after <> v_constraints_before then
    raise exception 'T14 fail: constraints count changed % → %',
      v_constraints_before, v_constraints_after;
  end if;

  raise notice 'monthly_plan_management_decisions_r1_tests: ALL PASSED (T1–T14)';
end $$;

-- T15 ROLLBACK удаляет fixture (transaction ends without commit)
rollback;
