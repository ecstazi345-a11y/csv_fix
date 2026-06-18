-- MVP: независимый контур ввода смены (Python Form → Supabase)
-- Выполнить в Supabase SQL Editor один раз.
-- Не затрагивает daily_progress_raw и Airtable pipeline.

create table if not exists public.daily_progress_form_submissions (
    submission_id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),

    project_code text not null,
    work_date date not null,
    shift_type text not null,
    crew_code text not null,
    crew_name text,
    is_day_off boolean not null default false,

    boq_code text,
    boq_name text,
    iwp_id text,
    system_label text,
    unit_of_measure text,
    quantity_today numeric,
    direct_work_hours numeric,
    idle_hours numeric,
    idle_reason text,

    operation_type text,
    operation_quantity numeric,
    operation_unit text,

    comment_foreman text,
    submitted_by text,
    data_source text not null default 'python_form'
);

create index if not exists idx_dp_form_submissions_work_date
    on public.daily_progress_form_submissions (work_date desc);

create index if not exists idx_dp_form_submissions_project
    on public.daily_progress_form_submissions (project_code, work_date);

comment on table public.daily_progress_form_submissions is
    'MVP: смены из Python Form (параллельно Airtable Daily Progress)';

-- RLS: для MVP разрешить insert/select через anon key (Streamlit + supabase_client)
alter table public.daily_progress_form_submissions enable row level security;

drop policy if exists "form_submissions_insert_anon" on public.daily_progress_form_submissions;
create policy "form_submissions_insert_anon"
    on public.daily_progress_form_submissions
    for insert
    to anon, authenticated
    with check (true);

drop policy if exists "form_submissions_select_anon" on public.daily_progress_form_submissions;
create policy "form_submissions_select_anon"
    on public.daily_progress_form_submissions
    for select
    to anon, authenticated
    using (true);
