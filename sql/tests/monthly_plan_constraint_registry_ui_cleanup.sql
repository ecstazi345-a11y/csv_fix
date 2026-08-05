-- =============================================================================
-- UI E2E cleanup: monthly_plan_constraint registry (TEST ONLY)
-- =============================================================================
-- File:   sql/tests/monthly_plan_constraint_registry_ui_cleanup.sql
-- Purpose: remove ONLY TEST_REG / test-2026 UI E2E fixture rows.
--
-- SAFETY:
--   - Deletes only exact fixture UUIDs OR (project_code='TEST_REG' AND month_key='test-2026')
--   - Events removed via FK ON DELETE CASCADE
--   - Does NOT touch monthly_plan_lines_v2
--   - Does NOT touch passport tables
--   - Does NOT delete product project_code rows
--
-- Run manually in SQL Editor AFTER UI E2E completes.
-- =============================================================================

-- 1) Delete by exact constraint UUIDs
delete from public.monthly_plan_constraints
where constraint_id in (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0002'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0003'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0004'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0005'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0006'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0007'::uuid,
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0008'::uuid
);

-- 2) Delete any leftover test line / TEST_REG + test-2026 (belt and suspenders)
delete from public.monthly_plan_constraints
where line_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid
   or (
        project_code = 'TEST_REG'
        and month_key = 'test-2026'
      );

-- 3) Post-check: must be 0
select count(*) as test_constraints_left
from public.monthly_plan_constraints
where project_code = 'TEST_REG'
   or month_key = 'test-2026'
   or line_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001'::uuid
   or constraint_id in (
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0002'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0003'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0004'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0005'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0006'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0007'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0008'::uuid
      );

select count(*) as test_events_left
from public.monthly_plan_constraint_events
where project_code = 'TEST_REG'
   or month_key = 'test-2026'
   or constraint_id in (
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0002'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0003'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0004'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0005'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0006'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0007'::uuid,
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0008'::uuid
      );

-- Product sanity (expect 1799 if no other concurrent product writes)
select count(*) as product_constraints_total
from public.monthly_plan_constraints;

select count(*) as product_events_total
from public.monthly_plan_constraint_events;
