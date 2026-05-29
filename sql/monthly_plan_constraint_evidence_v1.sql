-- =============================================================================
-- Monthly Plan Constraint Evidence v1 — доказательства по ограничениям (v2)
-- =============================================================================
-- Таблица:  public.monthly_plan_constraint_evidence
-- View:     public.monthly_plan_constraints_dashboard_v2
-- Depends:  public.monthly_plan_constraints (monthly_plan_constraints_v1.sql)
--
-- Deploy:   Supabase SQL Editor (выполнить после monthly_plan_constraints_v1.sql)
-- UI:       страница 15 пока НЕ подключена
-- =============================================================================

create table if not exists public.monthly_plan_constraint_evidence (
    evidence_id uuid primary key default gen_random_uuid(),

    constraint_id uuid not null
        references public.monthly_plan_constraints (constraint_id)
        on delete cascade,

    uploaded_at timestamptz not null default now(),
    uploaded_by text,

    evidence_type text,

    file_name text,
    file_url text,

    description text,

    evidence_date date,
    promised_date date,

    source_company text,
    source_person text,

    is_key_evidence boolean not null default false,

    comment text,

    constraint monthly_plan_constraint_evidence_type_chk
        check (evidence_type in (
            'EMAIL',
            'LETTER',
            'WHATSAPP',
            'PHOTO',
            'SCREENSHOT',
            'MEETING_MINUTES',
            'CONTRACT',
            'RFI',
            'SUBMITTAL',
            'DELIVERY_NOTE',
            'OTHER'
        ))
);

create index if not exists idx_monthly_plan_constraint_evidence_constraint_id
    on public.monthly_plan_constraint_evidence (constraint_id);

create index if not exists idx_monthly_plan_constraint_evidence_promised_date
    on public.monthly_plan_constraint_evidence (promised_date)
    where promised_date is not null;

create index if not exists idx_monthly_plan_constraint_evidence_key
    on public.monthly_plan_constraint_evidence (constraint_id, is_key_evidence)
    where is_key_evidence = true;

comment on table public.monthly_plan_constraint_evidence is
    'Доказательства и подтверждения по ограничениям допуска месячного плана (письма, фото, протоколы, RFI и т.д.).';

comment on column public.monthly_plan_constraint_evidence.evidence_id is
    'Уникальный идентификатор доказательства';
comment on column public.monthly_plan_constraint_evidence.constraint_id is
    'Ссылка на ограничение (monthly_plan_constraints); при удалении ограничения доказательства удаляются каскадно';
comment on column public.monthly_plan_constraint_evidence.uploaded_at is
    'Дата и время загрузки / регистрации доказательства';
comment on column public.monthly_plan_constraint_evidence.uploaded_by is
    'Кто загрузил или зарегистрировал доказательство';
comment on column public.monthly_plan_constraint_evidence.evidence_type is
    'Тип доказательства: EMAIL, LETTER, PHOTO, RFI, SUBMITTAL и др.';
comment on column public.monthly_plan_constraint_evidence.file_name is
    'Имя файла вложения';
comment on column public.monthly_plan_constraint_evidence.file_url is
    'URL или путь к файлу доказательства (Storage / внешняя ссылка)';
comment on column public.monthly_plan_constraint_evidence.description is
    'Краткое описание содержания доказательства';
comment on column public.monthly_plan_constraint_evidence.evidence_date is
    'Дата события / документа (когда получено письмо, проведена встреча и т.п.)';
comment on column public.monthly_plan_constraint_evidence.promised_date is
    'Обещанная дата снятия ограничения (контрагент / смежник / участок)';
comment on column public.monthly_plan_constraint_evidence.source_company is
    'Компания-источник (заказчик, субподрядчик, поставщик)';
comment on column public.monthly_plan_constraint_evidence.source_person is
    'Контактное лицо источника';
comment on column public.monthly_plan_constraint_evidence.is_key_evidence is
    'Ключевое доказательство для расчёта просрочки обещания в дашборде';
comment on column public.monthly_plan_constraint_evidence.comment is
    'Дополнительный комментарий';

-- -----------------------------------------------------------------------------
-- Dashboard v2: ограничения + контроль обещанных дат
-- promised_date берётся из ключевого доказательства; если нет — из max(promised_date)
-- -----------------------------------------------------------------------------

create or replace view public.monthly_plan_constraints_dashboard_v2 as
with evidence_promise as (
    select
        e.constraint_id,
        coalesce(
            max(e.promised_date) filter (
                where e.is_key_evidence and e.promised_date is not null
            ),
            max(e.promised_date) filter (where e.promised_date is not null)
        ) as effective_promised_date,
        count(*)::bigint as evidence_count
    from public.monthly_plan_constraint_evidence e
    group by e.constraint_id
)
select
    c.*,
    ep.effective_promised_date,
    ep.evidence_count,
    case
        when c.resolution_status not in ('RESOLVED', 'CANCELLED')
            and ep.effective_promised_date is not null
            and ep.effective_promised_date < current_date
        then (current_date - ep.effective_promised_date)::integer
        else 0
    end as days_since_promise,
    (
        c.resolution_status not in ('RESOLVED', 'CANCELLED')
        and ep.effective_promised_date is not null
        and ep.effective_promised_date < current_date
    ) as is_promise_overdue
from public.monthly_plan_constraints c
left join evidence_promise ep
    on ep.constraint_id = c.constraint_id;

comment on view public.monthly_plan_constraints_dashboard_v2 is
    'Дашборд ограничений v2: все поля ограничения + эффективная обещанная дата из доказательств, просрочка обещания и признак is_promise_overdue.';

comment on column public.monthly_plan_constraints_dashboard_v2.effective_promised_date is
    'Эффективная обещанная дата: из ключевого доказательства (is_key_evidence), иначе максимальная promised_date по строке';
comment on column public.monthly_plan_constraints_dashboard_v2.evidence_count is
    'Количество зарегистрированных доказательств по ограничению';
comment on column public.monthly_plan_constraints_dashboard_v2.days_since_promise is
    'Дней с момента просрочки обещания: current_date − promised_date, если ограничение не закрыто и дата обещания в прошлом; иначе 0';
comment on column public.monthly_plan_constraints_dashboard_v2.is_promise_overdue is
    'Признак просроченного обещания: true, если ограничение не RESOLVED/CANCELLED и effective_promised_date < сегодня';
