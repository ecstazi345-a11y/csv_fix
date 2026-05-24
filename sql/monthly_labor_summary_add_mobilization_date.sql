-- Дата фактической мобилизации из Airtable Crew_Register
alter table public.monthly_labor_summary
    add column if not exists actual_mobilization_date date;

comment on column public.monthly_labor_summary.actual_mobilization_date is
    'Actual_Mobilization_Date из Crew_Register — дата выхода человека на объект';
