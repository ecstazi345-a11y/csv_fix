import json, pathlib
d=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_tech_dup_audit.json').read_text(encoding='utf-8'))
for i,c in enumerate(d['candidates'],1):
    print('|'.join([
        str(i),
        c['GROUP_ID'],
        c['KEEP_PLAN_LINE_ID'],
        c['DELETE_PLAN_LINE_ID'],
        str(c['BOQ_CODE']),
        str(c['FACILITY']),
        str(c['CREW']),
        str(c['QTY']),
        str(c['VALUE']),
        str(c['HOURS']),
        str(c['CREATED_AT']),
    ]))
