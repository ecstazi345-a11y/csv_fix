-- =============================================================================
-- UI E2E fixture R2: update form on Page 24 (TEST ONLY)
-- =============================================================================
-- File:   sql/tests/monthly_plan_constraint_registry_r2_ui_fixture.sql
-- Purpose: insert reversible TEST_REG_R2 rows for Page 24 update UI.
--
-- SAFETY:
--   - Only TEST_REG_R2 / test-r2-ui-2026 / fixed cccccccc-… UUIDs
--   - Does NOT touch monthly_plan_lines_v2
--   - Does NOT touch passport tables
--   - Does NOT touch product project_code (PRJ_*)
--
-- Run manually in SQL Editor AFTER user confirmation.
-- Pair with: sql/tests/monthly_plan_constraint_registry_r2_ui_cleanup.sql
--
-- STOP BEFORE submit on real product rows.
-- =============================================================================

delete from public.monthly_plan_constraints
where constraint_id in (
    'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid,
    'cccccccc-cccc-cccc-cccc-cccccccc0003'::uuid
)
or line_id = 'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid
or (
    project_code = 'TEST_REG_R2'
    and month_key = 'test-r2-ui-2026'
);

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
    constraint_category,
    constraint_priority,
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
    'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid,
    'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid,
    'TEST_REG_R2',
    'test-r2-ui-2026',
    'TEST-FACILITY-R2',
    'Автоматизация',
    'BOQ-R2-UI-001',
    'Тестовое ограничение R2 UI update',
    'EXECUTABILITY',
    'МТО',
    'Материалы и оборудование',
    'HOLD',
    'OPEN',
    'Не согласован TEQ на МТР',
    'TEQ',
    'ПИ Тестов',
    'Заказчик',
    'Выдать письменное согласование TEQ',
    'Материал не поставлен',
    'HIGH',
    'ESTIMATED',
    'CUSTOMER',
    date '2026-07-01',
    date '2026-08-15',
    date '2026-08-10',
    150000,
    timestamptz '2026-07-05 10:00:00+00',
    'TEST_UI',
    'TEST_UI',
    now()
),
(
    'cccccccc-cccc-cccc-cccc-cccccccc0003'::uuid,
    'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid,
    'TEST_REG_R2',
    'test-r2-ui-2026',
    'TEST-FACILITY-R2',
    'Автоматизация',
    'BOQ-R2-UI-001',
    'Тестовое ограничение R2 UI resolved (disabled form)',
    'EXECUTABILITY',
    'ПТО',
    'РД / IWP / исполнительность',
    'PASS',
    'RESOLVED',
    null,
    null,
    'ПТО',
    null,
    null,
    'РД',
    'LOW',
    'CONFIRMED',
    'LETTER',
    date '2026-06-01',
    date '2026-06-20',
    null,
    0,
    timestamptz '2026-06-02 10:00:00+00',
    'TEST_UI',
    'TEST_UI',
    now()
);

-- Post-insert check
select constraint_id, project_code, month_key, resolution_status, boq_code
from public.monthly_plan_constraints
where project_code = 'TEST_REG_R2'
  and month_key = 'test-r2-ui-2026'
order by constraint_id;
