import json, uuid, pathlib
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
from supabase import create_client

load_dotenv(r'c:\csv_fix\.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_KEY')
client = create_client(url, key)

PROJECT = 'PRJ_001_БХК'
MONTH = 'июль-2026'

# baseline
before = client.table('monthly_plan_lines_v2').select('plan_line_id', count='exact').eq('project_code', PROJECT).eq('month_key', MONTH).execute()
rows_before = before.count
print('rows_before', rows_before)
assert rows_before == 95, f'baseline expected 95, got {rows_before}'

uid = str(uuid.uuid4())
now = datetime.now(timezone.utc).isoformat()

# synthetic NEW INITIAL line — unique enough BOQ marker for test
# use a real-ish facility/discipline/crew from cleaned data
payload1 = {
    'project_code': PROJECT,
    'month_key': MONTH,
    'facility': '16160-13',
    'discipline': 'Автоматизация',
    'system': None,
    'iwp': None,
    'boq_code': 'TEST-UID-HARDEN-001',
    'boq_name': 'Idempotency controlled test line',
    'unit': 'шт. / pcs',
    'planned_qty': 1.0,
    'crew': 'АСИ-19',
    'crew_size': 1,
    'labor_hours': 2.0,
    'labor_cost': 6000.0,
    'unit_price': 100.0,
    'plan_value': 100.0,
    'status': 'NOT_SENT',
    'line_origin': 'INITIAL',
    'client_line_uid': uid,
    'planned_by': 'AUTO TEST',
    'planned_at': now,
}

# Save #1 — same path as patched save_v2_month_plan (upsert on client_line_uid)
resp1 = client.table('monthly_plan_lines_v2').upsert(payload1, on_conflict='client_line_uid').execute()
row1 = (resp1.data or [None])[0]
if not row1:
    # recovery select
    row1 = (client.table('monthly_plan_lines_v2').select('*').eq('client_line_uid', uid).limit(1).execute().data or [None])[0]
assert row1, 'Save #1 failed'
plan_id_1 = row1['plan_line_id']
print('save1_uid', uid)
print('save1_plan_line_id', plan_id_1)
print('save1_qty', row1.get('planned_qty'))

c1 = client.table('monthly_plan_lines_v2').select('plan_line_id', count='exact').eq('client_line_uid', uid).execute()
print('rows_for_uid_after_save1', c1.count)
mid = client.table('monthly_plan_lines_v2').select('plan_line_id', count='exact').eq('project_code', PROJECT).eq('month_key', MONTH).execute()
print('rows_after_save1', mid.count)

# Save #2 — same uid, changed qty/hours/value
payload2 = dict(payload1)
payload2['planned_qty'] = 3.0
payload2['labor_hours'] = 6.0
payload2['labor_cost'] = 18000.0
payload2['plan_value'] = 300.0
payload2['unit_price'] = 100.0

resp2 = client.table('monthly_plan_lines_v2').upsert(payload2, on_conflict='client_line_uid').execute()
row2 = (resp2.data or [None])[0]
if not row2:
    row2 = (client.table('monthly_plan_lines_v2').select('*').eq('client_line_uid', uid).limit(1).execute().data or [None])[0]
assert row2, 'Save #2 failed'
plan_id_2 = row2['plan_line_id']
print('save2_plan_line_id', plan_id_2)
print('save2_qty', row2.get('planned_qty'))
print('save2_hours', row2.get('labor_hours'))
print('save2_value', row2.get('plan_value'))

c2 = client.table('monthly_plan_lines_v2').select('plan_line_id', count='exact').eq('client_line_uid', uid).execute()
print('rows_for_uid', c2.count)
detail = client.table('monthly_plan_lines_v2').select('plan_line_id,planned_qty,labor_hours,plan_value,client_line_uid,status,updated_at').eq('client_line_uid', uid).execute().data
print('detail', json.dumps(detail, ensure_ascii=False, default=str))
after = client.table('monthly_plan_lines_v2').select('plan_line_id', count='exact').eq('project_code', PROJECT).eq('month_key', MONTH).execute()
print('rows_after', after.count)

checks = {
    'rows_for_uid_eq_1': c2.count == 1,
    'plan_line_id_stable': plan_id_1 == plan_id_2,
    'qty_updated': float(row2.get('planned_qty') or 0) == 3.0,
    'hours_updated': float(row2.get('labor_hours') or 0) == 6.0,
    'value_updated': float(row2.get('plan_value') or 0) == 300.0,
    'rows_after_eq_96': after.count == 96,
    'save2_did_not_increase_extra': after.count == rows_before + 1,
}
print('checks', json.dumps(checks, ensure_ascii=False))
passed = all(checks.values())
print('TEST_RESULT', 'PASS' if passed else 'FAIL')
out = {
    'uid': uid,
    'plan_line_id_1': plan_id_1,
    'plan_line_id_2': plan_id_2,
    'rows_before': rows_before,
    'rows_after': after.count,
    'rows_for_uid': c2.count,
    'detail': detail,
    'checks': checks,
    'result': 'PASS' if passed else 'FAIL',
    'method': 'controlled upsert path identical to patched save_v2_month_plan (on_conflict=client_line_uid); Streamlit restarted on :8501',
}
pathlib.Path(r'c:\csv_fix\_tmp_idempotency_test_result.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
