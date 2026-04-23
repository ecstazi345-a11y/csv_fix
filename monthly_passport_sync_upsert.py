import os
import math
import re
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise ValueError("Не найдены SUPABASE_URL или SUPABASE_SECRET_KEY в файле .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

CSV_FILE = "monthly_passport_plan.csv"
TABLE_NAME = "monthly_passport_plan"


MONTHS_RU = {
    "января": "01",
    "февраля": "02",
    "марта": "03",
    "апреля": "04",
    "мая": "05",
    "июня": "06",
    "июля": "07",
    "августа": "08",
    "сентября": "09",
    "октября": "10",
    "ноября": "11",
    "декабря": "12",
}


def clean_value(value):
    if pd.isna(value):
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    # Преобразуем date / datetime в строку ISO для JSON
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    return value


def parse_numeric_value(value):
    """
    Преобразует строки вида:
    ₽2776,04
    ₽   375550,00
    70,000
    75,100
    в float
    """
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in {"nan", "none", "<na>"}:
        return None

    # убираем валюту и пробелы/неразрывные пробелы
    text = text.replace("₽", "")
    text = text.replace("\xa0", "")
    text = text.replace(" ", "")

    # оставляем только цифры, минус, запятую, точку
    text = re.sub(r"[^0-9,.\-]", "", text)

    if text == "":
        return None

    # если есть запятая, считаем ее десятичным разделителем
    # и удаляем точки как разделители тысяч
    if "," in text:
        text = text.replace(".", "")
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def parse_russian_date(value):
    """
    Преобразует строки вида:
    1 Февраля 2026 г.
    28 Февраля 2026 г.
    в date
    """
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in {"nan", "none", "<na>"}:
        return None

    text = text.replace(" г.", "").replace(" г", "").strip()
    parts = text.split()

    if len(parts) != 3:
        return None

    day, month_ru, year = parts
    month_ru = month_ru.lower()

    month = MONTHS_RU.get(month_ru)
    if not month:
        return None

    day = day.zfill(2)
    iso_text = f"{year}-{month}-{day}"

    try:
        return pd.to_datetime(iso_text, errors="coerce").date()
    except Exception:
        return None


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "Passport_Record_ID": "passport_record_id",
        "Project": "project",
        "Year_Quarter_Month_Week_ID": "year_quarter_month_week_id",
        "Month_Key": "month_key",
        "BOQ": "boq_code",
        "BOQ_Name": "boq_name",
        "IWP_ID_EXPORT": "iwp_id_export",
        "System_Label": "system_label",
        "Unit of Measure": "unit_of_measure",
        "Unit_Price": "unit_price",
        "Plan_Qty_Month": "plan_qty_month",
        "Plan_PV_WorkValue_auto": "plan_pv_workvalue_auto",
        "Plan_Work_Start_Date": "plan_work_start_date",
        "Plan_Work_Finish_Date": "plan_work_finish_date",
        "Facility_Building.": "facility_building",
        "Facility_Building": "facility_building",
        "crew": "crew",
        "Construction_Discipline.": "construction_discipline",
        "Construction_Discipline": "construction_discipline",
        "Budget_Status": "budget_status",
    }

    df = df.rename(columns=rename_map)

    required_columns = [
        "passport_record_id",
        "project",
        "year_quarter_month_week_id",
        "month_key",
        "boq_code",
        "boq_name",
        "iwp_id_export",
        "system_label",
        "unit_of_measure",
        "unit_price",
        "plan_qty_month",
        "plan_pv_workvalue_auto",
        "plan_work_start_date",
        "plan_work_finish_date",
        "facility_building",
        "crew",
        "construction_discipline",
        "budget_status",
    ]

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"В CSV не найдены обязательные колонки: {missing}")

    df = df[required_columns].copy()

    text_columns = [
        "passport_record_id",
        "project",
        "year_quarter_month_week_id",
        "month_key",
        "boq_code",
        "boq_name",
        "iwp_id_export",
        "system_label",
        "unit_of_measure",
        "facility_building",
        "crew",
        "construction_discipline",
        "budget_status",
    ]

    for col in text_columns:
        df[col] = df[col].astype("string").str.strip()

    numeric_columns = [
        "unit_price",
        "plan_qty_month",
        "plan_pv_workvalue_auto",
    ]

    for col in numeric_columns:
        df[col] = df[col].apply(parse_numeric_value)

    date_columns = [
        "plan_work_start_date",
        "plan_work_finish_date",
    ]

    for col in date_columns:
        df[col] = df[col].apply(parse_russian_date)

    return df


def print_duplicates(df: pd.DataFrame):
    duplicate_mask = df["passport_record_id"].duplicated(keep=False)
    duplicates = df[duplicate_mask].sort_values("passport_record_id")

    if duplicates.empty:
        print("Дублей passport_record_id не найдено.")
        return

    print("Найдены дубли passport_record_id:")
    preview_cols = [
        "passport_record_id",
        "month_key",
        "boq_code",
        "iwp_id_export",
        "system_label",
        "crew",
    ]
    existing_preview_cols = [c for c in preview_cols if c in duplicates.columns]
    print(duplicates[existing_preview_cols].to_string(index=False))


def upload_in_batches(records, batch_size=500):
    total = len(records)
    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        supabase.table(TABLE_NAME).upsert(
            batch, on_conflict="passport_record_id"
        ).execute()
        print(f"Загружен пакет {i + 1} - {min(i + batch_size, total)} из {total}")


def main():
    print("Читаем CSV...")
    df = pd.read_csv(CSV_FILE)

    print("Нормализуем данные...")
    df = normalize_dataframe(df)

    print("Проверяем дубли passport_record_id...")
    print_duplicates(df)

    print("Удаляем дубли, оставляем последнюю строку...")
    df = df.drop_duplicates(subset=["passport_record_id"], keep="last")

    print("Готовим записи...")
    records = df.to_dict(orient="records")
    records = [{k: clean_value(v) for k, v in r.items()} for r in records]

    print(f"Всего строк после удаления дублей: {len(records)}")

    print("Загружаем в Supabase...")
    upload_in_batches(records)

    print("Готово.")


if __name__ == "__main__":
    main()
