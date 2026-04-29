import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

# ===== 1. ДАННЫЕ ИЗ .env =====
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SUPABASE_TABLE = "boq_master_api"

AIRTABLE_HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def clean_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        return " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return value


def map_fields(fields):
    return {
        "name": clean_value(fields.get("Name")),
        "boq_code": clean_value(fields.get("BoQ_Code")),
        "description": clean_value(fields.get("Description")),
        "facility_building": clean_value(fields.get("Facility_Building")),
        "construction_discipline": clean_value(fields.get("Construction_Discipline")),
        "unit_of_measure": clean_value(fields.get("Unit of Measure")),
        "project_qty": clean_value(fields.get("Project_Qty")),
        "unit_price": clean_value(fields.get("Unit_Price")),
        "total_value": clean_value(fields.get("Total Value")),
    }


def fetch_airtable_records():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    all_rows = []

    while True:
        resp = requests.get(url, headers=AIRTABLE_HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        for rec in data.get("records", []):
            all_rows.append(map_fields(rec.get("fields", {})))

        offset = data.get("offset")
        if not offset:
            break

        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}?offset={offset}"
        time.sleep(0.2)

    return all_rows


def insert_to_supabase(rows):
    if not rows:
        print("Нет строк для загрузки.")
        return

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
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
            print("Ошибка загрузки батча:")
            print("status:", resp.status_code)
            print("response:", resp.text)
            return

        print(f"Загружено {min(i + batch_size, total)} из {total}")
        time.sleep(0.5)


def main():
    print("Читаю Airtable...")
    rows = fetch_airtable_records()
    print(f"Получено строк из Airtable: {len(rows)}")

    print("Пишу в Supabase...")
    insert_to_supabase(rows)
    print("Готово.")


if __name__ == "__main__":
    main()