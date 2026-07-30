import json, pathlib
from services.supabase_client import supabase

audit=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_audit.json').read_text(encoding='utf-8'))
rows=audit['report']
B=[r for r in rows if r['group']=='B']
D=[r for r in rows if r['group']=='D']
line_ids=[r['line_id'] for r in B]

all_lines=[]
off=0
while True:
    r=supabase.table('monthly_plan_draft_lines').select('*').eq('draft_id', audit['draft_id']).range(off, off+999).execute()
    b=r.data or []
    all_lines.extend(b)
    if len(b)<1000: break
    off+=1000
by_id={r['line_id']: r for r in all_lines}

out={'group_b':[], 'group_d_plan_rows':{}}
for r in B:
    src=by_id[r['line_id']]
    out['group_b'].append({
        'legacy_index': r['legacy_index'],
        'line_id': r['line_id'],
        'draft_id': src.get('draft_id'),
        'project': src.get('project_code'),
        'month': src.get('month_key'),
        'facility': src.get('facility_building'),
        'discipline': src.get('construction_discipline'),
        'system': src.get('system'),
        'iwp': src.get('iwp'),
        'boq_code': src.get('boq_code'),
        'boq_name': src.get('boq_name'),
        'quantity': src.get('planned_qty'),
        'unit': src.get('unit_of_measure'),
        'crew': src.get('crew_id'),
        'unit_price': src.get('unit_price'),
        'plan_value': src.get('plan_value'),
        'norm_scenario': src.get('norm_scenario'),
        'hours_per_unit': src.get('selected_hours_per_unit'),
        'required_hours': src.get('required_hours'),
        'labor_rate_per_hour': src.get('labor_rate_per_hour'),
        'labor_cost': src.get('labor_cost'),
        'line_status': src.get('line_status'),
        'comment': src.get('comment'),
        'plan_line_id': src.get('plan_line_id'),
        'client_line_uid': src.get('client_line_uid'),
        'line_origin': src.get('line_origin'),
        'parent_plan_line_id': src.get('parent_plan_line_id'),
    })

for r in D:
    details=[]
    for pid in r['matching_plan_line_ids']:
        rr=supabase.table('monthly_plan_lines_v2').select('*').eq('plan_line_id', pid).limit(1).execute().data or []
        if rr:
            p=rr[0]
            details.append({
                'plan_line_id': p.get('plan_line_id'),
                'status': p.get('status'),
                'project': p.get('project_code'),
                'month': p.get('month_key'),
                'facility': p.get('facility'),
                'discipline': p.get('discipline'),
                'system': p.get('system'),
                'iwp': p.get('iwp'),
                'boq_code': p.get('boq_code'),
                'boq_name': p.get('boq_name'),
                'quantity': p.get('planned_qty'),
                'crew': p.get('crew'),
                'plan_value': p.get('plan_value'),
                'labor_hours': p.get('labor_hours'),
                'labor_cost': p.get('labor_cost'),
                'created_at': p.get('created_at'),
                'updated_at': p.get('updated_at'),
                'sent_to_constraints_at': p.get('sent_to_constraints_at'),
            })
    out['group_d_plan_rows'][str(r['legacy_index'])] = {
        'legacy_row': r,
        'plan_rows': details,
    }

pathlib.Path(r'c:\csv_fix\_tmp_legacy_phase2.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(json.dumps({'group_b':len(out['group_b']), 'group_d':len(out['group_d_plan_rows'])}, ensure_ascii=False))
