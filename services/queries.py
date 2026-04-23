from services.supabase_client import supabase


def get_rcc_home_summary():
    response = supabase.table("daily_progress_raw").select("*").limit(20).execute()
    return response.data


def get_monthly_passport_plan(limit=300):
    response = (
        supabase.table("monthly_passport_plan").select("*").limit(limit).execute()
    )
    return response.data


def get_monthly_plan_vs_fact():
    response = supabase.table("monthly_plan_vs_fact").select("*").execute()
    return response.data
