-- =============================================================================
-- UI E2E fixture: monthly_plan_constraint registry (TEST ONLY)
-- =============================================================================
-- File:   sql/tests/monthly_plan_constraint_registry_ui_fixture.sql
-- Purpose: insert reversible TEST_REG / test-2026 rows for page 24 resolve UI.
--
-- SAFETY:
--   - Only TEST_REG / test-2026 / fixed bbbbbbbb-… UUIDs
--   - Does NOT touch monthly_plan_lines_v2
--   - Does NOT touch passport tables
--   - Does NOT touch product project_code (PRJ_*)
--
-- Run manually in SQL Editor AFTER user confirmation.
-- Pair with: sql/tests/monthly_plan_constraint_registry_ui_cleanup.sql
-- =============================================================================

-- 1) Pre-clean exact test UUIDs only (events CASCADE from constraints)
delete from public.monthly_plan_constraints
where constraint_id in (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0002'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0003'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0004'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0005'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0006'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0007'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0008'::uuid
)
or line_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid;

-- 2) Insert 7 constraints for one test line_id
-- Candidate (...0002 / МТО / HOLD) + 6 departments ОЖИДАЕТ
-- After resolving МТО via UI → admission_outcome = WAITING

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
    required_action,
    target_resolution_date,
    value_at_risk,
    constraint_created_at,
    created_by,
    updated_by,
    last_action_at
) values
-- Candidate: МТО HOLD (close this in UI)
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0002'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid,
    'TEST_REG',
    'test-2026',
    'TEST-FACILITY',
    'TEST-DISCIPLINE',
    'BOQ-TEST-E2E-001',
    'Тестовое ограничение E2E',
    'EXECUTABILITY',
    'МТО',
    'Материалы и оборудование',
    'HOLD',
    'OPEN',
    'Тестовое ограничение E2E',
    'Тестовое ограничение E2E',
    'TEST_USER',
    'TEST_OWNER',
    'Подтвердить снятие через UI',
    current_date,
    1000,
    now(),
    'TEST_FIXTURE',
    'TEST_FIXTURE',
    now()
),
-- Участок ОЖИДАЕТ
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0003'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid,
    'TEST_REG',
    'test-2026',
    'TEST-FACILITY',
    'TEST-DISCIPLINE',
    'BOQ-TEST-E2E-001',
    'Тестовое ограничение E2E',
    'EXECUTABILITY',
    'Участок',
    'Фронт физически открыт',
    'ОЖИДАЕТ',
    'OPEN',
    null,
    null,
    null,
    null,
    null,
    null,
    1000,
    now(),
    'TEST_FIXTURE',
    'TEST_FIXTURE',
    now()
),
-- ПТО ОЖИДАЕТ
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0004'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid,
    'TEST_REG',
    'test-2026',
    'TEST-FACILITY',
    'TEST-DISCIPLINE',
    'BOQ-TEST-E2E-001',
    'Тестовое ограничение E2E',
    'EXECUTABILITY',
    'ПТО',
    'РД / IWP / исполнительность',
    'ОЖИДАЕТ',
    'OPEN',
    null,
    null,
    null,
    null,
    null,
    null,
    1000,
    now(),
    'TEST_FIXTURE',
    'TEST_FIXTURE',
    now()
),
-- ОТиТБ ОЖИДАЕТ
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0005'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid,
    'TEST_REG',
    'test-2026',
    'TEST-FACILITY',
    'TEST-DISCIPLINE',
    'BOQ-TEST-E2E-001',
    'Тестовое ограничение E2E',
    'EXECUTABILITY',
    'ОТиТБ',
    'Наряды / безопасность',
    'ОЖИДАЕТ',
    'OPEN',
    null,
    null,
    null,
    null,
    null,
    null,
    1000,
    now(),
    'TEST_FIXTURE',
    'TEST_FIXTURE',
    now()
),
-- QAQC ОЖИДАЕТ
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0006'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid,
    'TEST_REG',
    'test-2026',
    'TEST-FACILITY',
    'TEST-DISCIPLINE',
    'BOQ-TEST-E2E-001',
    'Тестовое ограничение E2E',
    'EXECUTABILITY',
    'QAQC',
    'Контроль качества / приёмка',
    'ОЖИДАЕТ',
    'OPEN',
    null,
    null,
    null,
    null,
    null,
    null,
    1000,
    now(),
    'TEST_FIXTURE',
    'TEST_FIXTURE',
    now()
),
-- Коммерческий отдел ОЖИДАЕТ
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0007'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid,
    'TEST_REG',
    'test-2026',
    'TEST-FACILITY',
    'TEST-DISCIPLINE',
    'BOQ-TEST-E2E-001',
    'Тестовое ограничение E2E',
    'ACCEPTABILITY',
    'Коммерческий отдел',
    'Возможность предъявления',
    'ОЖИДАЕТ',
    'OPEN',
    null,
    null,
    null,
    null,
    null,
    null,
    1000,
    now(),
    'TEST_FIXTURE',
    'TEST_FIXTURE',
    now()
),
-- Руководство ОЖИДАЕТ
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0008'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid,
    'TEST_REG',
    'test-2026',
    'TEST-FACILITY',
    'TEST-DISCIPLINE',
    'BOQ-TEST-E2E-001',
    'Тестовое ограничение E2E',
    'CREW_ECONOMICS',
    'Руководство',
    'Экономика звена',
    'ОЖИДАЕТ',
    'OPEN',
    null,
    null,
    null,
    null,
    null,
    null,
    1000,
    now(),
    'TEST_FIXTURE',
    'TEST_FIXTURE',
    now()
);

-- 3) Verify fixture (read-only checks)
select
    count(*) as inserted_rows,
    count(*) filter (where check_status = 'HOLD') as hold_rows,
    count(*) filter (where check_status = 'ОЖИДАЕТ') as waiting_rows
from public.monthly_plan_constraints
where project_code = 'TEST_REG'
  and month_key = 'test-2026'
  and line_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid;

select
    constraint_id,
    responsible_department,
    check_status,
    resolution_status,
    boq_code
from public.monthly_plan_constraints
where line_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid
order by responsible_department;
