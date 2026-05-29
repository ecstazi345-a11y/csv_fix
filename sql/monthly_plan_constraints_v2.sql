-- =============================================================================
-- Monthly Plan Constraints v2 — lifecycle-поля (без пересоздания таблицы)
-- =============================================================================
-- Depends:  public.monthly_plan_constraints (monthly_plan_constraints_v1.sql)
-- Deploy:   Supabase SQL Editor (после v1, до/после evidence_v1)
-- UI:       страница 15 и Python не меняются
-- =============================================================================

do $$
begin
    if to_regclass('public.monthly_plan_constraints') is null then
        raise notice 'Таблица public.monthly_plan_constraints не найдена — миграция v2 пропущена.';
        return;
    end if;

    -- constraint_created_at
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'constraint_created_at'
    ) then
        alter table public.monthly_plan_constraints
            add column constraint_created_at timestamptz default now();
    end if;

    -- created_by
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'created_by'
    ) then
        alter table public.monthly_plan_constraints
            add column created_by text;
    end if;

    -- created_role
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'created_role'
    ) then
        alter table public.monthly_plan_constraints
            add column created_role text;
    end if;

    -- owner_role
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'owner_role'
    ) then
        alter table public.monthly_plan_constraints
            add column owner_role text;
    end if;

    -- owner_department (не дублировать, если уже есть)
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'owner_department'
    ) then
        alter table public.monthly_plan_constraints
            add column owner_department text;
    end if;

    -- target_resolution_date
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'target_resolution_date'
    ) then
        alter table public.monthly_plan_constraints
            add column target_resolution_date date;
    end if;

    -- resolved_at
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'resolved_at'
    ) then
        alter table public.monthly_plan_constraints
            add column resolved_at timestamptz;
    end if;

    -- resolved_by
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'resolved_by'
    ) then
        alter table public.monthly_plan_constraints
            add column resolved_by text;
    end if;

    -- severity
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'severity'
    ) then
        alter table public.monthly_plan_constraints
            add column severity text default 'MEDIUM';
    end if;

    -- constraint_category
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'constraint_category'
    ) then
        alter table public.monthly_plan_constraints
            add column constraint_category text;
    end if;

    -- root_cause
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'root_cause'
    ) then
        alter table public.monthly_plan_constraints
            add column root_cause text;
    end if;

    -- value_at_risk
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'value_at_risk'
    ) then
        alter table public.monthly_plan_constraints
            add column value_at_risk numeric default 0;
    end if;

    -- last_comment_at
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'last_comment_at'
    ) then
        alter table public.monthly_plan_constraints
            add column last_comment_at timestamptz;
    end if;

    -- updated_by
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'updated_by'
    ) then
        alter table public.monthly_plan_constraints
            add column updated_by text;
    end if;

    -- updated_role
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'updated_role'
    ) then
        alter table public.monthly_plan_constraints
            add column updated_role text;
    end if;

    -- last_action_at
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_constraints'
          and column_name = 'last_action_at'
    ) then
        alter table public.monthly_plan_constraints
            add column last_action_at timestamptz;
    end if;
end $$;

-- Для существующих строк: дата открытия ограничения = created_at, если не задана
update public.monthly_plan_constraints
set constraint_created_at = created_at
where constraint_created_at is null
  and created_at is not null;

update public.monthly_plan_constraints
set constraint_created_at = now()
where constraint_created_at is null;

-- CHECK severity (идемпотентно)
alter table public.monthly_plan_constraints
    drop constraint if exists monthly_plan_constraints_severity_chk;

alter table public.monthly_plan_constraints
    add constraint monthly_plan_constraints_severity_chk
    check (severity in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'));

-- -----------------------------------------------------------------------------
-- Dashboard v1: lifecycle (days_open / days_overdue / is_overdue)
-- -----------------------------------------------------------------------------

create or replace view public.monthly_plan_constraints_dashboard_v1 as
select
    c.*,
    case
        when c.resolved_at is null then
            (current_date - coalesce(c.constraint_created_at, c.created_at)::date)::integer
        else
            (c.resolved_at::date - coalesce(c.constraint_created_at, c.created_at)::date)::integer
    end as days_open,
    case
        when c.resolution_status not in ('RESOLVED', 'CANCELLED')
            and c.target_resolution_date is not null
            and c.target_resolution_date < current_date
        then (current_date - c.target_resolution_date)::integer
        else 0
    end as days_overdue,
    (
        c.resolution_status not in ('RESOLVED', 'CANCELLED')
        and c.target_resolution_date is not null
        and c.target_resolution_date < current_date
    ) as is_overdue
from public.monthly_plan_constraints c;

comment on view public.monthly_plan_constraints_dashboard_v1 is
    'Дашборд ограничений v1: lifecycle — сколько дней открыто ограничение и просрочка по target_resolution_date.';

comment on column public.monthly_plan_constraints_dashboard_v1.days_open is
    'Дней с момента открытия: до сегодня, если не закрыто; иначе до даты resolved_at';
comment on column public.monthly_plan_constraints_dashboard_v1.days_overdue is
    'Дней просрочки целевой даты снятия: current_date − target_resolution_date, если ограничение не закрыто и срок в прошлом; иначе 0';
comment on column public.monthly_plan_constraints_dashboard_v1.is_overdue is
    'Признак просрочки по target_resolution_date для незакрытых ограничений';

comment on column public.monthly_plan_constraints.constraint_created_at is
    'Дата и время регистрации ограничения (начало lifecycle)';
comment on column public.monthly_plan_constraints.created_by is
    'Кто зарегистрировал ограничение';
comment on column public.monthly_plan_constraints.created_role is
    'Роль создателя (прораб, ПТО, руководство и т.д.)';
comment on column public.monthly_plan_constraints.owner_role is
    'Роль текущего владельца / ответственного за снятие';
comment on column public.monthly_plan_constraints.owner_department is
    'Подразделение-владелец ограничения (если отличается от responsible_department)';
comment on column public.monthly_plan_constraints.target_resolution_date is
    'Целевая дата снятия ограничения';
comment on column public.monthly_plan_constraints.resolved_at is
    'Дата и время фактического закрытия ограничения';
comment on column public.monthly_plan_constraints.resolved_by is
    'Кто закрыл ограничение';
comment on column public.monthly_plan_constraints.severity is
    'Критичность: LOW, MEDIUM, HIGH, CRITICAL';
comment on column public.monthly_plan_constraints.constraint_category is
    'Категория ограничения (норма, фронт, мощность звена, признаваемость и т.д.)';
comment on column public.monthly_plan_constraints.root_cause is
    'Корневая причина ограничения';
comment on column public.monthly_plan_constraints.value_at_risk is
    'Стоимость под риском, ₽';
comment on column public.monthly_plan_constraints.last_comment_at is
    'Время последнего комментария по ограничению';
comment on column public.monthly_plan_constraints.updated_by is
    'Кто последним изменил запись';
comment on column public.monthly_plan_constraints.updated_role is
    'Роль последнего редактора';
comment on column public.monthly_plan_constraints.last_action_at is
    'Время последнего действия по ограничению (комментарий, смена статуса, вложение)';
