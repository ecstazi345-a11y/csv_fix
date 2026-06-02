import os
import requests
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

for key in [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]:
    os.environ.pop(key, None)

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE = "Crew_Register"
AIRTABLE_VIEW = "SUPABASE_MONTHLY_LABOR_SUMMARY"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

SUPABASE_TABLE = "monthly_labor_summary"

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


def make_requests_session():
    session = requests.Session()
    session.trust_env = False
    return session


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

    return {
        "airtable_record_id": record.get("id"),
        "assignment_period_id": clean_value(fields.get("Assignment_Period_ID")),
        "budget_status": clean_value(fields.get("Budget_Status")),
        "full_name_ru": clean_value(fields.get("Full_Name_RU")),
        "role": clean_value(fields.get("Role")),
        "crew_code": clean_value(fields.get("Crew_Code")),
        "support_function": clean_value(fields.get("Support_Function")),
        "planned_demobilization_date": to_date(
            fields.get("Planned_Demobilization_Date")
        ),
        "actual_demobilization_date": to_date(
            fields.get("Actual_Demobilization_Date")
        ),
        "actual_mobilization_date": to_date(
            fields.get("Actual_Mobilization_Date")
        ),
        "direct_hours_month": to_num(fields.get("Direct_Hours_Month")),
        "indirect_hours_month": to_num(fields.get("Indirect_Hours_Month")),
        "lab_hours_month": to_num(fields.get("LAB_Hours_Month")),
        "lab_fte_month": to_num(fields.get("LAB_FTE_Month")),
        "direct_cost_rub_month": to_num(fields.get("Direct_Cost_RUB_Month")),
        "indirect_cost_rub_month": to_num(fields.get("Indirect_Cost_RUB_Month")),
        "lab_cost_rub_month": to_num(fields.get("LAB_Cost_RUB_Month")),
        "discipline_code": clean_value(fields.get("Discipline_Code")),
        "month_key": clean_value(fields.get("Month_Key")),
        "project_code": clean_value(fields.get("Project_Code")),
        "last_synced_at": now_iso,
    }


def fetch_airtable_records():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"
    params = {
        "pageSize": 100,
        "view": AIRTABLE_VIEW,
    }
    all_rows = []
    session = make_requests_session()

    while True:
        resp = session.get(url, headers=AIRTABLE_HEADERS, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        for rec in data.get("records", []):
            row = map_fields(rec)
            if not row.get("airtable_record_id"):
                continue
            if not row.get("assignment_period_id"):
                continue
            all_rows.append(row)

        offset = data.get("offset")
        if not offset:
            break

        params = {
            "pageSize": 100,
            "view": AIRTABLE_VIEW,
            "offset": offset,
        }
        time.sleep(0.2)

    return all_rows


def deduplicate_rows(rows):
    """Оставить одну запись на airtable_record_id (последняя в snapshot)."""
    deduped = {}
    duplicate_keys = 0

    for row in rows:
        key = row.get("airtable_record_id")
        if not key:
            continue
        if key in deduped:
            duplicate_keys += 1
            prev_name = deduped[key].get("full_name_ru")
            new_name = row.get("full_name_ru")
            print(
                f"WARNING: duplicate airtable_record_id in snapshot: {key} "
                f"({prev_name!r} -> {new_name!r}); keeping last"
            )
        deduped[key] = row

    if duplicate_keys:
        print(f"WARNING: {duplicate_keys} duplicate airtable_record_id(s) in Airtable snapshot")

    return list(deduped.values())


def upsert_to_supabase(rows):
    if not rows:
        return 0

    url = (
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
        f"?on_conflict=airtable_record_id"
    )
    batch_size = 100
    total = len(rows)
    synced = 0
    session = make_requests_session()

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        resp = session.post(url, headers=SUPABASE_HEADERS, json=batch, timeout=60)

        if resp.status_code >= 300:
            print("Ошибка upsert батча:")
            print("status:", resp.status_code)
            print("response:", resp.text)
            return synced

        synced += len(batch)
        print(f"Upsert: {min(i + batch_size, total)} из {total}")
        time.sleep(0.2)

    return synced


def main():
    print(f"Читаю Airtable {AIRTABLE_TABLE} (view: {AIRTABLE_VIEW})...")
    rows = fetch_airtable_records()
    airtable_count = len(rows)
    rows = deduplicate_rows(rows)
    after_dedup = len(rows)
    removed = airtable_count - after_dedup

    print(f"Получено строк из Airtable: {airtable_count}")
    print(f"После дедупликации: {after_dedup}")
    print(f"Удалено дублей: {removed}")

    print("Делаю upsert в Supabase...")
    synced = upsert_to_supabase(rows)

    print(f"Синхронизировано записей: {synced}")
    print("Готово.")


if __name__ == "__main__":
    main()
