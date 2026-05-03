import os
import requests
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_MONTHLY_PASSPORT_PLAN_TABLE_ID")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

SUPABASE_TABLE = "monthly_passport_plan"

SUPABASE_TABLE = "monthly_passport_plan"
AIRTABLE_HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}


def clean_value(value):
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    if isinstance(value, str):
        return " ".join(value.replace("\n", " ").replace("\r", " ").split())
    return value


def to_num(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return value

    text = str(value).strip()

    if text == "" or text.lower() in {"nan", "none", "<na>"}:
        return None

    text = text.replace("₽", "")
    text = text.replace("\xa0", "")
    text = text.replace(" ", "")

    allowed = ""
    for ch in text:
        if ch.isdigit() or ch in ",.-":
            allowed += ch

    if allowed == "":
        return None

    if "," in allowed:
        allowed = allowed.replace(".", "")
        allowed = allowed.replace(",", ".")

    try:
        return float(allowed)
    except ValueError:
        return None


def to_date(value):
    if not value:
        return None
    return str(value)[:10]


def map_fields(record):
    fields = record.get("fields", {})
    now_iso = datetime.now(timezone.utc).isoformat()

    project_value = clean_value(fields.get("Project"))

    return {
        "airtable_record_id": record.get("id"),
        "passport_record_id": clean_value(fields.get("Passport_Record_ID")),
        "project": project_value,
        "project_code": project_value,
        "year_quarter_month_week_id": clean_value(
            fields.get("Year_Quarter_Month_Week_ID")
        ),
        "month_key": clean_value(fields.get("Month_Key")),
        "week_key": clean_value(fields.get("Week_ISO")),
        "boq_code": clean_value(fields.get("BOQ")),
        "boq_name": clean_value(fields.get("BOQ_Name")),
        "iwp_id_export": clean_value(fields.get("IWP_ID_EXPORT")),
        "system_label": clean_value(fields.get("System_Label")),
        "unit_of_measure": clean_value(fields.get("Unit of Measure")),
        "unit_price": to_num(fields.get("Unit_Price")),
        "plan_qty_month": to_num(fields.get("Plan_Qty_Month")),
        "plan_pv_workvalue_auto": to_num(fields.get("Plan_PV_WorkValue_auto")),
        "plan_work_start_date": to_date(fields.get("Plan_Work_Start_Date")),
        "plan_work_finish_date": to_date(fields.get("Plan_Work_Finish_Date")),
        "facility_building": clean_value(fields.get("Facility_Building.")),
        "crew": clean_value(fields.get("crew")),
        "construction_discipline": clean_value(fields.get("Construction_Discipline.")),
        "budget_status": clean_value(fields.get("Budget_Status")),
        "last_synced_at": now_iso,
    }


def fetch_airtable_records():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    all_rows = []

    while True:
        resp = requests.get(url, headers=AIRTABLE_HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for rec in data.get("records", []):
            all_rows.append(map_fields(rec))

        offset = data.get("offset")
        if not offset:
            break

        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}?offset={offset}"
        time.sleep(0.2)

    return all_rows


def upsert_to_supabase(rows):
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?on_conflict=airtable_record_id"

    batch_size = 20
    total = len(rows)

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]

        resp = requests.post(url, headers=SUPABASE_HEADERS, json=batch)

        if resp.status_code >= 300:
            print("❌ Ошибка:")
            print(resp.text)
            return

        print(f"Upsert: {min(i + batch_size, total)} / {total}")
        time.sleep(0.2)


def main():
    print("📥 Читаю Airtable Monthly Passport...")

    rows = fetch_airtable_records()

    print(f"📊 Получено строк из Airtable: {len(rows)}")

    print("🚀 Загружаю в Supabase...")
    upsert_to_supabase(rows)

    print("✅ Готово.")


if __name__ == "__main__":
    main()
