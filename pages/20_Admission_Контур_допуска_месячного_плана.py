import io
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st
from services.constraints_service import create_constraints_for_review_queue
from services.supabase_client import supabase


st.set_page_config(layout="wide")

st.title("Контур допуска месячного плана")
st.caption(
    "EXECUTABILITY / Monthly Plan Admission Layer — отвечает на вопрос: "
    "«Можно ли реально запускать месячный план в производство?»"
)
st.info(
    "Версия v1: мощность звена не считается автоматически без подтверждённого "
    "состава звена. В v2 проверка будет идти через отдельный контур экономики звена."
)


@st.cache_data(ttl=300)
def load_table(name: str, limit: int = 10000) -> pd.DataFrame:
    try:
        response = supabase.table(name).select("*").limit(limit).execute()
        return pd.DataFrame(response.data or [])
    except Exception as e:  # noqa: BLE001
        st.error(f"Не удалось загрузить таблицу {name}: {e}")
        return pd.DataFrame()


def to_num(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    result = df.copy()
    for col in cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    return result


def money(v: Any) -> str:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "0 ₽"
        return f"{float(v):,.0f} ₽".replace(",", " ")
    except Exception:  # noqa: BLE001
        return "0 ₽"


def pct(v: Any) -> str:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "0.0%"
        return f"{float(v):.1f}%"
    except Exception:  # noqa: BLE001
        return "0.0%"


def safe_str(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value)


def safe_num(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return 0.0


def options(df: pd.DataFrame, col: str) -> List[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = (
        df[col]
        .dropna()
        .astype(str)
        .str.strip()
    )
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def apply_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
    crew: str,
    review_status: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    res = df.copy()
    if project != "Все" and "project_code" in res.columns:
        res = res[res["project_code"].astype(str) == project]
    if month != "Все" and "month_key" in res.columns:
        res = res[res["month_key"].astype(str) == month]
    if facility != "Все" and "facility_building" in res.columns:
        res = res[res["facility_building"].astype(str) == facility]
    if discipline != "Все" and "construction_discipline" in res.columns:
        res = res[res["construction_discipline"].astype(str) == discipline]
    if crew != "Все" and "crew_id" in res.columns:
        res = res[res["crew_id"].astype(str) == crew]
    if review_status != "Все" and "review_status" in res.columns:
        res = res[res["review_status"].astype(str) == review_status]
    return res


def ensure_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Гарантируем наличие нужных колонок, чтобы не падать."""
    result = df.copy()
    for col in cols:
        if col not in result.columns:
            result[col] = pd.NA
    return result


def compute_check_boq_remaining(row: pd.Series) -> Tuple[str, str]:
    planned_raw = row.get("planned_qty")
    remaining_raw = row.get("planning_remaining_qty")
    planned_f = safe_num(planned_raw)
    remaining_f = safe_num(remaining_raw)

    if remaining_raw is None or pd.isna(remaining_raw):
        return "ОЖИДАЕТ", ""

    if remaining_f <= 0 and planned_f > 0:
        return "FAIL", "План превышает подтверждённый остаток"

    if planned_f <= remaining_f:
        return "PASS", ""

    if remaining_f <= 0:
        return "FAIL", "План превышает подтверждённый остаток"

    ratio = (planned_f - remaining_f) / remaining_f
    if ratio <= 0.10:
        return "WARNING", "План слегка превышает подтверждённый остаток"
    return "FAIL", "План превышает подтверждённый остаток"


def compute_check_norm(row: pd.Series) -> Tuple[str, str]:
    has_p50 = row.get("p50_hours_per_unit")
    has_p80 = row.get("p80_hours_per_unit")
    selected = row.get("selected_hours_per_unit")
    confidence = safe_str(row.get("confidence_level")).upper()

    has_any = False
    for v in (has_p50, has_p80, selected):
        try:
            if v is not None and not pd.isna(v) and float(v) > 0:
                has_any = True
                break
        except Exception:  # noqa: BLE001
            continue

    if not has_any:
        return "FAIL", "Нет подтверждённой производительности"

    if confidence == "LOW":
        return "WARNING", "Низкий уровень доверия к норме"

    return "PASS", ""


def _valid_crew_size(row: pd.Series) -> float:
    """Возвращает crew_size > 0 или 0.0, если состав звена не задан."""
    crew_size_raw = row.get("crew_size")
    if crew_size_raw is None or pd.isna(crew_size_raw):
        return 0.0
    crew_f = safe_num(crew_size_raw)
    return crew_f if crew_f > 0 else 0.0


def compute_crew_capacity(row: pd.Series) -> Tuple[str, str, float]:
    """
    Мощность звена: crew_size * 240 ч/мес.
    Без подстановки размера звена по умолчанию (v1).
    """
    required_f = safe_num(row.get("required_hours"))
    crew_f = _valid_crew_size(row)

    if crew_f > 0 and required_f > 0:
        crew_capacity_hours = crew_f * 240.0
        utilisation = required_f / crew_capacity_hours
        if utilisation <= 0.85:
            return "PASS", "", crew_capacity_hours
        if utilisation <= 1.0:
            return "WARNING", "Звено близко к пределу по часам", crew_capacity_hours
        return "FAIL", "Недостаточно мощности звена", crew_capacity_hours

    if required_f > 0:
        return (
            "WARNING",
            "Размер звена не задан. Мощность звена требует подтверждения.",
            0.0,
        )

    return "WARNING", "Не рассчитаны требуемые часы.", 0.0


def compute_front_readiness(row: pd.Series) -> Tuple[str, str]:
    facility_raw = row.get("facility_building")
    discipline_raw = row.get("construction_discipline")
    crew_id_raw = row.get("crew_id")

    facility = safe_str(facility_raw)
    discipline = safe_str(discipline_raw)
    crew_id = safe_str(crew_id_raw)

    if not facility or not discipline:
        return "FAIL", "Фронт требует подтверждения"

    if not crew_id:
        return "WARNING", "Не указан состав / идентификатор звена"

    return "PASS", ""


def compute_acceptability(row: pd.Series) -> Tuple[str, str]:
    accepted_qty = row.get("customer_accepted_qty")
    line_status_raw = row.get("line_status")
    line_status = "" if line_status_raw is None or pd.isna(line_status_raw) else str(line_status_raw).upper()

    if line_status in {"HOLD", "REJECTED"}:
        return "FAIL", "Есть риск непризнания объёма"

    if safe_num(accepted_qty) > 0:
        return "PASS", ""

    return "WARNING", "Нет подтверждённого признания объёма"


def aggregate_executability(row: pd.Series) -> str:
    checks = [
        row.get("check_boq_remaining_status"),
        row.get("check_norm_status"),
        row.get("check_crew_capacity_status"),
        row.get("check_front_readiness_status"),
        row.get("check_acceptability_status"),
    ]
    checks = [str(c) for c in checks if c is not None]
    upper = [c.upper() for c in checks]
    if any(c == "FAIL" for c in upper):
        return "BLOCKED"
    if any(c == "WARNING" for c in upper):
        return "READY_WITH_RISK"
    if all(c == "PASS" for c in upper) and upper:
        return "READY_TO_EXECUTE"
    return "ОЖИДАЕТ"


STATUS_COLOR = {
    "PASS": "#16a34a",
    "WARNING": "#eab308",
    "FAIL": "#dc2626",
    "HOLD": "#ea580c",
    "ОЖИДАЕТ": "#6b7280",
}

RESULT_COLOR = {
    "READY_TO_EXECUTE": "#16a34a",
    "READY_WITH_RISK": "#eab308",
    "BLOCKED": "#dc2626",
    "ОЖИДАЕТ": "#6b7280",
}

STATUS_RU = {
    "PASS": "ПРОЙДЕНО",
    "WARNING": "РИСК",
    "FAIL": "БЛОК",
    "HOLD": "СТОП",
    "ОЖИДАЕТ": "ОЖИДАЕТ",
}

RESULT_RU = {
    "READY_TO_EXECUTE": "МОЖНО ЗАПУСКАТЬ",
    "READY_WITH_RISK": "МОЖНО С РИСКОМ",
    "BLOCKED": "ЗАБЛОКИРОВАНО",
    "ОЖИДАЕТ": "ОЖИДАЕТ",
}

COLUMN_RU = {
    "project_code": "Проект",
    "month_key": "Месяц",
    "facility_building": "Здание / объект",
    "construction_discipline": "Дисциплина",
    "boq_code": "BOQ-код",
    "boq_name": "Наименование работы",
    "crew_id": "Звено",
    "planned_qty": "Плановый объём",
    "plan_value": "Плановая стоимость, ₽",
    "required_hours": "Требуется чел-ч",
    "check_boq_remaining_status": "Проверка остатка",
    "check_norm_status": "Проверка нормы",
    "check_crew_capacity_status": "Проверка мощности звена",
    "check_front_readiness_status": "Проверка фронта",
    "check_acceptability_status": "Проверка признаваемости",
    "executability_result": "Итог допуска",
    "decision_comment": "Комментарий",
}


def norm_status_key(value: Any) -> str:
    """
    Нормализация для подсветки: принимает и тех. значения (PASS/WARNING/...)
    и русские (ПРОЙДЕНО/РИСК/...) — возвращает ключ для словарей цветов.
    """
    if value is None or pd.isna(value):
        return "ОЖИДАЕТ"
    raw = str(value).strip().upper()
    rev = {v: k for k, v in STATUS_RU.items()}
    if raw in rev:
        return rev[raw]
    return raw


def norm_result_key(value: Any) -> str:
    if value is None or pd.isna(value):
        return "ОЖИДАЕТ"
    raw = str(value).strip().upper()
    rev = {v: k for k, v in RESULT_RU.items()}
    if raw in rev:
        return rev[raw]
    return raw


def color_status(val: Any) -> str:
    key = norm_status_key(val)
    color = STATUS_COLOR.get(key, "")
    return f"color: {color}; font-weight: 600;" if color else ""


def color_result(val: Any) -> str:
    key = norm_result_key(val)
    color = RESULT_COLOR.get(key, "")
    return f"color: {color}; font-weight: 700;" if color else ""


def main() -> None:
    base_df = load_table("monthly_plan_review_queue")

    if base_df.empty:
        st.warning("Нет данных в monthly_plan_review_queue.")
        return

    # фильтры
    cols = st.columns(6)
    project_sel = cols[0].selectbox("Проект", options(base_df, "project_code"))
    month_sel = cols[1].selectbox("Месяц", options(base_df, "month_key"))
    facility_sel = cols[2].selectbox("Здание / объект", options(base_df, "facility_building"))
    discipline_sel = cols[3].selectbox(
        "Дисциплина", options(base_df, "construction_discipline")
    )
    crew_sel = cols[4].selectbox("Звено", options(base_df, "crew_id"))
    review_status_sel = cols[5].selectbox(
        "Статус в очереди", options(base_df, "review_status")
    )

    df = apply_filters(
        base_df,
        project_sel,
        month_sel,
        facility_sel,
        discipline_sel,
        crew_sel,
        review_status_sel,
    )

    gen_col, _ = st.columns([1, 4])
    with gen_col:
        if st.button("Сформировать проверки по отделам", key="gen_department_constraints"):
            summary = create_constraints_for_review_queue(
                project_code=None if project_sel == "Все" else project_sel,
                month_key=None if month_sel == "Все" else month_sel,
            )
            st.success(
                f"Создано: {summary['created_count']} · "
                f"Пропущено (дубли): {summary['skipped_count']} · "
                f"Исходных строк очереди: {summary['source_rows_count']}"
            )
            if summary["errors"]:
                for err in summary["errors"]:
                    st.error(err)

    needed_numeric = [
        "planned_qty",
        "planning_remaining_qty",
        "p50_hours_per_unit",
        "p80_hours_per_unit",
        "selected_hours_per_unit",
        "required_hours",
        "crew_size",
        "customer_accepted_qty",
        "plan_value",
    ]
    df = ensure_columns(df, needed_numeric + ["line_status"])
    df = to_num(df, needed_numeric)

    # вычисляем проверки
    comments: Dict[int, List[str]] = {}
    for idx, row in df.iterrows():
        row_comments: List[str] = []

        status, msg = compute_check_boq_remaining(row)
        df.at[idx, "check_boq_remaining_status"] = status
        if msg:
            row_comments.append(msg)

        status, msg = compute_check_norm(row)
        df.at[idx, "check_norm_status"] = status
        if msg:
            row_comments.append(msg)

        status, msg, capacity = compute_crew_capacity(row)
        df.at[idx, "check_crew_capacity_status"] = status
        df.at[idx, "crew_capacity_hours"] = capacity
        if msg:
            row_comments.append(msg)

        status, msg = compute_front_readiness(row)
        df.at[idx, "check_front_readiness_status"] = status
        if msg:
            row_comments.append(msg)

        status, msg = compute_acceptability(row)
        df.at[idx, "check_acceptability_status"] = status
        if msg:
            row_comments.append(msg)

        df.at[idx, "executability_result"] = aggregate_executability(df.loc[idx])
        if row_comments:
            comments[idx] = row_comments

    # decision_comment — краткий текст по строке
    decision_comment_col = []
    for idx, row in df.iterrows():
        if idx in comments:
            unique_msgs = list(dict.fromkeys(comments[idx]))
            decision_comment_col.append(" · ".join(unique_msgs))
        else:
            decision_comment_col.append("")
    df["decision_comment"] = decision_comment_col

    # KPI
    df = ensure_columns(df, ["executability_result", "plan_value"])
    df = to_num(df, ["plan_value"])

    total_rows = len(df)
    total_value = float(df["plan_value"].fillna(0).sum()) if "plan_value" in df.columns else 0.0

    ready_mask = df["executability_result"].isin(["READY_TO_EXECUTE", "READY_WITH_RISK"])
    ready_value = float(df[ready_mask]["plan_value"].fillna(0).sum()) if total_rows else 0.0
    ready_to_execute_value = float(
        df[df["executability_result"] == "READY_TO_EXECUTE"]["plan_value"].fillna(0).sum()
    )
    ready_with_risk_value = float(
        df[df["executability_result"] == "READY_WITH_RISK"]["plan_value"].fillna(0).sum()
    )
    blocked_value = float(
        df[df["executability_result"] == "BLOCKED"]["plan_value"].fillna(0).sum()
    )
    ready_pct = (ready_value / total_value * 100.0) if total_value > 0 else 0.0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Всего строк на допуске", total_rows)
    k2.metric("Общая стоимость плана", money(total_value))
    k3.metric("Можно запускать, ₽", money(ready_to_execute_value))
    k4.metric("Можно с риском, ₽", money(ready_with_risk_value))
    k5.metric("Заблокировано, ₽", money(blocked_value))
    k6.metric("% допуска месяца", pct(ready_pct))

    # общий статус месяца
    st.markdown("---")
    if ready_pct >= 85.0:
        st.success("🟢 МЕСЯЦ ГОТОВ К ЗАПУСКУ")
    elif ready_pct >= 60.0:
        st.warning("🟡 МЕСЯЦ ЧАСТИЧНО ГОТОВ")
    else:
        st.error("🔴 МЕСЯЦ НЕ ГОТОВ")

    # основная таблица
    st.markdown("### Месячный план — статус допуска по строкам")
    base_cols = [
        "project_code",
        "month_key",
        "facility_building",
        "construction_discipline",
        "boq_code",
        "boq_name",
        "crew_id",
        "planned_qty",
        "plan_value",
        "required_hours",
        "check_boq_remaining_status",
        "check_norm_status",
        "check_crew_capacity_status",
        "check_front_readiness_status",
        "check_acceptability_status",
        "executability_result",
        "decision_comment",
    ]
    df_view = ensure_columns(df, base_cols)[base_cols]

    status_cols = [
        "check_boq_remaining_status",
        "check_norm_status",
        "check_crew_capacity_status",
        "check_front_readiness_status",
        "check_acceptability_status",
    ]

    display_cols = base_cols
    display_df = df_view[display_cols].copy()
    for col in status_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].map(STATUS_RU).fillna(display_df[col])
    if "executability_result" in display_df.columns:
        display_df["executability_result"] = (
            display_df["executability_result"]
            .map(RESULT_RU)
            .fillna(display_df["executability_result"])
        )
    display_df = display_df.rename(columns=COLUMN_RU)

    status_cols_ru = [COLUMN_RU[c] for c in status_cols if c in COLUMN_RU]
    result_col_ru = COLUMN_RU["executability_result"]

    def style_df(df_in: pd.DataFrame):
        styler = df_in.style
        for col in status_cols_ru:
            if col in df_in.columns:
                if hasattr(styler, "map"):
                    styler = styler.map(color_status, subset=pd.IndexSlice[:, [col]])
                else:
                    styler = styler.applymap(color_status, subset=pd.IndexSlice[:, [col]])
        if result_col_ru in df_in.columns:
            if hasattr(styler, "map"):
                styler = styler.map(
                    color_result, subset=pd.IndexSlice[:, [result_col_ru]]
                )
            else:
                styler = styler.applymap(
                    color_result, subset=pd.IndexSlice[:, [result_col_ru]]
                )
        return styler

    st.dataframe(
        style_df(display_df),
        use_container_width=True,
        hide_index=True,
    )

    # BLOCKED
    st.markdown("### Заблокированные строки")
    blocked_df = df[df["executability_result"] == "BLOCKED"].copy()
    blocked_df = blocked_df.sort_values("plan_value", ascending=False)
    if blocked_df.empty:
        st.caption("Заблокированных строк нет.")
    else:
        blocked_display_df = ensure_columns(blocked_df, display_cols)[display_cols].copy()
        for col in status_cols:
            if col in blocked_display_df.columns:
                blocked_display_df[col] = blocked_display_df[col].map(STATUS_RU).fillna(
                    blocked_display_df[col]
                )
        if "executability_result" in blocked_display_df.columns:
            blocked_display_df["executability_result"] = (
                blocked_display_df["executability_result"]
                .map(RESULT_RU)
                .fillna(blocked_display_df["executability_result"])
            )
        blocked_display_df = blocked_display_df.rename(columns=COLUMN_RU)
        st.dataframe(
            style_df(
                blocked_display_df,
            ),
            use_container_width=True,
            hide_index=True,
        )

    # READY_WITH_RISK
    st.markdown("### Строки с риском")
    risk_df = df[df["executability_result"] == "READY_WITH_RISK"].copy()
    if risk_df.empty:
        st.caption("Строк с риском нет.")
    else:
        risk_display_df = ensure_columns(risk_df, display_cols)[display_cols].copy()
        for col in status_cols:
            if col in risk_display_df.columns:
                risk_display_df[col] = risk_display_df[col].map(STATUS_RU).fillna(
                    risk_display_df[col]
                )
        if "executability_result" in risk_display_df.columns:
            risk_display_df["executability_result"] = (
                risk_display_df["executability_result"]
                .map(RESULT_RU)
                .fillna(risk_display_df["executability_result"])
            )
        risk_display_df = risk_display_df.rename(columns=COLUMN_RU)
        st.dataframe(
            style_df(
                risk_display_df,
            ),
            use_container_width=True,
            hide_index=True,
        )

    # TOP LIMITATIONS
    main_bottleneck = "Ограничений не выявлено"
    st.markdown("### Главные ограничения")
    limitations: List[Dict[str, Any]] = []
    for _, row in df_view.iterrows():
        plan_val = safe_num(row.get("plan_value"))
        if row.get("check_boq_remaining_status") in ["FAIL", "WARNING"]:
            limitations.append(
                {"restriction_reason": "Проблема с остатком BOQ", "plan_value": plan_val}
            )
        if row.get("check_norm_status") in ["FAIL", "WARNING"]:
            limitations.append(
                {"restriction_reason": "Проблема с нормой выработки", "plan_value": plan_val}
            )
        if row.get("check_crew_capacity_status") in ["FAIL", "WARNING"]:
            limitations.append(
                {"restriction_reason": "Недостаточная мощность звена", "plan_value": plan_val}
            )
        if row.get("check_front_readiness_status") in ["FAIL", "WARNING"]:
            limitations.append(
                {"restriction_reason": "Фронт требует подтверждения", "plan_value": plan_val}
            )
        if row.get("check_acceptability_status") in ["FAIL", "WARNING"]:
            limitations.append(
                {"restriction_reason": "Риск непризнания объёма", "plan_value": plan_val}
            )

    limitations_df = pd.DataFrame(limitations)
    if limitations_df.empty:
        st.info("Ограничений не выявлено.")
    else:
        top_limitations = (
            limitations_df.groupby("restriction_reason", as_index=False)
            .agg(
                rows_count=("restriction_reason", "count"),
                plan_value=("plan_value", "sum"),
            )
            .sort_values("plan_value", ascending=False)
        )
        top_limitations["plan_value_fmt"] = top_limitations["plan_value"].apply(money)
        main_bottleneck = str(top_limitations.iloc[0]["restriction_reason"])
        st.dataframe(
            top_limitations[["restriction_reason", "rows_count", "plan_value_fmt"]]
            .rename(
                columns={
                    "restriction_reason": "Причина",
                    "rows_count": "Кол-во строк",
                    "plan_value_fmt": "Стоимость, ₽",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    # CSV export
    st.markdown("### Выгрузка BLOCKED строк")
    if blocked_df.empty:
        st.caption("BLOCKED строки отсутствуют — выгружать нечего.")
    else:
        # Экспортируем русифицированную таблицу (для Excel / печати на стройке)
        blocked_export = blocked_display_df if "blocked_display_df" in locals() else ensure_columns(blocked_df, base_cols)[base_cols]
        csv_buf = io.StringIO()
        blocked_export.to_csv(csv_buf, index=False)
        st.download_button(
            "Выгрузить BLOCKED строки в CSV",
            data=csv_buf.getvalue().encode("utf-8-sig"),
            file_name="monthly_plan_blocked.csv",
            mime="text/csv",
        )

    # Управленческий вывод
    st.markdown("### Управленческий вывод")
    st.markdown(
        f"- **Сколько денег реально можно запускать:** {money(ready_value)} "
        f"(READY_TO_EXECUTE + READY_WITH_RISK)."
    )
    st.markdown(f"- **Сколько денег заблокировано:** {money(blocked_value)} (BLOCKED).")

    if main_bottleneck and main_bottleneck != "Ограничений не выявлено":
        st.markdown(f"- **Главное ограничение:** {main_bottleneck}")
    else:
        st.markdown("- **Главное ограничение:** ограничений не выявлено.")

    st.markdown(
        "- **Рекомендация:** сначала снять ограничения по самым дорогим строкам плана "
        "в статусе BLOCKED."
    )


if __name__ == "__main__":
    main()

