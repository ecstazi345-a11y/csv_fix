import json, pathlib
from services.supabase_client import supabase

phase2=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_phase2.json').read_text(encoding='utf-8'))
b8=next(r for r in phase2['group_b'] if r['legacy_index']==8)
b9=next(r for r in phase2['group_b'] if r['legacy_index']==9)
ids=[b8['line_id'], b9['line_id']]

rows=[]
for lid in ids:
    r=supabase.table('monthly_plan_draft_lines').select('*').eq('line_id', lid).limit(1).execute()
    rows.extend(r.data or [])

if len(rows)!=2:
    print(json.dumps({'error':'expected 2 rows', 'got':len(rows)}, ensure_ascii=False))
else:
    a=next(r for r in rows if r['line_id']==b8['line_id'])
    b=next(r for r in rows if r['line_id']==b9['line_id'])
    keys=sorted(set(a)|set(b))
    diffs=[]
    same=[]
    for k in keys:
        va,vb=a.get(k),b.get(k)
        if va!=vb:
            diffs.append({'col':k,'b8':va,'b9':vb})
        else:
            same.append(k)
    cols=sorted(a.keys())
    out={
        'columns': cols,
        'b8_full': a,
        'b9_full': b,
        'diff_cols': diffs,
        'same_col_count': len(same),
        'same_cols': same,
        'same_draft_id': a.get('draft_id')==b.get('draft_id'),
        'draft_id': a.get('draft_id'),
    }
    pathlib.Path(r'c:\csv_fix\_tmp_b8b9_audit.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({
        'cols': cols,
        'diff_count': len(diffs),
        'diff_cols': [d['col'] for d in diffs],
        'diffs': diffs,
        'same_draft': out['same_draft_id'],
        'b8_line_id': b8['line_id'],
        'b9_line_id': b9['line_id'],
        'b8_created': a.get('created_at'),
        'b9_created': b.get('created_at'),
        'b8_updated': a.get('updated_at'),
        'b9_updated': b.get('updated_at'),
        'has_sort': any(c in cols for c in ['sort_order','line_order','position','ord']),
    }, ensure_ascii=False, indent=2, default=str))
