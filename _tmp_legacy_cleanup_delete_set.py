import json, pathlib
from services.supabase_client import supabase

audit=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_audit.json').read_text(encoding='utf-8'))
biz=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_b_business_audit.json').read_text(encoding='utf-8')) if pathlib.Path(r'c:\csv_fix\_tmp_legacy_b_business_audit.json').exists() else None

DRAFT='661d5ffe-5851-4a27-8b4b-e01d16929798'
KEEP='c90c5f21-e9e5-45c8-93e2-940dbc4fe862'

# label map from audit
rows=audit['report']
assert audit['draft_id']==DRAFT

biz_map={}
if biz:
  for r in biz['results']:
    biz_map[r['label']]={
      'plans':[{'plan_line_id':p['plan_line_id'],'qty':p['planned_qty'],'crew':p['crew'],'facility':p['facility'],'status':p['status']} for p in r['plans']],
      'classification':'see business audit',
    }

# D plan ids from phase2
phase2=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_phase2.json').read_text(encoding='utf-8'))
d_plans={}
for k,v in phase2.get('group_d_plan_rows',{}).items():
  d_plans[int(k)]=[p['plan_line_id'] for p in v['plan_rows']]

delete_set=[]
for r in rows:
  lid=r['line_id']
  if lid==KEEP:
    continue
  label=None
  reason=None
  related=[]
  g=r['group']
  idx=r['legacy_index']
  if g=='A':
    label=f'A{idx}'
    reason='Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail'
    related=r.get('matching_plan_line_ids') or []
  elif g=='D':
    label=f'D{idx}'
    reason='Group D: ambiguous multi-match plan duplicates; legacy tail, do not restore'
    related=r.get('matching_plan_line_ids') or d_plans.get(idx,[])
  elif g=='B':
    # map known B labels
    b_labels={1:'B1',5:'B5',6:'B6',7:'B7',8:'B8',9:'B9',10:'B10',11:'B11',33:'B33',34:'B34',35:'B35'}
    label=b_labels.get(idx,f'B{idx}')
    if label=='B35':
      raise SystemExit('B35 leaked into delete builder')
    if label in ('B8',):
      reason='Group B exact-duplicate draft twin of B9; technical legacy tail; related plan already SENT (same scope as B9)'
      # B8/B9 share plans
      related=biz_map.get('B9',{}).get('plans',[])
      related=[p['plan_line_id'] if isinstance(p,dict) else p for p in related]
    else:
      reason='Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail'
      plans=biz_map.get(label,{}).get('plans',[])
      # filter closest same facility/crew/qty when possible
      related=[p['plan_line_id'] for p in plans]
      # also from audit matching if any
      related = related or (r.get('matching_plan_line_ids') or [])
  else:
    raise SystemExit(f'unknown group {g}')

  delete_set.append({
    'label': label,
    'legacy_index': idx,
    'group': g,
    'line_id': lid,
    'boq': r.get('boq_code'),
    'qty': r.get('quantity'),
    'crew': r.get('crew'),
    'facility': r.get('facility'),
    'reason': reason,
    'related_plan_line_ids': related if related and isinstance(related[0], str) else [p if isinstance(p,str) else p.get('plan_line_id') for p in related],
  })

# live verify all exist + B35
live=supabase.table('monthly_plan_draft_lines').select('line_id,draft_id,client_line_uid,plan_line_id,line_status,boq_code,planned_qty,crew_id,facility_building,project_code,month_key').eq('draft_id', DRAFT).execute().data or []
live_ids={x['line_id'] for x in live}
print('live_count', len(live))
print('delete_set_count', len(delete_set))
print('keep_in_delete', KEEP in {d['line_id'] for d in delete_set})
print('keep_in_live', KEEP in live_ids)
missing=[d['line_id'] for d in delete_set if d['line_id'] not in live_ids]
extra_live=sorted(live_ids - {d['line_id'] for d in delete_set} - {KEEP})
print('missing_from_live', missing)
print('unexpected_extra_live_besides_keep', extra_live)

b35=[x for x in live if x['line_id']==KEEP]
print('B35', json.dumps(b35, ensure_ascii=False, default=str))

out={'draft_id':DRAFT,'keep_line_id':KEEP,'delete_set':delete_set,'live_count':len(live)}
pathlib.Path(r'c:\csv_fix\_tmp_legacy_cleanup_delete_set.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

# print table
for d in sorted(delete_set, key=lambda x: x['legacy_index']):
  rel=','.join((d['related_plan_line_ids'] or [])[:3])
  if len(d['related_plan_line_ids'] or [])>3: rel += f' (+{len(d["related_plan_line_ids"])-3})'
  print(f"{d['label']}\t{d['line_id']}\t{d['boq']}\tqty={d['qty']}\tcrew={d['crew']}\tplans={rel}\t{d['reason'][:80]}")
