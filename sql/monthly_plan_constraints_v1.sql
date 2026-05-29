-- =============================================================================
-- Monthly Plan Constraints v1 — архитектура ограничений допуска месячного плана
-- =============================================================================
-- Таблица:  public.monthly_plan_constraints
-- Назначение: реестр проверок и блокировок по слоям допуска (EXECUTABILITY,
--              ACCEPTABILITY, CREW_ECONOMICS) для связки с очередью review и
--              черновиками месячного плана.
--
-- Deploy:   Supabase SQL Editor (выполнить один раз вручную)
-- Страница: pages/15_Контур_допуска_месячного_плана.py — пока НЕ подключена
-- =============================================================================

create table if not exists public.monthly_plan_constraints (
    constraint_id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    draft_id uuid,
    line_id uuid,
    review_id uuid,

    project_code text,
    month_key text,
    facility_building text,
    construction_discipline text,
    boq_code text,
    boq_name text,
    crew_id text,

    gate_layer text,
    responsible_department text,
    check_name text,
    check_status text not null default 'ОЖИДАЕТ',
    block_reason text,
    owner_name text,
    due_date date,
    resolution_status text not null default 'OPEN',
    comment text,

    plan_value numeric,
    required_hours numeric,

    constraint monthly_plan_constraints_gate_layer_chk
        check (gate_layer in ('EXECUTABILITY', 'ACCEPTABILITY', 'CREW_ECONOMICS')),

    constraint monthly_plan_constraints_responsible_department_chk
        check (responsible_department in (
            'Участок',
            'ПТО',
            'МТО',
            'ОТиТБ',
            'QAQC',
            'Коммерческий отдел',
            'Руководство'
        )),

    constraint monthly_plan_constraints_check_status_chk
        check (check_status in ('ОЖИДАЕТ', 'PASS', 'WARNING', 'HOLD', 'FAIL')),

    constraint monthly_plan_constraints_resolution_status_chk
        check (resolution_status in ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CANCELLED'))
);

create index if not exists idx_monthly_plan_constraints_draft_id
    on public.monthly_plan_constraints (draft_id);

create index if not exists idx_monthly_plan_constraints_line_id
    on public.monthly_plan_constraints (line_id);

create index if not exists idx_monthly_plan_constraints_review_id
    on public.monthly_plan_constraints (review_id);

create index if not exists idx_monthly_plan_constraints_project_code
    on public.monthly_plan_constraints (project_code);

create index if not exists idx_monthly_plan_constraints_month_key
    on public.monthly_plan_constraints (month_key);

create index if not exists idx_monthly_plan_constraints_gate_layer
    on public.monthly_plan_constraints (gate_layer);

create index if not exists idx_monthly_plan_constraints_responsible_department
    on public.monthly_plan_constraints (responsible_department);

create index if not exists idx_monthly_plan_constraints_check_status
    on public.monthly_plan_constraints (check_status);

create index if not exists idx_monthly_plan_constraints_resolution_status
    on public.monthly_plan_constraints (resolution_status);

comment on table public.monthly_plan_constraints is
    'Реестр ограничений и проверок допуска месячного плана по слоям EXECUTABILITY / ACCEPTABILITY / CREW_ECONOMICS (v1, SQL-архитектура).';

comment on column public.monthly_plan_constraints.constraint_id is
    'Уникальный идентификатор записи ограничения';
comment on column public.monthly_plan_constraints.created_at is
    'Дата и время создания записи';
comment on column public.monthly_plan_constraints.updated_at is
    'Дата и время последнего обновления записи';

comment on column public.monthly_plan_constraints.draft_id is
    'Ссылка на черновик месячного плана (monthly_plan_drafts)';
comment on column public.monthly_plan_constraints.line_id is
    'Ссылка на строку черновика (monthly_plan_draft_lines)';
comment on column public.monthly_plan_constraints.review_id is
    'Ссылка на строку очереди допуска (monthly_plan_review_queue)';

comment on column public.monthly_plan_constraints.project_code is
    'Код проекта';
comment on column public.monthly_plan_constraints.month_key is
    'Ключ месяца плана (например, May-2026)';
comment on column public.monthly_plan_constraints.facility_building is
    'Здание / объект строительства';
comment on column public.monthly_plan_constraints.construction_discipline is
    'Строительная дисциплина';
comment on column public.monthly_plan_constraints.boq_code is
    'Код позиции BOQ';
comment on column public.monthly_plan_constraints.boq_name is
    'Наименование позиции BOQ';
comment on column public.monthly_plan_constraints.crew_id is
    'Идентификатор звена';

comment on column public.monthly_plan_constraints.gate_layer is
    'Слой допуска: EXECUTABILITY, ACCEPTABILITY или CREW_ECONOMICS';
comment on column public.monthly_plan_constraints.responsible_department is
    'Ответственное подразделение за снятие ограничения';
comment on column public.monthly_plan_constraints.check_name is
    'Наименование проверки (например, мощность звена, остаток BOQ)';
comment on column public.monthly_plan_constraints.check_status is
    'Статус проверки: ОЖИДАЕТ, PASS, WARNING, HOLD, FAIL';
comment on column public.monthly_plan_constraints.block_reason is
    'Причина блокировки или удержания строки плана';
comment on column public.monthly_plan_constraints.owner_name is
    'Ответственный за устранение ограничения';
comment on column public.monthly_plan_constraints.due_date is
    'Срок устранения ограничения';
comment on column public.monthly_plan_constraints.resolution_status is
    'Статус разрешения: OPEN, IN_PROGRESS, RESOLVED, CANCELLED';
comment on column public.monthly_plan_constraints.comment is
    'Комментарий по ограничению';

comment on column public.monthly_plan_constraints.plan_value is
    'Стоимость строки плана, ₽';
comment on column public.monthly_plan_constraints.required_hours is
    'Требуемые трудозатраты по строке, ч';
