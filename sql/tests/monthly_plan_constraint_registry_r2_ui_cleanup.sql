-- =============================================================================
-- UI E2E cleanup R2: Page 24 update form fixture
-- =============================================================================
-- File:   sql/tests/monthly_plan_constraint_registry_r2_ui_cleanup.sql
-- Deletes ONLY TEST_REG_R2 / test-r2-ui-2026 / cccccccc-… fixture rows.
-- Events removed via FK ON DELETE CASCADE.
-- Does NOT touch product PRJ_* / passport / plan lines.
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

select count(*) as test_r2_ui_constraints_left
from public.monthly_plan_constraints
where project_code = 'TEST_REG_R2'
   or month_key = 'test-r2-ui-2026'
   or line_id = 'cccccccc-cccc-cccc-cccc-cccccccc0001'::uuid
   or constraint_id in (
        'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid,
        'cccccccc-cccc-cccc-cccc-cccccccc0003'::uuid
      );

select count(*) as test_r2_ui_events_left
from public.monthly_plan_constraint_events
where project_code = 'TEST_REG_R2'
   or month_key = 'test-r2-ui-2026'
   or constraint_id in (
        'cccccccc-cccc-cccc-cccc-cccccccc0002'::uuid,
        'cccccccc-cccc-cccc-cccc-cccccccc0003'::uuid
      );

select count(*) as product_constraints_total
from public.monthly_plan_constraints;

select count(*) as product_events_total
from public.monthly_plan_constraint_events;
