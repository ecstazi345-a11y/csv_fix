from services.supabase_client import supabase
import json
from collections import Counter

draft_id='661d5ffe-5851-4a27-8b4b-e01d16929798'

def fetch_all(table, select='*', **eqs):
    rows=[]; off=0
    while True:
        q=supabase.table(table).select(select)
        for k,v in eqs.items():
            q=q.eq(k,v)
        r=q.range(off, off+999).execute()
        b=r.data or []
        rows.extend(b)
        if len(b)<1000:
            break
        off+=1000
    return rows

lines=fetch_all('monthly_plan_draft_lines', draft_id=draft_id)
if not lines:
    raise SystemExit('No draft lines')
project=lines[0].get('project_code')
month=lines[0].get('month_key')
plans=fetch_all('monthly_plan_lines_v2', project_code=project, month_key=month)


def norm_text(v):
    if v is None:
        return ''
    s=str(v).strip()
    if not s or s.casefold() in {'nan','<na>','none'}:
        return ''
    return s.upper()

def norm_qty(v):
    try:
        return round(float(v or 0), 6)
    except Exception:
        return None

def scope_key_line(r):
    return (
        norm_text(r.get('project_code')),
        norm_text(r.get('month_key')),
        norm_text(r.get('facility_building')),
        norm_text(r.get('construction_discipline')),
        norm_text(r.get('system')),
        norm_text(r.get('iwp')),
        norm_text(r.get('crew_id')),
        norm_text(r.get('boq_code')),
    )

def scope_key_plan(r):
    return (
        norm_text(r.get('project_code')),
        norm_text(r.get('month_key')),
        norm_text(r.get('facility')),
        norm_text(r.get('discipline')),
        norm_text(r.get('system')),
        norm_text(r.get('iwp')),
        norm_text(r.get('crew')),
        norm_text(r.get('boq_code')),
    )

def exact_key_line(r):
    return scope_key_line(r) + (norm_qty(r.get('planned_qty')),)

def exact_key_plan(r):
    return scope_key_plan(r) + (norm_qty(r.get('planned_qty')),)

plan_by_scope={}
plan_by_exact={}
for p in plans:
    plan_by_scope.setdefault(scope_key_plan(p), []).append(p)
    plan_by_exact.setdefault(exact_key_plan(p), []).append(p)

report=[]
counts=Counter()
for idx, line in enumerate(lines, start=1):
    required_missing=[]
    if not norm_text(line.get('project_code')):
        required_missing.append('project')
    if not norm_text(line.get('month_key')):
        required_missing.append('month')
    if not norm_text(line.get('boq_code')):
        required_missing.append('boq_code')
    sk=scope_key_line(line)
    ek=exact_key_line(line)
    scope_matches=plan_by_scope.get(sk, [])
    exact_matches=plan_by_exact.get(ek, [])
    if required_missing:
        group='C'
        outcome='restore создаст pending-строку с повреждёнными ключами; безопасно не восстанавливать'
    elif len(exact_matches)==1:
        group='A'
        outcome='восстановление создаст pending-копию уже сохранённой строки; последующий Save создаст дубль'
    elif len(exact_matches)>1:
        group='D'
        outcome='строка уже присутствует в плане более чем в одном экземпляре; parent/источник неоднозначен'
    elif len(scope_matches)==0:
        group='B'
        outcome='в плане такой строки нет; восстановление допустимо как единственная версия'
    else:
        group='D'
        outcome='найдены частичные совпадения по scope, но без однозначного exact-match; восстановление рискованно'
    counts[group]+=1
    report.append({
        'legacy_index': idx,
        'draft_id': line.get('draft_id'),
        'line_id': line.get('line_id'),
        'plan_line_id': line.get('plan_line_id'),
        'client_line_uid': line.get('client_line_uid'),
        'line_origin': line.get('line_origin'),
        'parent_plan_line_id': line.get('parent_plan_line_id'),
        'status': line.get('line_status'),
        'month': line.get('month_key'),
        'project': line.get('project_code'),
        'boq_code': line.get('boq_code'),
        'system': line.get('system'),
        'iwp': line.get('iwp'),
        'crew': line.get('crew_id'),
        'quantity': line.get('planned_qty'),
        'facility': line.get('facility_building'),
        'discipline': line.get('construction_discipline'),
        'group': group,
        'exact_match_count': len(exact_matches),
        'scope_match_count': len(scope_matches),
        'matching_plan_line_ids': [p.get('plan_line_id') for p in (exact_matches or scope_matches)[:5]],
        'outcome': outcome,
    })

summary={
    'draft_id': draft_id,
    'project': project,
    'month': month,
    'legacy_total': len(lines),
    'plan_rows_same_scope_total': len(plans),
    'group_counts': counts,
    'report': report,
}
open(r'c:\csv_fix\_tmp_legacy_audit.json','w',encoding='utf-8').write(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
print(json.dumps({'legacy_total': len(lines), 'plan_rows': len(plans), 'group_counts': counts}, ensure_ascii=False, default=str))
