import requests
import time
from datetime import datetime, timezone

# ===== 1. ВСТАВЬ СВОИ ДАННЫЕ =====
AIRTABLE_TOKEN = "patv4p3Z6I60zw6fk.e4eaa7afd024c58d3d894446e8ccd99324223fdd55dc5baeb0f5c1a7dd88278d"
AIRTABLE_BASE_ID = "app9iyPkp63WZ0lPn"
AIRTABLE_TABLE_ID = "tblwiTtRRC8DVT9ki"

SUPABASE_URL = "https://fdaxiedifkikasudcygx.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_0Nzo8TLwFA6N9LeoTCobvQ_hOMZhamd"

SUPABASE_TABLE = "boq_master_api"

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
    if isinstance(value, str):
        return " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return value


def to_num(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return value
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

    project_qty = clean_value(fields.get("Project_Qty"))
    unit_price = clean_value(fields.get("Unit_Price"))
    total_value = clean_value(fields.get("Total Value"))

    return {
        "airtable_record_id": record.get("id"),
        "name": clean_value(fields.get("Name")),
        "boq_code": clean_value(fields.get("BoQ_Code")),
        "description": clean_value(fields.get("Description")),
        "facility_building": clean_value(fields.get("Facility_Building")),
        "construction_discipline": clean_value(fields.get("Construction_Discipline")),
        "unit_of_measure": clean_value(fields.get("Unit of Measure")),
        "project_name": clean_value(fields.get("Project_Name")) or "БХК",
        "project_qty": project_qty,
        "unit_price": unit_price,
        "total_value": total_value,
        "project_qty_num": to_num(project_qty),
        "unit_price_num": to_num(unit_price),
        "total_value_num": to_num(total_value),
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
        batch = rows[i:i + batch_size]
        resp = requests.post(
            url,
            headers=SUPABASE_HEADERS,
            json=batch,
            timeout=60
        )

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
        chunk = to_soft_delete[i:i + batch_size]

        for rid in chunk:
            url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?airtable_record_id=eq.{rid}"
            payload = {
                "is_deleted": True,
                "last_synced_at": now_iso
            }

            resp = requests.patch(url, headers=SUPABASE_HEADERS, json=payload, timeout=60)

            if resp.status_code >= 300:
                print("Ошибка soft delete:")
                print("record:", rid)
                print("status:", resp.status_code)
                print("response:", resp.text)
                return

        print(f"Soft delete: {min(i + batch_size, len(to_soft_delete))} из {len(to_soft_delete)}")
        time.sleep(0.3)


def main():
    print("Читаю Airtable...")
    rows = fetch_airtable_records()
    print(f"Получено строк из Airtable: {len(rows)}")

    print("Делаю upsert в Supabase...")
    upsert_to_supabase(rows)

    current_ids = {row["airtable_record_id"] for row in rows if row.get("airtable_record_id")}

    print("Проверяю soft delete...")
    mark_deleted_records(current_ids)

    print("Готово.")


if __name__ == "__main__":
    main()