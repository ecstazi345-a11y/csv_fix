import json, hashlib, pathlib
from collections import defaultdict
from services.supabase_client import supabase

rows=[]
off=0
while True:
    r=supabase.table('monthly_plan_lines_v2').select(
        'plan_line_id,project_code,month_key,facility,discipline,crew,boq_code,planned_qty,plan_value,labor_hours,unit_price,system,iwp,created_at,status'
    ).range(off, off+999).execute()
    b=r.data or []
    rows.extend(b)
    if len(b)<1000: break
    off+=1000

def n(v):
    return '' if v is None else str(v)

def group_key(r):
    parts=[
        n(r.get('project_code')), n(r.get('month_key')), n(r.get('facility')),
        n(r.get('discipline')), n(r.get('crew')), n(r.get('boq_code')),
        n(r.get('planned_qty')), n(r.get('plan_value')), n(r.get('labor_hours')),
        n(r.get('unit_price')), n(r.get('system')), n(r.get('iwp')),
    ]
    raw='||'.join(parts)
    return hashlib.md5(raw.encode('utf-8')).hexdigest(), raw

groups=defaultdict(list)
for r in rows:
    gid,_=group_key(r)
    groups[gid].append(r)

candidates=[]
for gid, items in groups.items():
    if len(items)<2: continue
    items_sorted=sorted(items, key=lambda x: (str(x.get('created_at') or '9999'), str(x.get('plan_line_id') or '')))
    keep=items_sorted[0]
    for d in items_sorted[1:]:
        candidates.append({
            'GROUP_ID': gid,
            'KEEP_PLAN_LINE_ID': keep['plan_line_id'],
            'DELETE_PLAN_LINE_ID': d['plan_line_id'],
            'BOQ_CODE': d.get('boq_code'),
            'FACILITY': d.get('facility'),
            'CREW': d.get('crew'),
            'QTY': d.get('planned_qty'),
            'VALUE': d.get('plan_value'),
            'HOURS': d.get('labor_hours'),
            'CREATED_AT': d.get('created_at'),
            'DELETE_REASON': f"technical duplicate of {keep['plan_line_id']} (same project/month/facility/discipline/crew/boq/qty/value/hours/unit_price/system/iwp); keep earliest created_at",
            'project_code': d.get('project_code'),
            'month_key': d.get('month_key'),
            'KEEP_CREATED_AT': keep.get('created_at'),
            'group_size': len(items),
        })

candidates.sort(key=lambda x: (str(x['BOQ_CODE'] or ''), str(x['FACILITY'] or ''), str(x['CREW'] or ''), str(x['CREATED_AT'] or ''), str(x['DELETE_PLAN_LINE_ID'] or '')))

delete_ids={c['DELETE_PLAN_LINE_ID'] for c in candidates}
rows_before=len(rows)
rows_to_delete=len(delete_ids)
rows_remaining=rows_before-rows_to_delete

def fnum(v):
    try: return float(v or 0)
    except: return 0.0

value_before=sum(fnum(r.get('plan_value')) for r in rows)
hours_before=sum(fnum(r.get('labor_hours')) for r in rows)
value_removed=sum(fnum(c['VALUE']) for c in candidates)
hours_removed=sum(fnum(c['HOURS']) for c in candidates)

# scope focus PRJ_001 / july for clarity
scope_cands=[c for c in candidates if c.get('project_code')=='PRJ_001_БХК' and c.get('month_key')=='июль-2026']
scope_rows=[r for r in rows if r.get('project_code')=='PRJ_001_БХК' and r.get('month_key')=='июль-2026']
scope_del={c['DELETE_PLAN_LINE_ID'] for c in scope_cands}
scope_value_before=sum(fnum(r.get('plan_value')) for r in scope_rows)
scope_hours_before=sum(fnum(r.get('labor_hours')) for r in scope_rows)
scope_value_removed=sum(fnum(c['VALUE']) for c in scope_cands)
scope_hours_removed=sum(fnum(c['HOURS']) for c in scope_cands)

out={
  'sql_file': 'sql/monthly_plan_lines_v2_technical_duplicates_audit.sql',
  'global': {
    'rows_before': rows_before,
    'rows_to_delete': rows_to_delete,
    'rows_remaining': rows_remaining,
    'plan_value_before': value_before,
    'plan_value_removed': value_removed,
    'plan_value_after': value_before-value_removed,
    'labor_hours_before': hours_before,
    'labor_hours_removed': hours_removed,
    'labor_hours_after': hours_before-hours_removed,
    'twin_groups': len({c['GROUP_ID'] for c in candidates}),
  },
  'prj_july': {
    'rows_before': len(scope_rows),
    'rows_to_delete': len(scope_del),
    'rows_remaining': len(scope_rows)-len(scope_del),
    'plan_value_before': scope_value_before,
    'plan_value_removed': scope_value_removed,
    'plan_value_after': scope_value_before-scope_value_removed,
    'labor_hours_before': scope_hours_before,
    'labor_hours_removed': scope_hours_removed,
    'labor_hours_after': scope_hours_before-scope_hours_removed,
    'twin_groups': len({c['GROUP_ID'] for c in scope_cands}),
  },
  'candidates': candidates,
}
pathlib.Path(r'c:\csv_fix\_tmp_tech_dup_audit.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(json.dumps({'global': out['global'], 'prj_july': out['prj_july'], 'candidate_count': len(candidates)}, ensure_ascii=False, indent=2))
print('---CANDIDATES---')
for i,c in enumerate(candidates,1):
    print(f"{i:02d}\t{c['BOQ_CODE']}\t{c['FACILITY']}\t{c['CREW']}\tqty={c['QTY']}\thrs={c['HOURS']}\tKEEP={c['KEEP_PLAN_LINE_ID'][:8]}\tDEL={c['DELETE_PLAN_LINE_ID'][:8]}\tcreated={c['CREATED_AT']}")
