-- =============================================================================
-- Monthly Plan Passport Override v1 — управленческий допуск (Management Override)
-- =============================================================================
-- Depends:  public.monthly_plan_passport_lines (monthly_plan_passport_v1.sql)
-- Deploy:   Supabase SQL Editor (после monthly_plan_passport_v1.sql)
-- Service:  services/monthly_passport_service.py
-- =============================================================================
--
-- Management Override =
-- ручное управленческое решение о допуске строки в Monthly Passport
-- несмотря на HOLD / FAIL по ограничениям.
--
-- Пример: код гидроиспытаний не входит в договор, FAIL по признаваемости,
-- но заказчик требует продолжать, остановка невозможна — руководство принимает риск.
-- Поля фиксируют след ответственности.
-- =============================================================================

do $$
begin
    if to_regclass('public.monthly_plan_passport_lines') is null then
        raise notice 'Таблица public.monthly_plan_passport_lines не найдена — миграция override v1 пропущена.';
        return;
    end if;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_passport_lines'
          and column_name = 'management_override'
    ) then
        alter table public.monthly_plan_passport_lines
            add column management_override boolean not null default false;
    end if;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_passport_lines'
          and column_name = 'override_by'
    ) then
        alter table public.monthly_plan_passport_lines
            add column override_by text;
    end if;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_passport_lines'
          and column_name = 'override_at'
    ) then
        alter table public.monthly_plan_passport_lines
            add column override_at timestamptz;
    end if;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_passport_lines'
          and column_name = 'override_reason'
    ) then
        alter table public.monthly_plan_passport_lines
            add column override_reason text;
    end if;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_passport_lines'
          and column_name = 'override_risk_comment'
    ) then
        alter table public.monthly_plan_passport_lines
            add column override_risk_comment text;
    end if;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'monthly_plan_passport_lines'
          and column_name = 'override_basis'
    ) then
        alter table public.monthly_plan_passport_lines
            add column override_basis text;
    end if;
end $$;

comment on column public.monthly_plan_passport_lines.management_override is
    'Management Override: управленческое решение включить строку в паспорт несмотря на HOLD/FAIL';
comment on column public.monthly_plan_passport_lines.override_by is
    'Кто принял управленческое решение о допуске (ФИО / роль)';
comment on column public.monthly_plan_passport_lines.override_at is
    'Дата и время управленческого решения о допуске';
comment on column public.monthly_plan_passport_lines.override_reason is
    'Причина override: почему строка допускается в производство';
comment on column public.monthly_plan_passport_lines.override_risk_comment is
    'Комментарий по принятому риску (коммерческий, репутационный, договорной)';
comment on column public.monthly_plan_passport_lines.override_basis is
    'Основание решения: протокол, письмо заказчика, указание руководства';

-- Допустимые статусы допуска строки паспорта (документация, без CHECK — гибкость v1)
comment on column public.monthly_plan_passport_lines.admission_status is
    'Статус допуска: BLOCKED, READY_WITH_RISK, APPROVED_TO_EXECUTE, WAITING_CHECKS, NO_CHECKS, APPROVED_BY_OVERRIDE';

-- Расширить dashboard v1 полями override (если view уже существует)
create or replace view public.monthly_plan_passport_dashboard_v1 as
select
    p.passport_id,
    p.passport_status,
    p.project_code,
    p.month_key,
    p.passport_name,
    p.approved_by,
    p.approved_at,
    l.boq_code,
    l.boq_name,
    l.facility_building,
    l.construction_discipline,
    l.crew_id,
    l.planned_qty,
    l.plan_value,
    l.required_hours,
    l.labor_cost,
    l.admission_status,
    l.week_plan_status,
    l.management_override,
    l.override_by,
    l.override_at,
    l.override_reason
from public.monthly_plan_passports p
inner join public.monthly_plan_passport_lines l
    on l.passport_id = p.passport_id;

comment on view public.monthly_plan_passport_dashboard_v1 is
    'Дашборд паспорта месяца v1: шапка + строки + поля Management Override.';
