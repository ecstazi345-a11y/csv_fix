import json, pathlib
from datetime import datetime
data=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_b_business_audit.json').read_text(encoding='utf-8'))

def pdt(v):
    if not v: return None
    return datetime.fromisoformat(v.replace('Z','+00:00'))

for r in data['results']:
    print('====', r['label'], r['line_id'])
    print(' legacy planned_at', r['legacy']['planned_at'])
    print(' legacy created_at', r['legacy']['created_at'])
    print(' avail', r['legacy'].get('available_qty_before_add'), 'remaining', r['legacy'].get('planning_remaining_qty'), 'reserved', r['legacy'].get('already_reserved_qty'))
    lp=pdt(r['legacy']['planned_at'])
    for p in r['plans']:
        pc=pdt(p['created_at'])
        delta=None if not (lp and pc) else (lp-pc).total_seconds()
        print(f"  plan={p['plan_line_id']} fac={p['facility']} crew={p['crew']} qty={p['planned_qty']} hrs={p['labor_hours']} val={p['plan_value']} status={p['status']} created={p['created_at']} sent={p['sent_to_constraints_at']} delta_planned_minus_created_sec={delta}")
        print(f"    system={p['system']!r}")
        print(f"    iwp={p['iwp']!r}")
        print(f"    uid={p['client_line_uid']} origin={p['line_origin']} parent={p['parent_plan_line_id']}")
    print(' group_a_b11_context' if r['label']=='B11' else '', end='')
    print()

print('GROUP A same BOQ as B11:')
for a in data['group_a_same_boq_as_b11']:
    print(a)
