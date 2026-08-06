-- =============================================================================
-- Tests: monthly_plan_management_decisions_r2_optional_fields
-- =============================================================================
-- File:   sql/tests/monthly_plan_management_decisions_r2_optional_fields_tests.sql
-- Deploy: run ONLY on sandbox / local Postgres AFTER applying
--         sql/monthly_plan_management_decisions_r2_optional_fields.sql
-- DO NOT run on production.
--
-- All fixtures use project_code = TEST_MGMT and synthetic UUIDs.
-- BEGIN / ROLLBACK — no persistent writes.
-- =============================================================================

begin;

do $$
declare
  v_line uuid := 'bbbbbbbb-cccc-dddd-eeee-00000000a201'::uuid;

  v_res jsonb;
  v_cnt integer;
  v_decision text;
  v_comment text;
  v_deadline text;
  v_passport_before integer;
  v_passport_after integer;
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

  select count(*)::integer into v_passport_before
  from public.monthly_plan_passports;
  select count(*)::integer into v_constraints_before
  from public.monthly_plan_constraints;

  delete from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
     or plan_line_id = v_line;

  -- =========================================================================
  -- T1 INCLUDE without deadline/comment → success
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line,
    'INCLUDE',
    'Tester R2',
    jsonb_build_object(
      'boq_code', 'TEST-BOQ-R2',
      'decision_basis', 'TEST_OPTIONAL_FIELDS_INCLUDE',
      'responsible_person', 'TEST_OPTIONAL_FIELDS',
      'decision_comment', '',
      'review_deadline', ''
    )
  );
  if v_res->>'status' <> 'inserted' or v_res->>'new_decision' <> 'INCLUDE' then
    raise exception 'T1 fail: %', v_res;
  end if;
  select decision_comment, review_deadline
    into v_comment, v_deadline
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and plan_line_id = v_line;
  if v_comment is not null or v_deadline is not null then
    raise exception 'T1 fail: comment=% deadline=%', v_comment, v_deadline;
  end if;

  -- =========================================================================
  -- T2 DEFER without deadline/comment → success
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line,
    'DEFER',
    'Tester R2',
    jsonb_build_object(
      'decision_basis', 'TEST_OPTIONAL_FIELDS_DEFER',
      'responsible_person', 'TEST_OPTIONAL_FIELDS'
    )
  );
  if v_res->>'new_decision' <> 'DEFER' then
    raise exception 'T2 fail: %', v_res;
  end if;

  -- =========================================================================
  -- T3 EXCLUDE without deadline/comment → success
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line,
    'EXCLUDE',
    'Tester R2',
    jsonb_build_object(
      'decision_basis', 'TEST_OPTIONAL_FIELDS_EXCLUDE',
      'responsible_person', 'TEST_OPTIONAL_FIELDS'
    )
  );
  if v_res->>'new_decision' <> 'EXCLUDE' then
    raise exception 'T3 fail: %', v_res;
  end if;

  -- =========================================================================
  -- T4 INCLUDE_RISK without risk protocol → fail
  -- =========================================================================
  begin
    perform public.apply_monthly_plan_management_decision(
      'TEST_MGMT',
      'test-2026-08',
      v_line,
      'INCLUDE_RISK',
      'Tester R2',
      jsonb_build_object(
        'decision_basis', 'TEST_OPTIONAL_FIELDS_RISK',
        'responsible_person', 'TEST_OPTIONAL_FIELDS'
      )
    );
    raise exception 'T4 fail: INCLUDE_RISK without risk protocol accepted';
  exception
    when others then
      if sqlerrm not like '%risk_description is required%' then
        raise;
      end if;
  end;

  -- =========================================================================
  -- T5 INCLUDE_RISK with risk protocol, without comment/deadline → success
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line,
    'INCLUDE_RISK',
    'Tester R2',
    jsonb_build_object(
      'decision_basis', 'TEST_OPTIONAL_FIELDS_RISK',
      'responsible_person', 'TEST_OPTIONAL_FIELDS',
      'risk_description', 'R2 risk desc',
      'risk_impact', 'R2 impact',
      'risk_mitigation_owner', 'R2 owner',
      'risk_mitigation_deadline', '2026-09-01',
      'risk_acceptance_basis', 'R2 basis',
      'risk_manager_comment', 'R2 manager comment'
    )
  );
  if v_res->>'new_decision' <> 'INCLUDE_RISK' then
    raise exception 'T5 fail: %', v_res;
  end if;
  select decision_comment, review_deadline
    into v_comment, v_deadline
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and plan_line_id = v_line;
  if v_comment is not null or v_deadline is not null then
    raise exception 'T5 fail: comment=% deadline=%', v_comment, v_deadline;
  end if;

  -- =========================================================================
  -- T6 placeholder «—» not stored
  -- =========================================================================
  v_res := public.apply_monthly_plan_management_decision(
    'TEST_MGMT',
    'test-2026-08',
    v_line,
    'INCLUDE',
    'Tester R2',
    jsonb_build_object(
      'decision_basis', 'TEST_OPTIONAL_FIELDS_PLACEHOLDER',
      'responsible_person', 'TEST_OPTIONAL_FIELDS',
      'decision_comment', '—',
      'review_deadline', '-'
    )
  );
  select decision_comment, review_deadline
    into v_comment, v_deadline
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and plan_line_id = v_line;
  if v_comment is not null or v_deadline is not null then
    raise exception 'T6 fail: placeholder stored comment=% deadline=%',
      v_comment, v_deadline;
  end if;

  -- =========================================================================
  -- T7 row count per grain = 1 after decision changes
  -- =========================================================================
  select count(*)::integer into v_cnt
  from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and month_key = 'test-2026-08'
    and plan_line_id = v_line;
  if v_cnt <> 1 then
    raise exception 'T7 fail: row count=%', v_cnt;
  end if;

  -- =========================================================================
  -- T8 passport / constraints unchanged
  -- =========================================================================
  select count(*)::integer into v_passport_after
  from public.monthly_plan_passports;
  select count(*)::integer into v_constraints_after
  from public.monthly_plan_constraints;
  if v_passport_after <> v_passport_before
     or v_constraints_after <> v_constraints_before then
    raise exception 'T8 fail: passport %→% constraints %→%',
      v_passport_before, v_passport_after,
      v_constraints_before, v_constraints_after;
  end if;

  delete from public.monthly_plan_management_decisions
  where project_code = 'TEST_MGMT'
    and plan_line_id = v_line;

  raise notice 'monthly_plan_management_decisions_r2_optional_fields_tests: ALL OK';
end $$;

rollback;
