import os
import requests
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

SUPABASE_TABLE = "daily_progress_raw"

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
        cleaned_items = []
        for item in value:
            if isinstance(item, dict):
                cleaned_items.append(str(item))
            else:
                cleaned_items.append(str(item))
        return ", ".join(cleaned_items)
    if isinstance(value, str):
        return " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return value


def to_num(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if cleaned == "":
        return None

    cleaned = cleaned.replace("₽", "")
    cleaned = cleaned.replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    cleaned = "".join(ch for ch in cleaned if ch.isdigit() or ch in ".-")

    if cleaned == "":
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def map_fields(record):
    fields = record.get("fields", {})
    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "airtable_record_id": record.get("id"),
        "project_code": clean_value(fields.get("Project")),
        "month_key": clean_value(fields.get("Month_Key")),
        "created_time": clean_value(fields.get("Created_Time")),
        "facility_building": clean_value(fields.get("Facility_Building")),
        "construction_discipline": clean_value(fields.get("Construction_Discipline")),
        "shift_type": clean_value(fields.get("Shift_Type")),
        "boq": clean_value(fields.get("BOQ")),
        "boq_name": clean_value(fields.get("BOQ_Name")),
        "foreman": clean_value(fields.get("Foreman")),
        "crew_id": clean_value(fields.get("Crew_ID")),
        "unit_of_measure": clean_value(fields.get("Unit_of_Measure")),
        "project_qty": to_num(clean_value(fields.get("Project_Qty"))),
        "quantity_today": to_num(clean_value(fields.get("Quantity_Today"))),
        "crew_size": to_num(clean_value(fields.get("Crew_Size"))),
        "idle_reason": clean_value(fields.get("Idle_Reason")),
        "idle_reason_normalized": clean_value(fields.get("Idle_Reason_Normalized")),
        "direct_work_hours": to_num(clean_value(fields.get("Direct_Work_Hours"))),
        "iwp_id": clean_value(fields.get("IWP_ID_EXPORT")),
        "idle_hours": to_num(clean_value(fields.get("Idle_Hours"))),
        "productive_work_hours": to_num(
            clean_value(fields.get("Productive_Work_Hours"))
        ),
        "ev_day_value": to_num(clean_value(fields.get("EV_DAY_VALUE"))),
        "ac_day_value": to_num(clean_value(fields.get("AC_DAY_VALUE"))),
        "cv_evm": to_num(clean_value(fields.get("CV_EVM"))),
        "cv_cashout": to_num(clean_value(fields.get("CV_CashOut"))),
        "idle_loss_value": to_num(clean_value(fields.get("Idle_Loss_Value"))),
        "direct_rate_rub_per_hour": to_num(
            clean_value(fields.get("Direct_Rate_Rub_per_Hour"))
        ),
        "comment_foreman": clean_value(fields.get("Comment_Foreman")),
        "operation_type": clean_value(fields.get("Operation_Type")),
        "operation_quantity": to_num(clean_value(fields.get("Operation_Quantity"))),
        "operation_main_parameter": clean_value(fields.get("Operation_Main_Parameter")),
        "operation_location": clean_value(fields.get("Operation_Location")),
        "operation_comment": clean_value(fields.get("Operation_Comment")),
        "system_label": clean_value(fields.get("System_Label")),
        "is_deleted": False,
        "last_synced_at": now_iso,
    }


def fetch_airtable_records():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    all_rows = []

    while True:
        resp = requests.get(url, headers=AIRTABLE_HEADERS, timeout=60)
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
    if not rows:
        print("Нет строк для загрузки.")
        return

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?on_conflict=airtable_record_id"
    batch_size = 20
    total = len(rows)

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        resp = requests.post(url, headers=SUPABASE_HEADERS, json=batch, timeout=60)

        if resp.status_code >= 300:
            print("Ошибка upsert батча:")
            print("status:", resp.status_code)
            print("response:", resp.text)
            return

        print(f"Upsert: {min(i + batch_size, total)} из {total}")
        time.sleep(0.4)


def fetch_existing_ids_from_supabase():
    ids = set()
    offset = 0
    limit = 1000

    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
            f"?select=airtable_record_id&limit={limit}&offset={offset}"
        )
        resp = requests.get(url, headers=SUPABASE_HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            break

        for row in data:
            rid = row.get("airtable_record_id")
            if rid:
                ids.add(rid)

        if len(data) < limit:
            break

        offset += limit

    return ids


def mark_deleted_records(current_airtable_ids):
    existing_ids = fetch_existing_ids_from_supabase()
    to_soft_delete = list(existing_ids - current_airtable_ids)

    if not to_soft_delete:
        print("Удалённых записей для soft delete нет.")
        return

    print(f"Найдено к soft delete: {len(to_soft_delete)}")

    batch_size = 50
    now_iso = datetime.now(timezone.utc).isoformat()

    for i in range(0, len(to_soft_delete), batch_size):
        chunk = to_soft_delete[i : i + batch_size]

        for rid in chunk:
            url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?airtable_record_id=eq.{rid}"
            payload = {"is_deleted": True, "last_synced_at": now_iso}

            resp = requests.patch(
                url, headers=SUPABASE_HEADERS, json=payload, timeout=60
            )

            if resp.status_code >= 300:
                print("Ошибка soft delete:")
                print("record:", rid)
                print("status:", resp.status_code)
                print("response:", resp.text)
                return

        print(
            f"Soft delete: {min(i + batch_size, len(to_soft_delete))} из {len(to_soft_delete)}"
        )
        time.sleep(0.3)


def main():
    print("Читаю Airtable...")
    rows = fetch_airtable_records()
    print(f"Получено строк из Airtable: {len(rows)}")

    print("Делаю upsert в Supabase...")
    upsert_to_supabase(rows)

    current_ids = {
        row["airtable_record_id"] for row in rows if row.get("airtable_record_id")
    }

    print("Проверяю soft delete...")
    mark_deleted_records(current_ids)

    print("Готово.")


if __name__ == "__main__":
    main()
