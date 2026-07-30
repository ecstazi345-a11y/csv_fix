import json, pathlib
from datetime import datetime
from services.supabase_client import supabase

MIGRATE = [
  {"label":"B1","line_id":"4280dbdc-aebb-4256-a731-098065edf19c"},
  {"label":"B5","line_id":"49362e64-d137-4f95-b6eb-669ac68a45af"},
  {"label":"B6","line_id":"5677541c-1e70-4431-9093-0d374ed58bf0"},
  {"label":"B7","line_id":"f1bf6b49-e80a-4f84-9f55-614428106cd6"},
  {"label":"B9","line_id":"16486e86-d338-401c-9daf-ee7d7d17f933"},
  {"label":"B10","line_id":"c65de2cc-8fd7-466e-8494-c98c0c126a64"},
  {"label":"B11","line_id":"5136b0f9-d585-4e84-b849-56b6c3bbcb52"},
  {"label":"B33","line_id":"b148f69b-5375-4ccc-825c-5c0589b4300a"},
  {"label":"B34","line_id":"366ba576-2b4f-43c0-9708-d24bf458c5d7"},
  {"label":"B35","line_id":"c90c5f21-e9e5-45c8-93e2-940dbc4fe862"},
]

PROJECT="PRJ_001_БХК"
MONTH="июль-2026"

def parse_dt(v):
    if not v: return None
    try:
        return datetime.fromisoformat(str(v).replace('Z','+00:00'))
    except Exception:
        return None

def norm(v):
    if v is None: return ''
    s=str(v).strip()
    if s.lower() in ('none','nan','<na>'): return ''
    return s

def fnum(v):
    if v is None or v=='': return None
    try: return float(v)
    except Exception: return None

# load legacy rows
legacy={}
for item in MIGRATE:
    rr=supabase.table('monthly_plan_draft_lines').select('*').eq('line_id', item['line_id']).limit(1).execute().data or []
    if not rr:
        raise SystemExit(f"missing legacy {item}")
    legacy[item['label']]=rr[0]

# discover plan columns via one sample
sample=supabase.table('monthly_plan_lines_v2').select('*').eq('project_code',PROJECT).eq('month_key',MONTH).limit(1).execute().data or []
plan_cols=sorted(sample[0].keys()) if sample else []

# fetch all plan rows for relevant BOQs
boqs=sorted({legacy[l]['boq_code'] for l in legacy})
plan_by_boq={b:[] for b in boqs}
for boq in boqs:
    off=0
    while True:
        r=supabase.table('monthly_plan_lines_v2').select('*').eq('project_code',PROJECT).eq('month_key',MONTH).eq('boq_code',boq).range(off, off+999).execute()
        batch=r.data or []
        plan_by_boq[boq].extend(batch)
        if len(batch)<1000: break
        off+=1000

# also load Group A draft lines for B11 context (same draft)
audit=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_audit.json').read_text(encoding='utf-8'))
group_a=[r for r in audit['report'] if r['group']=='A' and r['boq_code']=='1500-05-09-01']

# helper field mapping for plan (facility/discipline/crew naming may differ)
def plan_facility(p):
    return p.get('facility') if 'facility' in p else p.get('facility_building')
def plan_discipline(p):
    return p.get('discipline') if 'discipline' in p else p.get('construction_discipline')
def plan_crew(p):
    return p.get('crew') if 'crew' in p else p.get('crew_id')
def plan_qty(p):
    return p.get('planned_qty') if p.get('planned_qty') is not None else p.get('quantity')
def plan_hours(p):
    return p.get('labor_hours') if p.get('labor_hours') is not None else p.get('required_hours')

def scope_key_legacy(d):
    return (
      norm(d.get('project_code')),
      norm(d.get('month_key')),
      norm(d.get('facility_building')),
      norm(d.get('construction_discipline')),
      norm(d.get('boq_code')),
      norm(d.get('crew_id')),
      '', # system not in draft schema
      '', # iwp not in draft schema
    )

def scope_key_plan(p):
    return (
      norm(p.get('project_code')),
      norm(p.get('month_key')),
      norm(plan_facility(p)),
      norm(plan_discipline(p)),
      norm(p.get('boq_code')),
      norm(plan_crew(p)),
      norm(p.get('system')),
      norm(p.get('iwp')),
    )

def boq_facility_key_legacy(d):
    return (
      norm(d.get('project_code')),
      norm(d.get('month_key')),
      norm(d.get('facility_building')),
      norm(d.get('construction_discipline')),
      norm(d.get('boq_code')),
    )

def boq_facility_key_plan(p):
    return (
      norm(p.get('project_code')),
      norm(p.get('month_key')),
      norm(plan_facility(p)),
      norm(plan_discipline(p)),
      norm(p.get('boq_code')),
    )

results=[]
for item in MIGRATE:
    lab=item['label']
    d=legacy[lab]
    plans=plan_by_boq.get(d['boq_code'], [])
    lsk=scope_key_legacy(d)
    lbk=boq_facility_key_legacy(d)
    lqty=fnum(d.get('planned_qty'))

    level1=[]; level2=[]; level3=[]; level4_notes=[]
    for p in plans:
        psk=scope_key_plan(p)
        pbk=boq_facility_key_plan(p)
        pqty=fnum(plan_qty(p))
        same_full_scope = (
            lsk[0]==psk[0] and lsk[1]==psk[1] and lsk[2]==psk[2] and lsk[3]==psk[3]
            and lsk[4]==psk[4] and lsk[5]==psk[5]
            # system/iwp both empty on legacy side always; treat plan empty as comparable
            and (psk[6]=='' or True) and (psk[7]=='' or True)
        )
        # Strict production scope: facility+discipline+boq+crew; system/iwp only if both sides have values
        prod_same = (lsk[0]==psk[0] and lsk[1]==psk[1] and lsk[2]==psk[2] and lsk[3]==psk[3]
                     and lsk[4]==psk[4] and lsk[5]==psk[5])
        # If plan has non-empty system/iwp while legacy has none -> still same production? Mark incomplete
        incomplete = (psk[6] != '' or psk[7] != '')  # legacy always empty system/iwp columns

        if prod_same and (pqty is not None and lqty is not None and abs(pqty-lqty)<1e-9):
            level1.append(p)
        elif prod_same:
            level2.append(p)
        elif lbk==pbk:
            # same facility+discipline+boq, different crew (or other)
            level3.append(p)
        else:
            # same BOQ project/month but different facility/discipline
            pass

        if incomplete and prod_same:
            level4_notes.append({'plan_line_id':p.get('plan_line_id'),'system':p.get('system'),'iwp':p.get('iwp'),'note':'plan has system/iwp while legacy draft has no such columns'})

    # also collect same BOQ different facility
    other_facility=[p for p in plans if boq_facility_key_plan(p)!=lbk]

    # closest plan: prefer L1, else L2, else L3 by qty proximity
    closest=None; closest_level=None
    if level1:
        closest=level1[0]; closest_level=1
    elif level2:
        closest=min(level2, key=lambda p: abs((fnum(plan_qty(p)) or 0)-(lqty or 0))); closest_level=2
    elif level3:
        closest=min(level3, key=lambda p: abs((fnum(plan_qty(p)) or 0)-(lqty or 0))); closest_level=3
    elif plans:
        closest=min(plans, key=lambda p: abs((fnum(plan_qty(p)) or 0)-(lqty or 0))); closest_level=0

    # chronology
    l_created=parse_dt(d.get('created_at'))
    l_planned=parse_dt(d.get('planned_at'))
    chron=[]
    for p in plans:
        pc=parse_dt(p.get('created_at')); pu=parse_dt(p.get('updated_at')); ps=parse_dt(p.get('sent_to_constraints_at'))
        ref=l_planned or l_created
        relation=None; delta=None
        if ref and pc:
            delta=(ref-pc).total_seconds()
            if abs(delta) < 3600:
                relation='C_near_simultaneous'
            elif delta < 0:
                relation='A_legacy_before_plan'  # legacy earlier
            else:
                relation='B_plan_before_legacy'
        chron.append({
            'plan_line_id': p.get('plan_line_id'),
            'plan_created': p.get('created_at'),
            'plan_updated': p.get('updated_at'),
            'sent_at': p.get('sent_to_constraints_at'),
            'legacy_planned_at': d.get('planned_at'),
            'legacy_created_at': d.get('created_at'),
            'delta_sec_planned_minus_plan_created': delta,
            'relation': relation,
            'crew': plan_crew(p),
            'qty': plan_qty(p),
            'facility': plan_facility(p),
            'discipline': plan_discipline(p),
            'status': p.get('status'),
            'system': p.get('system'),
            'iwp': p.get('iwp'),
            'plan_value': p.get('plan_value'),
            'labor_hours': plan_hours(p),
            'labor_cost': p.get('labor_cost'),
            'unit_price': p.get('unit_price'),
            'hours_per_unit': p.get('selected_hours_per_unit') or p.get('hours_per_unit'),
            'client_line_uid': p.get('client_line_uid'),
            'line_origin': p.get('line_origin'),
            'parent_plan_line_id': p.get('parent_plan_line_id'),
        })

    # norms comparison for closest
    norms=None
    if closest is not None:
        pq=fnum(plan_qty(closest)); ph=fnum(plan_hours(closest)); pvc=fnum(closest.get('plan_value')); plc=fnum(closest.get('labor_cost'))
        lup=fnum(d.get('unit_price')); pup=fnum(closest.get('unit_price'))
        lhu=fnum(d.get('selected_hours_per_unit')); phu=fnum(closest.get('selected_hours_per_unit') or closest.get('hours_per_unit'))
        llr=fnum(d.get('labor_rate_per_hour')); plr=fnum(closest.get('labor_rate_per_hour'))
        norms={
            'legacy': {
                'qty': lqty, 'value': fnum(d.get('plan_value')), 'hours': fnum(d.get('required_hours')),
                'labor_cost': fnum(d.get('labor_cost')), 'unit_price': lup, 'hours_per_unit': lhu, 'labor_rate': llr,
            },
            'plan': {
                'qty': pq, 'value': pvc, 'hours': ph, 'labor_cost': plc, 'unit_price': pup, 'hours_per_unit': phu, 'labor_rate': plr,
            },
            'same_unit_price': (lup is not None and pup is not None and abs(lup-pup)<0.01) if (lup is not None and pup is not None) else None,
            'same_hours_per_unit': (lhu is not None and phu is not None and abs(lhu-phu)<1e-6) if (lhu is not None and phu is not None) else None,
            'qty_diff': (None if pq is None or lqty is None else pq-lqty),
        }

    compact_plans=[]
    for p in plans:
        compact_plans.append({
            'plan_line_id': p.get('plan_line_id'),
            'client_line_uid': p.get('client_line_uid'),
            'line_origin': p.get('line_origin'),
            'parent_plan_line_id': p.get('parent_plan_line_id'),
            'status': p.get('status'),
            'project_code': p.get('project_code'),
            'month_key': p.get('month_key'),
            'facility': plan_facility(p),
            'discipline': plan_discipline(p),
            'boq_code': p.get('boq_code'),
            'boq_name': p.get('boq_name'),
            'planned_qty': plan_qty(p),
            'crew': plan_crew(p),
            'system': p.get('system'),
            'iwp': p.get('iwp'),
            'plan_value': p.get('plan_value'),
            'labor_hours': plan_hours(p),
            'labor_cost': p.get('labor_cost'),
            'unit_price': p.get('unit_price'),
            'hours_per_unit': p.get('selected_hours_per_unit') or p.get('hours_per_unit'),
            'labor_rate_per_hour': p.get('labor_rate_per_hour'),
            'created_at': p.get('created_at'),
            'updated_at': p.get('updated_at'),
            'sent_to_constraints_at': p.get('sent_to_constraints_at'),
            'created_by': p.get('created_by'),
            'planned_by': p.get('planned_by'),
            'source_draft_id': p.get('source_draft_id'),
            'source_line_id': p.get('source_line_id'),
            'all_keys': sorted(p.keys()),
        })

    results.append({
        'label': lab,
        'line_id': d['line_id'],
        'legacy': {
            'boq_code': d.get('boq_code'),
            'boq_name': d.get('boq_name'),
            'qty': d.get('planned_qty'),
            'crew': d.get('crew_id'),
            'facility': d.get('facility_building'),
            'discipline': d.get('construction_discipline'),
            'plan_value': d.get('plan_value'),
            'required_hours': d.get('required_hours'),
            'labor_cost': d.get('labor_cost'),
            'unit_price': d.get('unit_price'),
            'hours_per_unit': d.get('selected_hours_per_unit'),
            'labor_rate': d.get('labor_rate_per_hour'),
            'planned_at': d.get('planned_at'),
            'created_at': d.get('created_at'),
            'updated_at': d.get('updated_at'),
            'available_qty_before_add': d.get('available_qty_before_add'),
            'planning_remaining_qty': d.get('planning_remaining_qty'),
            'already_reserved_qty': d.get('already_reserved_qty'),
            'customer_accepted_qty': d.get('customer_accepted_qty'),
            'has_system_col': 'system' in d,
            'has_iwp_col': 'iwp' in d,
        },
        'plan_count_same_boq': len(plans),
        'level1_count': len(level1),
        'level2_count': len(level2),
        'level3_count': len(level3),
        'other_facility_count': len(other_facility),
        'level1_ids': [p.get('plan_line_id') for p in level1],
        'level2_ids': [p.get('plan_line_id') for p in level2],
        'level3_ids': [p.get('plan_line_id') for p in level3],
        'level4_notes': level4_notes,
        'closest_level': closest_level,
        'closest_plan_line_id': None if closest is None else closest.get('plan_line_id'),
        'norms': norms,
        'chronology': chron,
        'plans': compact_plans,
    })

out={
  'plan_columns_sample': plan_cols,
  'group_a_same_boq_as_b11': group_a,
  'results': results,
}
pathlib.Path(r'c:\csv_fix\_tmp_legacy_b_business_audit.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

# compact print
for r in results:
    print('====', r['label'], r['legacy']['boq_code'], 'qty', r['legacy']['qty'], 'crew', r['legacy']['crew'])
    print(' plan_same_boq', r['plan_count_same_boq'], 'L1', r['level1_count'], 'L2', r['level2_count'], 'L3', r['level3_count'], 'other_fac', r['other_facility_count'])
    for p in r['plans']:
        print('  PLAN', p['plan_line_id'][:8], 'st', p['status'], 'fac', p['facility'], 'crew', p['crew'], 'qty', p['planned_qty'], 'sys', p['system'], 'iwp', p['iwp'], 'val', p['plan_value'], 'hrs', p['labor_hours'], 'created', p['created_at'], 'sent', p['sent_to_constraints_at'])
    print(' legacy planned_at', r['legacy']['planned_at'], 'created', r['legacy']['created_at'])
    if r['norms']:
        print(' norms', json.dumps(r['norms'], ensure_ascii=False, default=str))
    print()
