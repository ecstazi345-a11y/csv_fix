-- =============================================================================
-- UI E2E cleanup: monthly_plan_constraint registry R2 UPDATE (TEST ONLY)
-- =============================================================================
-- File:   sql/tests/monthly_plan_constraint_registry_r2_ui_cleanup.sql
-- Purpose: remove ONLY TEST_REG_R2 / test-r2-ui-2026 / cccccccc-… fixture rows.
--
-- SAFETY:
--   - Deletes only exact fixture UUIDs OR (project_code='TEST_REG_R2' AND month_key='test-r2-ui-2026')
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
    'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid,
    'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid
);

-- 2) Delete leftover TEST_REG_R2 / test-r2-ui-2026 / test line
delete from public.monthly_plan_constraints
where line_id = 'cccccccc-cccc-cccc-cccc-cccccccc1001'::uuid
   or (
        project_code = 'TEST_REG_R2'
        and month_key = 'test-r2-ui-2026'
      );

-- 3) Post-check: must be 0
select count(*) as test_r2_constraints_left
from public.monthly_plan_constraints
where project_code = 'TEST_REG_R2'
   or month_key = 'test-r2-ui-2026'
   or line_id = 'cccccccc-cccc-cccc-cccc-cccccccc1001'::uuid
   or constraint_id in (
        'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid,
        'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid
      );

select count(*) as test_r2_events_left
from public.monthly_plan_constraint_events
where project_code = 'TEST_REG_R2'
   or month_key = 'test-r2-ui-2026'
   or constraint_id in (
        'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid,
        'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid
      );

-- Product sanity
select count(*) as product_constraints_total
from public.monthly_plan_constraints;

select count(*) as product_events_total
from public.monthly_plan_constraint_events;
