# ============================================================
# CREW PLAN BURNDOWN — LAYER 1
# Управленческий слой по звену: Month + Crew
# Показывает план работ, direct часы, direct себестоимость,
# списание/потребление direct cost и финансовый риск.
#
# НЕ смешивать с будущим Layer 2.
# Layer 2 будет строиться ниже:
# Month + Crew + BOQ_Code + IWP + System + Operation.
# Там будет сменное списание объёмов, работ, часов и затрат
# по конкретным кодам/пакетам/системам.
# ============================================================

# TODO Layer 2:
# Подключить Daily Progress fact:
# - actual_qty
# - ev_value
# - actual_direct_hours
# - actual_direct_cost
# на уровне Month + Crew + BOQ_Code + IWP + System + Unit_of_Measure.
# Тогда 4 счётчика станут реальными:
# Quantity Burn, Work Value Burn, Direct Hours Burn, Direct Cost Burn.

import textwrap

import streamlit as st
import pandas as pd
from services.supabase_client import supabase


def render_html(html: str) -> None:
    """Рендер HTML/CSS; без unsafe_allow_html и dedent Markdown показывает разметку как текст."""
    if not html:
        return
    st.markdown(textwrap.dedent(html).strip(), unsafe_allow_html=True)

st.set_page_config(layout="wide")

VIEW_NAME = "v_crew_burndown_with_fact"
FACT_PENDING_STATUS = "Факт ещё не поступил"

NUMERIC_COLS = [
    "plan_work_value_month",
    "plan_direct_hours_month",
    "plan_direct_cost_month",
    "actual_work_value",
    "actual_direct_hours",
    "actual_direct_cost",
    "actual_qty_total",
    "remaining_work_value",
    "remaining_direct_hours",
    "remaining_direct_cost",
    "work_value_burn_pct",
    "direct_hours_burn_pct",
    "direct_cost_burn_pct",
    "margin_after_direct",
    "direct_cost_share",
    "fact_rows",
]

RISK_LABELS = {
    "OK": "OK",
    "MEDIUM_DIRECT_COST": "MEDIUM",
    "HIGH_DIRECT_COST": "HIGH",
    "CRITICAL_DIRECT_LOSS": "CRITICAL",
    "NO_LABOR_DATA": "NO DATA",
}

RISK_COLORS = {
    "OK": "#1b7f3a",
    "MEDIUM_DIRECT_COST": "#b8860b",
    "HIGH_DIRECT_COST": "#d97706",
    "CRITICAL_DIRECT_LOSS": "#b91c1c",
    "NO_LABOR_DATA": "#6b7280",
}

FORECAST_LABELS = {
    "ON_TRACK": "ON TRACK",
    "AT_RISK": "AT RISK",
    "LOSS_FORECAST": "LOSS",
    "NO_FACT": "NO FACT",
}

FORECAST_COLORS = {
    "ON_TRACK": "#1b7f3a",
    "AT_RISK": "#b8860b",
    "LOSS_FORECAST": "#b91c1c",
    "NO_FACT": "#6b7280",
}

FORECAST_TEXTS = {
    "NO_FACT": "Недостаточно факта для прогноза.",
    "ON_TRACK": (
        "При текущей выработке звено способно закрыть план в пределах плановых часов."
    ),
    "AT_RISK": "При текущей выработке есть риск недоосвоения плана.",
    "LOSS_FORECAST": (
        "При текущей выработке звено рискует сжечь direct cost быстрее, "
        "чем создаёт стоимость работ."
    ),
}

QUANTITY_LAYER2_NOTE = (
    "Объём требует детализации Layer 2 по BOQ/IWP/System/Unit. "
    "На Layer 1 общий объём может быть некорректен из-за разных единиц измерения."
)


@st.cache_data(ttl=300)
def load_burndown(limit: int = 5000) -> pd.DataFrame:
    response = supabase.table(VIEW_NAME).select("*").limit(limit).execute()
    df = pd.DataFrame(response.data or [])
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def safe_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def money(value):
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.0f} ₽".replace(",", " ")


def money_per_hour(value):
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.0f} ₽/ч".replace(",", " ")


def hours_fmt(value):
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.1f} чел-ч".replace(",", " ")


def pct_fmt(value, as_ratio: bool = True):
    v = safe_float(value)
    if v is None:
        return "—"
    pct = v * 100 if as_ratio else v
    return f"{pct:.1f}%"


def burn_ratio(fact, planned):
    f = safe_float(fact)
    p = safe_float(planned)
    if p is None or p == 0:
        return None
    if f is None:
        f = 0.0
    return f / p


def burn_pct_from_view(row, pct_col: str, fact_col: str, plan_col: str):
    pct = safe_float(row.get(pct_col))
    if pct is not None:
        return pct
    return burn_ratio(row.get(fact_col), row.get(plan_col))


def has_fact(row: pd.Series) -> bool:
    fact_rows = safe_float(row.get("fact_rows")) or 0.0
    if fact_rows > 0:
        return True
    for col in (
        "actual_work_value",
        "actual_direct_hours",
        "actual_direct_cost",
        "actual_qty_total",
    ):
        v = safe_float(row.get(col))
        if v is not None and v != 0:
            return True
    return False


def fact_status_html(row: pd.Series) -> str:
    if has_fact(row):
        return ""
    return (
        f'<span style="color:#6b7280;font-size:12px;font-weight:600;">'
        f"{FACT_PENDING_STATUS}</span>"
    )


def qty_fmt(value):
    v = safe_float(value)
    if v is None:
        return "0"
    return f"{v:,.1f}".replace(",", " ")


def calc_risk(direct_cost_share) -> str:
    share = safe_float(direct_cost_share)
    if share is None:
        return "NO_LABOR_DATA"
    if share > 1:
        return "CRITICAL_DIRECT_LOSS"
    if share > 0.7:
        return "HIGH_DIRECT_COST"
    if share > 0.5:
        return "MEDIUM_DIRECT_COST"
    return "OK"


def filter_options(df: pd.DataFrame, col: str) -> list[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def apply_filters(df: pd.DataFrame, month_key: str, crew: str) -> pd.DataFrame:
    result = df.copy()
    if month_key != "Все" and "month_key" in result.columns:
        result = result[result["month_key"].astype(str) == month_key]
    if crew != "Все" and "crew" in result.columns:
        result = result[result["crew"].astype(str) == crew]
    return result


def badge_html(label: str, color: str) -> str:
    return (
        '<span style="display:inline-block;padding:5px 12px;border-radius:999px;'
        f'background:{color};color:#fff;font-weight:700;font-size:12px;">{label}</span>'
    )


def risk_badge_html(risk: str) -> str:
    return badge_html(RISK_LABELS.get(risk, risk), RISK_COLORS.get(risk, "#6b7280"))


def forecast_badge_html(status: str) -> str:
    return badge_html(
        FORECAST_LABELS.get(status, status),
        FORECAST_COLORS.get(status, "#6b7280"),
    )


def calc_forecast(row: pd.Series) -> dict:
    actual_work = safe_float(row.get("actual_work_value")) or 0.0
    actual_hours = safe_float(row.get("actual_direct_hours")) or 0.0
    plan_work = safe_float(row.get("plan_work_value_month")) or 0.0
    plan_hours = safe_float(row.get("plan_direct_hours_month")) or 0.0
    plan_cost = safe_float(row.get("plan_direct_cost_month")) or 0.0

    base = {
        "expected_direct_cost_at_completion": plan_cost,
    }

    if actual_hours == 0 or actual_work == 0:
        return {
            **base,
            "work_value_per_hour": None,
            "forecast_work_value_at_plan_hours": None,
            "forecast_remaining_work_value": None,
            "forecast_margin_at_completion": None,
            "forecast_status": "NO_FACT",
            "forecast_text": FORECAST_TEXTS["NO_FACT"],
        }

    work_value_per_hour = actual_work / actual_hours
    forecast_work_value_at_plan_hours = work_value_per_hour * plan_hours
    forecast_remaining_work_value = plan_work - forecast_work_value_at_plan_hours
    forecast_margin_at_completion = (
        forecast_work_value_at_plan_hours - plan_cost
    )

    if forecast_margin_at_completion <= 0:
        status = "LOSS_FORECAST"
    elif forecast_work_value_at_plan_hours >= plan_work:
        status = "ON_TRACK"
    else:
        status = "AT_RISK"

    return {
        **base,
        "work_value_per_hour": work_value_per_hour,
        "forecast_work_value_at_plan_hours": forecast_work_value_at_plan_hours,
        "forecast_remaining_work_value": forecast_remaining_work_value,
        "forecast_margin_at_completion": forecast_margin_at_completion,
        "forecast_status": status,
        "forecast_text": FORECAST_TEXTS[status],
    }


def enrich_with_forecast(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    forecasts = df.apply(calc_forecast, axis=1, result_type="expand")
    return pd.concat([df.reset_index(drop=True), forecasts.reset_index(drop=True)], axis=1)


def counter_cell(
    label: str,
    plan_label: str,
    plan: str,
    fact_label: str,
    fact: str,
    remaining_label: str,
    remaining: str,
    note: str = "",
) -> str:
    note_html = (
        f'<div style="font-size:11px;color:#64748b;margin-top:6px;">{note}</div>'
        if note
        else ""
    )
    return f"""
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px;">
        <div style="font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;
                    letter-spacing:0.05em;margin-bottom:10px;">{label}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px;">
            <div><div style="color:#94a3b8;">{plan_label}</div>
                <div style="font-weight:700;color:#0f172a;">{plan}</div></div>
            <div><div style="color:#94a3b8;">{fact_label}</div>
                <div style="font-weight:700;color:#0f172a;">{fact}</div></div>
            <div><div style="color:#94a3b8;">{remaining_label}</div>
                <div style="font-weight:700;color:#0f172a;">{remaining}</div></div>
        </div>
        {note_html}
    </div>
    """


def four_counters_html(row: pd.Series) -> str:
    fact_ok = has_fact(row)
    status_note = "" if fact_ok else FACT_PENDING_STATUS

    plan_work = row.get("plan_work_value_month")
    actual_work = safe_float(row.get("actual_work_value")) or 0.0
    rem_work = row.get("remaining_work_value")

    plan_hours = row.get("plan_direct_hours_month")
    actual_hours = safe_float(row.get("actual_direct_hours")) or 0.0
    rem_hours = row.get("remaining_direct_hours")

    plan_cost = row.get("plan_direct_cost_month")
    actual_cost = safe_float(row.get("actual_direct_cost")) or 0.0
    rem_cost = row.get("remaining_direct_cost")

    actual_qty = safe_float(row.get("actual_qty_total")) or 0.0
    fact_rows = int(safe_float(row.get("fact_rows")) or 0)

    a = counter_cell(
        "1. Объём",
        "Плановый объём",
        "—",
        "Факт мастера (Daily Progress)",
        qty_fmt(actual_qty) if fact_ok else "0",
        "Остаток",
        "—",
        QUANTITY_LAYER2_NOTE,
    )
    b = counter_cell(
        "2. Стоимость объёма",
        "Плановая стоимость работ",
        money(plan_work),
        "EV по факту мастера",
        money(actual_work),
        "Остаток",
        money(rem_work),
        status_note or "Плановая стоимость работ → EV по факту мастера → остаток.",
    )
    c = counter_cell(
        "3. Чел-часы звена",
        "План direct hours",
        hours_fmt(plan_hours),
        "Факт direct hours из смен",
        hours_fmt(actual_hours),
        "Остаток",
        hours_fmt(rem_hours),
        status_note or "План direct hours → факт из смен → остаток.",
    )
    d = counter_cell(
        "4. Затраты звена",
        "План direct cost",
        money(plan_cost),
        "Факт / списание direct cost",
        money(actual_cost),
        "Остаток",
        money(rem_cost),
        (
            f"Количество записей Daily Progress: {fact_rows}. "
            + (status_note or "План direct cost → факт/списание → остаток.")
        ),
    )

    return f"""
    <div style="display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:14px;">
        {a}{b}{c}{d}
    </div>
    """


def progress_card_html(
    title: str,
    current_label: str,
    current_value: str,
    plan_value: str,
    remaining_value: str,
    pct: float | None,
    bar_color: str = "#2563eb",
    footnote: str = "",
    show_burn: bool = True,
) -> str:
    if not show_burn:
        bar_html = ""
        pct_text = ""
    elif pct is None:
        bar_width = 0
        pct_text = "—"
        bar_html = (
            '<div style="height:9px;background:#e2e8f0;border-radius:999px;overflow:hidden;margin-bottom:6px;">'
            f'<div style="width:{bar_width:.1f}%;height:100%;background:{bar_color};"></div></div>'
            f'<div style="font-size:12px;font-weight:700;color:#334155;">{pct_text}</div>'
        )
    else:
        bar_width = min(max(pct, 0.0), 1.0) * 100
        pct_text = pct_fmt(pct)
        bar_html = (
            '<div style="height:9px;background:#e2e8f0;border-radius:999px;overflow:hidden;margin-bottom:6px;">'
            f'<div style="width:{bar_width:.1f}%;height:100%;background:{bar_color};"></div></div>'
            f'<div style="font-size:12px;font-weight:700;color:#334155;">{pct_text}</div>'
        )

    plan_remain_html = ""
    if plan_value or remaining_value:
        plan_remain_html = (
            '<div style="display:flex;justify-content:space-between;font-size:12px;'
            'color:#475569;margin-bottom:6px;">'
            f"<span>План: <strong>{plan_value}</strong></span>"
            f"<span>Остаток: <strong>{remaining_value}</strong></span></div>"
        )

    footnote_html = (
        f'<div style="font-size:11px;color:#64748b;margin-top:8px;line-height:1.4;">{footnote}</div>'
        if footnote
        else ""
    )

    return f"""
    <div style="border:1px solid #dbe3ee;border-radius:12px;padding:16px;
                background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%);
                box-shadow:0 4px 14px rgba(15,23,42,0.06);height:100%;">
        <div style="font-size:13px;font-weight:700;color:#334155;margin-bottom:12px;">{title}</div>
        <div style="font-size:22px;font-weight:800;color:#0f172a;margin-bottom:4px;">{current_value}</div>
        <div style="font-size:11px;color:#64748b;margin-bottom:10px;">{current_label}</div>
        {plan_remain_html}
        {bar_html}
        {footnote_html}
    </div>
    """


def quantity_fact_card_html(row: pd.Series) -> str:
    fact_ok = has_fact(row)
    qty = safe_float(row.get("actual_qty_total")) or 0.0
    fact_rows = int(safe_float(row.get("fact_rows")) or 0)
    status = fact_status_html(row)
    note = QUANTITY_LAYER2_NOTE
    if not fact_ok:
        note = f"{FACT_PENDING_STATUS}. {note}"

    return (
        '<div style="border:1px solid #dbe3ee;border-radius:12px;padding:16px;'
        'background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%);'
        'box-shadow:0 4px 14px rgba(15,23,42,0.06);height:100%;">'
        '<div style="font-size:13px;font-weight:700;color:#334155;margin-bottom:12px;">'
        "Quantity · информация</div>"
        f'<div style="font-size:22px;font-weight:800;color:#0f172a;margin-bottom:4px;">'
        f"{qty_fmt(qty)}</div>"
        '<div style="font-size:11px;color:#64748b;margin-bottom:8px;">'
        "actual_qty_total · Daily Progress (без burn %)</div>"
        '<div style="font-size:12px;color:#475569;margin-bottom:6px;">'
        f"Количество записей Daily Progress: <strong>{fact_rows}</strong></div>"
        f'<div style="margin-bottom:8px;">{status}</div>'
        f'<div style="font-size:11px;color:#64748b;line-height:1.4;">{note}</div>'
        "</div>"
    )


def four_progress_cards_html(row: pd.Series, risk: str) -> str:
    fact_ok = has_fact(row)
    pending_note = "" if fact_ok else f"{FACT_PENDING_STATUS}. "

    actual_work = safe_float(row.get("actual_work_value")) or 0.0
    actual_hours = safe_float(row.get("actual_direct_hours")) or 0.0
    actual_cost = safe_float(row.get("actual_direct_cost")) or 0.0
    fact_rows = int(safe_float(row.get("fact_rows")) or 0)

    work_burn_pct = burn_pct_from_view(
        row, "work_value_burn_pct", "actual_work_value", "plan_work_value_month"
    )
    hours_burn_pct = burn_pct_from_view(
        row, "direct_hours_burn_pct", "actual_direct_hours", "plan_direct_hours_month"
    )
    cost_burn_pct = burn_pct_from_view(
        row, "direct_cost_burn_pct", "actual_direct_cost", "plan_direct_cost_month"
    )
    risk_color = RISK_COLORS.get(risk, "#2563eb")

    cards = [
        progress_card_html(
            "Work Value Burn",
            "actual_work_value · EV по факту мастера",
            money(actual_work),
            money(row.get("plan_work_value_month")),
            money(row.get("remaining_work_value")),
            work_burn_pct if fact_ok else 0.0,
            bar_color="#0ea5e9",
            footnote=f"{pending_note}План → EV по факту мастера → остаток. Записей DP: {fact_rows}.",
        ),
        progress_card_html(
            "Direct Hours Burn",
            "actual_direct_hours · факт из смен",
            hours_fmt(actual_hours),
            hours_fmt(row.get("plan_direct_hours_month")),
            hours_fmt(row.get("remaining_direct_hours")),
            hours_burn_pct if fact_ok else 0.0,
            bar_color="#2563eb",
            footnote=f"{pending_note}План direct hours → факт из смен → остаток.",
        ),
        progress_card_html(
            "Direct Cost Burn",
            "actual_direct_cost · факт/списание",
            money(actual_cost),
            money(row.get("plan_direct_cost_month")),
            money(row.get("remaining_direct_cost")),
            cost_burn_pct if fact_ok else 0.0,
            bar_color=risk_color,
            footnote=f"{pending_note}План direct cost → факт/списание → остаток.",
        ),
        quantity_fact_card_html(row),
    ]

    grid = "".join(
        f'<div style="min-width:0;">{card}</div>' for card in cards
    )
    return f"""
    <div style="display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:14px;">
        {grid}
    </div>
    """


def crew_header_html(row: pd.Series, risk: str) -> str:
    crew_name = row.get("crew") if pd.notna(row.get("crew")) else "—"
    month = row.get("month_key") if pd.notna(row.get("month_key")) else "—"
    fact_rows = int(safe_float(row.get("fact_rows")) or 0)
    status = fact_status_html(row)
    badge = risk_badge_html(risk)
    share = pct_fmt(row.get("direct_cost_share"))
    margin = money(row.get("margin_after_direct"))
    status_block = (
        f'<div style="margin-top:4px;">{status}</div>' if status else ""
    )
    return (
        '<div style="display:flex;justify-content:space-between;align-items:center;'
        'flex-wrap:wrap;gap:10px;margin-bottom:14px;">'
        "<div>"
        '<div style="font-size:12px;color:#64748b;text-transform:uppercase;'
        f'letter-spacing:0.06em;">Crew Burn-Down · {VIEW_NAME}</div>'
        f'<div style="font-size:26px;font-weight:800;color:#0f172a;">{crew_name}</div>'
        f'<div style="font-size:13px;color:#475569;">{month}</div>'
        '<div style="font-size:12px;color:#475569;margin-top:4px;">'
        f"Количество записей Daily Progress: <strong>{fact_rows}</strong></div>"
        f"{status_block}"
        "</div>"
        '<div style="text-align:right;">'
        f'<div style="margin-bottom:6px;">{badge}</div>'
        '<div style="font-size:11px;color:#64748b;">'
        f"Direct share: {share} · Маржа: {margin}</div>"
        "</div></div>"
    )


def forecast_block_html(row: pd.Series, forecast: dict) -> str:
    status = forecast.get("forecast_status", "NO_FACT")
    badge = forecast_badge_html(status)
    text = forecast.get("forecast_text", "")
    ev_per_hour = money_per_hour(forecast.get("work_value_per_hour"))
    forecast_ev = money(forecast.get("forecast_work_value_at_plan_hours"))
    plan_work = money(row.get("plan_work_value_month"))
    forecast_margin = money(forecast.get("forecast_margin_at_completion"))

    return (
        '<div style="border:1px solid #dbe3ee;border-radius:12px;padding:18px 20px;'
        'background:#fff;box-shadow:0 4px 14px rgba(15,23,42,0.06);margin-top:14px;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;'
        'flex-wrap:wrap;gap:10px;margin-bottom:14px;">'
        '<div style="font-size:15px;font-weight:800;color:#0f172a;">Прогноз исполнения</div>'
        f"<div>{badge}</div></div>"
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));'
        'gap:12px;margin-bottom:12px;">'
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;">'
        '<div style="font-size:11px;color:#64748b;">Факт EV / чел-ч</div>'
        f'<div style="font-size:18px;font-weight:700;color:#0f172a;">{ev_per_hour}</div></div>'
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;">'
        '<div style="font-size:11px;color:#64748b;">Прогноз EV при всех плановых часах</div>'
        f'<div style="font-size:18px;font-weight:700;color:#0f172a;">{forecast_ev}</div></div>'
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;">'
        '<div style="font-size:11px;color:#64748b;">Плановая стоимость работ</div>'
        f'<div style="font-size:18px;font-weight:700;color:#0f172a;">{plan_work}</div></div>'
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;">'
        '<div style="font-size:11px;color:#64748b;">Прогнозная маржа после direct</div>'
        f'<div style="font-size:18px;font-weight:700;color:#0f172a;">{forecast_margin}</div></div>'
        "</div>"
        f'<div style="font-size:12px;color:#475569;line-height:1.5;">{text}</div>'
        "</div>"
    )


def render_compact_table(df: pd.DataFrame):
    if df.empty:
        st.info("Нет данных для отображения.")
        return

    table_df = enrich_with_forecast(df)
    rows_html = []
    for _, row in table_df.iterrows():
        risk = calc_risk(row.get("direct_cost_share"))
        risk_color = RISK_COLORS.get(risk, "#6b7280")
        fc_status = row.get("forecast_status", "NO_FACT")
        fc_color = FORECAST_COLORS.get(fc_status, "#6b7280")
        rows_html.append(
            "<tr>"
            f"<td><strong>{row.get('crew', '—')}</strong></td>"
            f"<td>{money(row.get('plan_work_value_month'))}</td>"
            f"<td>{hours_fmt(row.get('plan_direct_hours_month'))}</td>"
            f"<td>{money(row.get('plan_direct_cost_month'))}</td>"
            f"<td>{hours_fmt(row.get('actual_direct_hours'))}</td>"
            f"<td>{money(row.get('actual_direct_cost'))}</td>"
            f"<td>{int(safe_float(row.get('fact_rows')) or 0)}</td>"
            f"<td>{money(row.get('margin_after_direct'))}</td>"
            f"<td>{pct_fmt(row.get('direct_cost_share'))}</td>"
            f'<td><span style="background:{risk_color};color:#fff;padding:3px 8px;'
            f'border-radius:999px;font-size:11px;font-weight:700;">'
            f"{RISK_LABELS.get(risk, risk)}</span></td>"
            f"<td>{money_per_hour(row.get('work_value_per_hour'))}</td>"
            f"<td>{money(row.get('forecast_work_value_at_plan_hours'))}</td>"
            f"<td>{money(row.get('forecast_margin_at_completion'))}</td>"
            f'<td><span style="background:{fc_color};color:#fff;padding:3px 8px;'
            f'border-radius:999px;font-size:11px;font-weight:700;">'
            f"{FORECAST_LABELS.get(fc_status, fc_status)}</span></td>"
            "</tr>"
        )

    render_html(
        "<div style='overflow-x:auto;border:1px solid #e2e8f0;border-radius:10px;'>"
        "<table style='width:100%;border-collapse:collapse;font-size:12px;background:#fff;'>"
        "<thead><tr style='background:#f1f5f9;color:#334155;text-align:left;'>"
        "<th style='padding:8px 10px;'>Звено</th>"
        "<th style='padding:8px 10px;'>План работ</th>"
        "<th style='padding:8px 10px;'>План ч</th>"
        "<th style='padding:8px 10px;'>План cost</th>"
        "<th style='padding:8px 10px;'>Факт ч</th>"
        "<th style='padding:8px 10px;'>Факт cost</th>"
        "<th style='padding:8px 10px;'>DP rows</th>"
        "<th style='padding:8px 10px;'>Маржа</th>"
        "<th style='padding:8px 10px;'>Share</th>"
        "<th style='padding:8px 10px;'>Риск</th>"
        "<th style='padding:8px 10px;'>EV/ч</th>"
        "<th style='padding:8px 10px;'>Прогноз EV</th>"
        "<th style='padding:8px 10px;'>Прогноз маржа</th>"
        "<th style='padding:8px 10px;'>Прогноз</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table></div>"
        "<p style='font-size:11px;color:#64748b;margin-top:6px;'>"
        "Прогноз рассчитан в Python: выработка EV/ч × плановые часы.</p>"
    )


# ---------------- UI ----------------

st.title("Счётчик звена")
st.caption(
    "Crew Burn-Down · Month + Crew. "
    "Источник: v_crew_burndown_with_fact (план + факт Daily Progress)."
)

st.info(
    "Это Layer 1 — финансово-ресурсный счётчик звена. "
    "Детализация по BOQ / IWP / System / Operation будет в Layer 2."
)

df = load_burndown()

if df.empty:
    st.warning(f"Витрина {VIEW_NAME} пока пустая.")
    st.stop()

col_f1, col_f2, col_f3 = st.columns([1.2, 1.2, 0.4])

with col_f1:
    selected_month = st.selectbox("Месяц", filter_options(df, "month_key"), label_visibility="visible")

with col_f2:
    month_filtered = df.copy()
    if selected_month != "Все":
        month_filtered = month_filtered[
            month_filtered["month_key"].astype(str) == selected_month
        ]
    selected_crew = st.selectbox(
        "Звено", filter_options(month_filtered, "crew"), label_visibility="visible"
    )

with col_f3:
    render_html("<div style='height:28px'></div>")
    if st.button("↻", help="Обновить данные", use_container_width=True):
        load_burndown.clear()
        st.rerun()

filtered = apply_filters(df, selected_month, selected_crew)

st.divider()

# --- 4 счётчика + progress cards ---
st.subheader("4 счётчика звена")

if selected_crew == "Все":
    st.caption("Выберите звено, чтобы открыть счётчики и burn-карты.")
elif filtered.empty:
    st.warning("Нет данных для выбранного звена.")
else:
    card_row = filtered.iloc[0]
    risk = calc_risk(card_row.get("direct_cost_share"))

    render_html(crew_header_html(card_row, risk))
    st.markdown("#### Счётчики")
    render_html(four_counters_html(card_row))
    st.markdown("#### Burn-карты")
    render_html(four_progress_cards_html(card_row, risk))
    forecast = calc_forecast(card_row)
    render_html(forecast_block_html(card_row, forecast))

st.divider()

# --- Таблица всех звеньев месяца ---
st.subheader("Все звенья месяца")

if selected_month == "Все":
    st.caption("Выберите месяц для свода по звеньям.")
    month_table_df = pd.DataFrame()
else:
    month_table_df = df[df["month_key"].astype(str) == selected_month].copy()
    if "crew" in month_table_df.columns:
        month_table_df = month_table_df.sort_values("crew", na_position="last")

if month_table_df.empty:
    st.info("Нет строк для выбранного месяца.")
else:
    render_compact_table(month_table_df)
