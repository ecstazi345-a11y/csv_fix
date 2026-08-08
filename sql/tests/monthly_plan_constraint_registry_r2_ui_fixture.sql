-- =============================================================================
-- UI E2E fixture: monthly_plan_constraint registry R2 UPDATE (TEST ONLY)
-- =============================================================================
-- File:   sql/tests/monthly_plan_constraint_registry_r2_ui_fixture.sql
-- Purpose: insert reversible TEST_REG_R2 / test-r2-ui-2026 rows for page 24
--          update-form UI E2E (OPEN / IN_PROGRESS).
--
-- SAFETY:
--   - Only TEST_REG_R2 / test-r2-ui-2026 / fixed cccccccc-… UUIDs
--   - Does NOT touch monthly_plan_lines_v2
--   - Does NOT touch passport tables
--   - Does NOT touch product project_code (PRJ_*)
--
-- Run manually in SQL Editor AFTER user confirmation.
-- Pair with: sql/tests/monthly_plan_constraint_registry_r2_ui_cleanup.sql
-- =============================================================================

-- 1) Pre-clean exact test UUIDs / TEST_REG_R2 slice only
delete from public.monthly_plan_constraints
where constraint_id in (
    'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid,
    'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid
)
or (
    project_code = 'TEST_REG_R2'
    and month_key = 'test-r2-ui-2026'
);

-- 2) Insert 2 open constraints for update UI (events initial = 0)
insert into public.monthly_plan_constraints (
    constraint_id,
    line_id,
    project_code,
    month_key,
    facility_building,
    construction_discipline,
    boq_code,
    boq_name,
    gate_layer,
    responsible_department,
    check_name,
    check_status,
    resolution_status,
    block_reason,
    root_cause,
    owner_name,
    problem_owner,
    subcontractor_coordinator,
    constraint_category,
    constraint_priority,
    problem_description,
    problem_impact,
    required_action,
    deadline_status,
    deadline_source,
    constraint_occurred_at,
    target_resolution_date,
    next_control_date,
    value_at_risk,
    constraint_created_at,
    created_by,
    updated_by,
    last_action_at
) values
(
    'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid,
    'cccccccc-cccc-cccc-cccc-cccccccc1001'::uuid,
    'TEST_REG_R2',
    'test-r2-ui-2026',
    'TEST-R2-FACILITY',
    'TEST-R2-DISCIPLINE',
    'BOQ-TEST-R2-001',
    'Тестовое ограничение R2 UI #1',
    'EXECUTABILITY',
    'МТО',
    'Материалы и оборудование',
    'HOLD',
    'OPEN',
    'Тестовое R2 ограничение',
    'Тестовое R2 ограничение',
    'TEST_EXECUTOR',
    'TEST_OWNER',
    'TEST_COORD',
    'Документы',
    'NORMAL',
    'Описание проблемы R2 #1',
    'Последствия R2 #1',
    'Обновить через UI форму',
    'NOT_SET',
    null,
    current_date - 5,
    current_date + 7,
    current_date + 2,
    1500,
    now(),
    'TEST_FIXTURE_R2',
    'TEST_FIXTURE_R2',
    now()
),
(
    'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid,
    'cccccccc-cccc-cccc-cccc-cccccccc1001'::uuid,
    'TEST_REG_R2',
    'test-r2-ui-2026',
    'TEST-R2-FACILITY',
    'TEST-R2-DISCIPLINE',
    'BOQ-TEST-R2-001',
    'Тестовое ограничение R2 UI #2',
    'EXECUTABILITY',
    'ПТО',
    'Проектная готовность',
    'WARNING',
    'IN_PROGRESS',
    'Тестовое R2 ограничение #2',
    'Тестовое R2 ограничение #2',
    'TEST_EXECUTOR_2',
    'TEST_OWNER_2',
    null,
    'Проект',
    'HIGH',
    'Описание проблемы R2 #2',
    'Последствия R2 #2',
    'Проверить обновление IN_PROGRESS',
    'ESTIMATED',
    'SUBCONTRACTOR_ESTIMATE',
    current_date - 10,
    current_date + 3,
    null,
    1500,
    now(),
    'TEST_FIXTURE_R2',
    'TEST_FIXTURE_R2',
    now()
);

-- 3) Post-check fixture
select count(*) as test_r2_constraints
from public.monthly_plan_constraints
where project_code = 'TEST_REG_R2'
  and month_key = 'test-r2-ui-2026';

select count(*) as test_r2_events
from public.monthly_plan_constraint_events
where project_code = 'TEST_REG_R2'
   or constraint_id in (
        'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid,
        'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid
      );

-- Expect: test_r2_constraints = 2, test_r2_events = 0
