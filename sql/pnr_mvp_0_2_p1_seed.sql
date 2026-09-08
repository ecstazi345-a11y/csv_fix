-- =============================================================================
-- PNR MVP-0.2 — Minimum P1 catalog seed
-- =============================================================================
-- File:    sql/pnr_mvp_0_2_p1_seed.sql
-- Deploy:  Supabase SQL Editor MANUALLY after review. Do NOT auto-run.
--          Requires MVP-0.1 (sql/pnr_mvp_0_1.sql) already applied.
--
-- Inserts exactly four catalog rows:
--   1. public.eos_systems        P1
--   2. public.pnr_objects        ШСАУ-P1
--   3. public.pnr_work_scopes    AUT_ALGORITHMS
--   4. public.pnr_operations     PNR-AUT-003
--
-- Does NOT:
--   - insert pnr_execution_events
--   - insert baselines / GESN / BOQ / acceptance / measurements
--   - UPDATE / DELETE
--   - ON CONFLICT
--   - hardcode UUIDs
--   - change schema, RLS, or grants
--
-- Fail-visible identity:
--   Unique constraints from MVP-0.1 reject a second identical seed.
--   Object/operation FKs are scalar subqueries: 0 parent rows → NOT NULL
--   failure; >1 parent row → PostgreSQL "more than one row returned".
-- =============================================================================

begin;

insert into public.eos_systems (
    project_code,
    system_code,
    system_name,
    legacy_system_label
)
values (
    'PRJ_001_SLM',
    'P1',
    'Система вентиляции P1',
    null
);

insert into public.pnr_objects (
    system_id,
    object_code,
    object_name,
    object_kind,
    parent_object_id
)
values (
    (
        select s.system_id
        from public.eos_systems s
        where s.project_code = 'PRJ_001_SLM'
          and s.system_code = 'P1'
    ),
    'ШСАУ-P1',
    'Шкаф системы автоматического управления P1',
    'PANEL',
    null
);

insert into public.pnr_work_scopes (
    scope_code,
    scope_name,
    sequence_no
)
values (
    'AUT_ALGORITHMS',
    'Автоматика / алгоритмы',
    1
);

insert into public.pnr_operations (
    operation_code,
    work_scope_id,
    operation_name,
    sequence_no
)
values (
    'PNR-AUT-003',
    (
        select w.work_scope_id
        from public.pnr_work_scopes w
        where w.scope_code = 'AUT_ALGORITHMS'
    ),
    'Проверка алгоритма',
    1
);

commit;
