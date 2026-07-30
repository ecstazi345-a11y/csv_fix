import json, pathlib, uuid, datetime
from services.supabase_client import supabase

audit=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_audit.json').read_text(encoding='utf-8'))
phase2=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_b8b9_audit.json').read_text(encoding='utf-8'))

# Keeper rule: same created_at -> min line_id
b8_id='a72017cc-e9fd-4aad-ab1a-75c349d47f85'
b9_id='16486e86-d338-401c-9daf-ee7d7d17f933'
keeper_id=min([b8_id,b9_id])
skip_id=b8_id if keeper_id==b9_id else b9_id
keeper_label='B9' if keeper_id==b9_id else 'B8'
skip_label='B8' if skip_id==b8_id else 'B9'

group_b=[r for r in audit['report'] if r['group']=='B']
group_a=[r for r in audit['report'] if r['group']=='A']
group_d=[r for r in audit['report'] if r['group']=='D']

migrate=[r for r in group_b if r['line_id']!=skip_id]
skip=[r for r in group_b if r['line_id']==skip_id]

# fetch full rows for migrate+skip
all_ids=[r['line_id'] for r in migrate]+[skip_id]
full_by_id={}
for lid in all_ids:
    rr=supabase.table('monthly_plan_draft_lines').select('*').eq('line_id', lid).limit(1).execute().data or []
    if rr: full_by_id[lid]=rr[0]

# refs: search draft lines where plan_line_id/parent equals these? unlikely for draft line_ids
# also check if line_id appears as FK elsewhere - try common tables
ref_report={}
candidate_tables=[
    ('monthly_plan_draft_lines','line_id'),
    ('monthly_plan_drafts','draft_id'),
]
# For each line_id, count self and check parent_plan_line_id / plan_line_id pointing to them (won't for draft PKs)
for lid in [b8_id,b9_id]+[r['line_id'] for r in migrate[:1]]:
    ref_report[lid]={}
    # only one row with this line_id
    c=supabase.table('monthly_plan_draft_lines').select('line_id', count='exact').eq('line_id', lid).execute()
    ref_report[lid]['draft_lines_self_count']=c.count if hasattr(c,'count') else len(c.data or [])

# plan count before
plan_cnt=supabase.table('monthly_plan_lines_v2').select('plan_line_id', count='exact').eq('project_code','PRJ_001_БХК').eq('month_key','июль-2026').execute()

# snapshots for A/D client_line_uid state
untouched_ids=[r['line_id'] for r in group_a+group_d]
untouched_snap=[]
for lid in untouched_ids:
    rr=supabase.table('monthly_plan_draft_lines').select('line_id,client_line_uid,line_origin,parent_plan_line_id,plan_line_id,line_status,boq_code,planned_qty,crew_id').eq('line_id', lid).limit(1).execute().data or []
    if rr: untouched_snap.append(rr[0])

batch_id=str(uuid.uuid4())
backup={
  'migration_batch_id': batch_id,
  'migration_reason': 'legacy_group_b_client_line_uid_backfill',
  'backed_up_at': datetime.datetime.utcnow().isoformat()+'Z',
  'draft_id': audit['draft_id'],
  'b8_b9': {
    'exact_duplicate': True,
    'diff_cols': ['line_id','planned_at'],
    'keeper_label': keeper_label,
    'keeper_line_id': keeper_id,
    'skip_label': skip_label,
    'skip_line_id': skip_id,
    'same_created_at': True,
    'selection_rule': 'created_at equal -> min(line_id)',
  },
  'MIGRATE_B': [{'legacy_index':r['legacy_index'],'line_id':r['line_id'],'row':full_by_id.get(r['line_id'])} for r in migrate],
  'SKIP_B': [{'legacy_index':r['legacy_index'],'line_id':r['line_id'],'row':full_by_id.get(r['line_id'])} for r in skip],
  'LEGACY_DRAFT_DUPLICATES': [{'legacy_index':r['legacy_index'],'line_id':r['line_id'],'pair_keeper':keeper_id,'reason':'exact_duplicate_of_B8_B9'} for r in skip],
  'UNTOUCHED': {
    'group_a': [{'legacy_index':r['legacy_index'],'line_id':r['line_id']} for r in group_a],
    'group_d': [{'legacy_index':r['legacy_index'],'line_id':r['line_id']} for r in group_d],
    'snapshot': untouched_snap,
  },
  'plan_rows_prj_month_before': plan_cnt.count if hasattr(plan_cnt,'count') else None,
  'ref_report': ref_report,
}

pathlib.Path(r'c:\csv_fix\_tmp_legacy_b_precheck.json').write_text(json.dumps(backup, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

print(json.dumps({
  'keeper': {'label':keeper_label,'line_id':keeper_id},
  'skip': {'label':skip_label,'line_id':skip_id},
  'migrate_count': len(migrate),
  'migrate': [{'idx':r['legacy_index'],'line_id':r['line_id']} for r in migrate],
  'skip_list': [{'idx':r['legacy_index'],'line_id':r['line_id']} for r in skip],
  'untouched_a': len(group_a),
  'untouched_d': [{'idx':r['legacy_index'],'line_id':r['line_id']} for r in group_d],
  'batch_id': batch_id,
  'plan_count_before': backup['plan_rows_prj_month_before'],
  'client_uids_null_in_migrate': all(full_by_id[r['line_id']].get('client_line_uid') is None for r in migrate),
  'refs_b8': ref_report.get(b8_id),
  'refs_b9': ref_report.get(b9_id),
}, ensure_ascii=False, indent=2))
