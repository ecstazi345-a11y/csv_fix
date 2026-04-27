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


def apply_filters(query, filters: dict):
    """
    Универсальные фильтры для Streamlit.
    Пока week_key может отсутствовать в Supabase — используем только если поле появится во view.
    """

    if filters.get("project_code"):
        query = query.eq("project_code", filters["project_code"])

    if filters.get("month_key"):
        query = query.eq("month_key", filters["month_key"])

    if filters.get("week_key"):
        query = query.eq("week_key", filters["week_key"])

    if filters.get("facility_building"):
        query = query.eq("facility_building", filters["facility_building"])

    if filters.get("construction_discipline"):
        query = query.eq("construction_discipline", filters["construction_discipline"])

    if filters.get("crew"):
        # В разных view поле может называться по-разному.
        # Для plan-line используем plan_crew / fact_crew отдельно.
        query = query.or_(
            f"plan_crew.eq.{filters['crew']},fact_crew.eq.{filters['crew']}"
        )

    if filters.get("budget_status"):
        query = query.eq("budget_status", filters["budget_status"])

    return query


def get_smr_reconciliation(filters=None, limit=1000):
    filters = filters or {}

    query = supabase.table("work_plan_fact_reconciliation").select("*").limit(limit)

    query = apply_filters(query, filters)

    response = query.execute()
    return response.data


def get_smr_plan_line_control(filters=None, limit=1000):
    filters = filters or {}

    query = supabase.table("work_plan_fact_by_plan_line").select("*").limit(limit)

    query = apply_filters(query, filters)

    response = query.execute()
    return response.data


def get_smr_plan_line_status(filters=None, limit=1000):
    filters = filters or {}

    query = (
        supabase.table("work_plan_fact_by_plan_line_status").select("*").limit(limit)
    )

    query = apply_filters(query, filters)

    response = query.execute()
    return response.data


def get_smr_fact_only(filters=None, limit=1000):
    filters = filters or {}

    query = (
        supabase.table("work_plan_fact_reconciliation")
        .select("*")
        .eq("reconciliation_status", "FACT_ONLY")
        .limit(limit)
    )

    query = apply_filters(query, filters)

    response = query.execute()
    return response.data


def get_smr_plan_only(filters=None, limit=1000):
    filters = filters or {}

    query = (
        supabase.table("work_plan_fact_reconciliation")
        .select("*")
        .eq("reconciliation_status", "PLAN_ONLY")
        .limit(limit)
    )

    query = apply_filters(query, filters)

    response = query.execute()
    return response.data


def get_smr_matched(filters=None, limit=1000):
    filters = filters or {}

    query = (
        supabase.table("work_plan_fact_reconciliation")
        .select("*")
        .eq("reconciliation_status", "MATCHED")
        .limit(limit)
    )

    query = apply_filters(query, filters)

    response = query.execute()
    return response.data
