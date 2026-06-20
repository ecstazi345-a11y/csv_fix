-- Исключение остатка из выполнения (v2 конструктор месячного плана)
-- Таблица: public.monthly_scope_manual_adjustments

alter table public.monthly_scope_manual_adjustments
    add column if not exists not_required_qty numeric default 0,
    add column if not exists not_required_reason text,
    add column if not exists not_required_responsible_person text,
    add column if not exists not_required_comment text,
    add column if not exists not_required_updated_at timestamptz;

comment on column public.monthly_scope_manual_adjustments.not_required_qty is
    'Объём BOQ, не требующий выполнения (исключён из рабочего объёма)';
comment on column public.monthly_scope_manual_adjustments.not_required_reason is
    'Причина исключения остатка из выполнения';
comment on column public.monthly_scope_manual_adjustments.not_required_responsible_person is
    'ФИО ответственного за исключение остатка';
comment on column public.monthly_scope_manual_adjustments.not_required_comment is
    'Основание / комментарий к исключению остатка';
comment on column public.monthly_scope_manual_adjustments.not_required_updated_at is
    'Время последнего сохранения исключения остатка (UTC)';
