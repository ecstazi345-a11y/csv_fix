# PNR MVP-0 Implementation Plan

**Identifier:** PNR-MVP-0  
**Status:** IMPLEMENTATION PLAN ONLY — does not authorize SQL, code, Streamlit, seed, or Supabase change until increment MVP-0.1 is explicitly started  
**Date:** 2026-09-08  
**Worktree:** `C:/csv_fix_pnr`  
**Branch:** `wip/pnr-dataset-foundation`  
**Depends on:** ADR-PNR-001 (laws), PNR schema v0.1 design (full target)  
**This document does not modify those files.**

Principle: **real data first. Tune the model after real usage.**  
The 12-entity architecture remains valid. MVP-0 implements **five tables** and a field form so site events can start arriving.

Vertical slice:

```
FIELD USER → STREAMLIT FORM → STRUCTURED PNR EXECUTION EVENT → SUPABASE → EVENT JOURNAL
```

---

## 1. MVP goal

A site engineer can, in Russian, on a phone or laptop:

1. pick System → Object → Work scope → Operation (or describe an unmapped operation);
2. set result (`PASS` / `FAIL` / `PARTIAL` / `BLOCKED`);
3. enter people count and duration;
4. see labor hours auto-calculated;
5. enter reason / optional comment;
6. press **СОХРАНИТЬ**;
7. get clear success or error;
8. see the event in a simple journal as its own row.

A later PASS on the same object/operation is a **new** row. The FAIL stays.

Out of MVP-0: analytics, GESN, BOQ maps, baselines, acceptance instances, Agent Runtime, SMR, dashboards.

---

## 2. Exact five-table scope

| # | Table | Role in MVP-0 |
|---|--------|----------------|
| 1 | `eos_systems` | Stable system identity (`P1`) |
| 2 | `pnr_objects` | Commissioning objects (`ШСАУ-P1`) |
| 3 | `pnr_work_scopes` | Work scopes (`Автоматика / алгоритмы`) |
| 4 | `pnr_operations` | Catalog operations (`PNR-AUT-003`) |
| 5 | `pnr_execution_events` | Append-only field facts |

**Do not implement now:**  
`pnr_normative_items`, `pnr_labor_baselines`, `pnr_operation_commercial_map`, `pnr_operation_normative_map`, `pnr_acceptance_requirements`, `pnr_operation_acceptance_map`, `pnr_event_labor`, measurements, evidence, defects, constraints, physical state engine, signed acceptance records, Agent Runtime.

`pnr_event_labor` stays documented architecture. MVP-0 stores a **single total** labor triple on the event (section 14, 16).

---

## 3. Minimum fields per table

Omit display-only / future fields from schema v0.1 unless the form or journal needs them.

### 3.1 `eos_systems`

| Field | Type | Null | MVP need |
|-------|------|------|----------|
| `system_id` | `uuid` | NO | PK |
| `system_code` | `text` | NO | Stable code `P1` |
| `display_name` | `text` | NO | Form label |
| `legacy_system_label` | `text` | YES | Correlation to SMR text; optional |
| `is_active` | `boolean` | NO | Hide inactive in form |
| `created_at` | `timestamptz` | NO | Audit |

Omit: long `description`, `updated_at` (add later if catalog editing UI appears).

### 3.2 `pnr_objects`

| Field | Type | Null | MVP need |
|-------|------|------|----------|
| `object_id` | `uuid` | NO | PK |
| `system_id` | `uuid` | NO | Cascade filter |
| `object_code` | `text` | NO | `SHSAU-P1` |
| `object_name` | `text` | NO | `ШСАУ-P1` |
| `is_active` | `boolean` | NO | |
| `created_at` | `timestamptz` | NO | |

Omit: `object_kind` (not needed for the form).

### 3.3 `pnr_work_scopes`

| Field | Type | Null | MVP need |
|-------|------|------|----------|
| `work_scope_id` | `uuid` | NO | PK |
| `system_id` | `uuid` | NO | Cascade |
| `scope_code` | `text` | NO | `AUT` |
| `scope_name` | `text` | NO | `Автоматика / алгоритмы` |
| `is_active` | `boolean` | NO | |
| `created_at` | `timestamptz` | NO | |

### 3.4 `pnr_operations`

| Field | Type | Null | MVP need |
|-------|------|------|----------|
| `operation_id` | `uuid` | NO | PK |
| `work_scope_id` | `uuid` | NO | Cascade; implies system |
| `operation_code` | `text` | NO | `PNR-AUT-003` |
| `operation_name` | `text` | NO | `Проверка алгоритма` |
| `is_active` | `boolean` | NO | |
| `created_at` | `timestamptz` | NO | |

No `UNKNOWN` sentinel row.

### 3.5 `pnr_execution_events`

Minimum safe fact for a real site event:

| Field | Type | Null | MVP need |
|-------|------|------|----------|
| `event_id` | `uuid` | NO | PK |
| `system_id` | `uuid` | NO | Journal + invariant (denormalized; must match object) |
| `object_id` | `uuid` | NO | Grain |
| `operation_id` | `uuid` | YES | Catalog branch of XOR |
| `unmapped_operation_name` | `text` | YES | Unmapped branch of XOR |
| `unmapped_operation_code` | `text` | YES | Optional field code |
| `result` | `text` | NO | PASS/FAIL/PARTIAL/BLOCKED |
| `occurred_at` | `timestamptz` | NO | When it happened (form default: now) |
| `people_count` | `integer` | NO | Field input |
| `duration_hours` | `numeric` | NO | Field input |
| `labor_hours` | `numeric` | NO | `people_count × duration_hours` |
| `result_reason` | `text` | YES | Problem / reason |
| `comment` | `text` | YES | Optional |
| `source` | `text` | NO | e.g. `pnr_field_form_mvp0` |
| `created_at` | `timestamptz` | NO | Insert time |

**Omit from MVP-0 events:** `completion_pct`, labor categories, person FK, `is_current`, `occurred_on` as a separate required date (derive for journal display from `occurred_at`). Schema v0.1 had `occurred_on`; MVP-0 uses `occurred_at` only to avoid two clocks. Journal shows local date/time from `occurred_at`.

**MVP vs schema v0.1 (intentional, compatible):**

| Schema v0.1 | MVP-0 |
|-------------|--------|
| No `system_id` on event (derived) | `system_id` stored; must equal `object.system_id` |
| Labor on `pnr_event_labor` | `people_count`, `duration_hours`, `labor_hours` on the event |
| `occurred_on` + optional `occurred_at` | `occurred_at` only |
| `recorded_at` / `recorded_by_label` | `created_at`; no person master |

These do not block later columns or `pnr_event_labor`.

---

## 4. PK / FK / CHECK / UNIQUE

### 4.1 `eos_systems`

- PK: `system_id`
- UNIQUE: `system_code`
- CHECK: `length(trim(system_code)) > 0`, `length(trim(display_name)) > 0`

### 4.2 `pnr_objects`

- PK: `object_id`
- FK: `system_id` → `eos_systems.system_id`
- UNIQUE: `(system_id, object_code)`
- CHECK: non-empty code/name

### 4.3 `pnr_work_scopes`

- PK: `work_scope_id`
- FK: `system_id` → `eos_systems.system_id`
- UNIQUE: `(system_id, scope_code)`
- CHECK: non-empty code/name

### 4.4 `pnr_operations`

- PK: `operation_id`
- FK: `work_scope_id` → `pnr_work_scopes.work_scope_id`
- UNIQUE: `(work_scope_id, operation_code)`
- CHECK: non-empty code/name

### 4.5 `pnr_execution_events`

- PK: `event_id`
- FK: `system_id` → `eos_systems.system_id`
- FK: `object_id` → `pnr_objects.object_id`
- FK: `operation_id` → `pnr_operations.operation_id` (nullable)
- UNIQUE: PK only. **Do not** unique `(object_id, operation_id)` or `(object_id, operation_id, day)`.
- CHECK `result in ('PASS','FAIL','PARTIAL','BLOCKED')`
- CHECK XOR:
  - catalogued: `operation_id IS NOT NULL` AND unmapped name/code IS NULL
  - unmapped: `operation_id IS NULL` AND `unmapped_operation_name` non-empty
- CHECK `people_count >= 1`
- CHECK `duration_hours > 0`
- CHECK `labor_hours > 0`
- CHECK `labor_hours = people_count * duration_hours` (numeric exact; form sends the product)
- CHECK `source` non-empty
- **Application (or trigger later):** `object.system_id = event.system_id`. If catalogued, operation’s work scope must belong to the same system. v0.1 called this UNRESOLVED; MVP-0 enforces it in the **service** before insert. Do not add a DB trigger in MVP-0 unless the SQL increment is still tiny.

Indexes: PK; `occurred_at DESC`; `object_id`; `system_id`; `operation_id` (partial).

Catalog rows: no UPDATE/DELETE from the field form. Events: INSERT only.

---

## 5. Creation order

1. `eos_systems` (no PNR FKs)
2. `pnr_objects`
3. `pnr_work_scopes`
4. `pnr_operations`
5. `pnr_execution_events`
6. RLS enable + policies + grants in the **same** SQL increment (do not leave tables open)

No views required for MVP-0. Journal joins in Python.

---

## 6. Minimum P1 seed

**Do not write seed in this step.** MVP-0.2 only.

A file named “P1 Operation Catalog v0.1” is **not present** in this repository. The task references it as source material. MVP-0 therefore seeds only the **vertical-slice rows** already named in the business flow (and ADR/schema walkthrough), not a full catalog. Launch must not wait for catalog completeness (ADR Law 10). Unmapped path covers the rest.

### Recommended minimum (required for sanity test)

| Table | Rows |
|-------|------|
| `eos_systems` | `system_code=P1`, `display_name=Система P1`, `legacy_system_label=P1` |
| `pnr_objects` | `object_code=SHSAU-P1`, `object_name=ШСАУ-P1`, system P1 |
| `pnr_work_scopes` | `scope_code=AUT`, `scope_name=Автоматика / алгоритмы`, system P1 |
| `pnr_operations` | `operation_code=PNR-AUT-003`, `operation_name=Проверка алгоритма`, scope AUT |

That is **four catalog rows**. Enough to run:

`P1 → ШСАУ-P1 → Автоматика / алгоритмы → PNR-AUT-003 → FAIL` then a second event `PASS`.

### Optional extras (only if still small)

Do **not** require these before first field save:

- One extra object on P1 so the object dropdown is not a single item (e.g. a second cabinet/unit **only if** a real site name is known — do not invent a fake fleet).
- Extra operations from a future P1 catalog import.

Default: **required four rows only.**

Do not seed: BOQ maps, GESN 37.44 h, 800 h baseline, example labor categories, fictional UUIDs from the schema doc as if they were production keys. Let the database generate UUIDs.

---

## 7. Streamlit form UX

Site engineer, Russian, not enterprise.

**Placement (recommended):** isolated app, same idea as `form_app/daily_progress_form_app.py` (centered, no 24-page sidebar, large save button). Proposed path for a later increment: `form_app/pnr_execution_app.py` (name may be adjusted at implementation). Optional later: a thin `pages/` link in the main dashboard for office users — **not** required for MVP-0.

**Do not copy** that form’s **security** (anon insert policy). Copy only the field-UX shape.

Flow (one screen, cascading):

1. **Система** — select from active `eos_systems`
2. **Объект** — objects of that system
3. **Раздел работ** — work scopes of that system
4. **Операция** — operations of that scope, plus last option **«Другая операция (нет в каталоге)»**
5. If unmapped: **Название операции** (required), **Код** (optional)
6. **Результат** — PASS / FAIL / PARTIAL / BLOCKED (Russian labels, stored English codes)
7. **Количество людей** — integer ≥ 1
8. **Продолжительность, ч** — number > 0
9. **Трудозатраты, чел·ч** — read-only, `people × duration`
10. **Причина / проблема** — required if result ≠ PASS; optional if PASS
11. **Комментарий** — optional
12. **СОХРАНИТЬ**

No BOQ, GESN, crew master, photos, GPS, completion %.

After save: green **«Событие сохранено»** with result + object + time. On failure: red message, form values kept. Do not clear the cascade on success in a way that punishes double-entry; reset result/labor/reason, keep system/object/scope.

Journal: same app, second tab **«Журнал»** (MVP-0.5), or below the form if that is less navigation. Two tabs is enough.

---

## 8. Event write flow

```
User taps СОХРАНИТЬ
  → Streamlit validates locally
      (cascade filled, XOR, people≥1, duration>0, reason if not PASS)
  → labor_hours := people_count * duration_hours
  → services/pnr layer (server) validates again
      (object.system_id == selected system;
       if operation_id: operation.work_scope.system_id == system;
       XOR; labor identity)
  → INSERT into pnr_execution_events only
  → no UPDATE, no UPSERT, no DELETE
  → return event_id
```

Catalog tables are **read** by the form, never written by it.

`source` constant: `pnr_field_form_mvp0`.

---

## 9. Journal read flow

```
SELECT events (order occurred_at desc, created_at desc)
  JOIN objects, systems, work_scopes, operations
  LIMIT ~200
```

Columns:

| Column | Source |
|--------|--------|
| Дата/время | `occurred_at` |
| Система | `eos_systems.display_name` / code |
| Объект | `pnr_objects.object_name` |
| Раздел работ | scope name; blank if unmapped and scope not stored on event |
| Операция | catalog `code — name` OR unmapped name |
| Результат | `result` |
| Люди | `people_count` |
| Продолжительность | `duration_hours` |
| Чел·ч | `labor_hours` |
| Причина | `result_reason` |

FAIL then PASS = **two rows**. No “latest only”.

Optional KPIs (count/sum in Python on the same page, no extra tables): total events, counts by result, sum `labor_hours`. No charts.

Unmapped events: operation column shows the typed name; scope may be shown from the form’s selected scope **only if we stored it**. MVP-0 does **not** add `work_scope_id` on the event (not in the minimum field list). Journal scope for unmapped rows is empty unless we later add that column. Acceptable for MVP-0.

---

## 10. Supabase access / security approach

### Repository evidence (do not invent)

| Pattern | Evidence | Verdict for PNR |
|---------|----------|-----------------|
| Streamlit pages read via `services/supabase_client.py` + `SUPABASE_KEY` (anon) | `services/supabase_client.py` | OK for **existing** SMR reads. **Do not** use this client for PNR **writes**. |
| Product writes use `SUPABASE_SECRET_KEY` server-side | constructor, passport, constraints pages/services | **Reuse this class of path** for PNR writes. |
| Isolated field form `form_app/` + `SUPABASE_SECRET_KEY` or anon fallback | `form_app/form_supabase.py` | Isolation of the app is good. **Anon fallback is not acceptable** for PNR if secret is missing — fail closed. |
| `daily_progress_form_submissions` RLS: `INSERT/SELECT to anon WITH CHECK (true)` | `sql/daily_progress_form_submissions.sql` | **Do not copy.** Open anon insert is an insecure MVP pattern. |
| Safer table: anon SELECT only; DML via `service_role` | `sql/monthly_resource_plan_r1_security_verify.sql` | **Closest existing target** for PNR tables. |
| Agent EOS-SEC | `security/**`, `agents/**` | Out of scope. Do not route PNR writes through Agent Runtime. |

Streamlit is a **server**. `.env` keys are not sent to the browser if the page never writes them into HTML/JS. Do not print keys. Do not use a browser-only anon key for inserts.

### Smallest safe write path

```
Streamlit server (form_app)
  → Python service using SUPABASE_SECRET_KEY only
  → PostgREST as service_role
  → INSERT public.pnr_execution_events
```

- No new secrets in the client bundle.
- Do not grant new INSERT on SMR tables or `boq_master_api`.
- Do not change existing RLS on non-PNR tables.
- Do not use `services/supabase_client.py` (anon) for PNR writes.
- If `SUPABASE_SECRET_KEY` is missing: form shows error, no insert.

Reads of the five PNR tables: same secret client in the PNR app (simplest; no need to open anon SELECT). Main dashboard pages need not read PNR in MVP-0.

---

## 11. Minimal RLS concept

**Do not implement SQL in this planning step.** MVP-0.1 must ship tables **with RLS on**.

Concept:

| Role | Catalogs (1–4) | `pnr_execution_events` |
|------|----------------|-------------------------|
| `anon` | no SELECT / no INSERT / no UPDATE / no DELETE | none |
| `authenticated` | none unless a later ADR says otherwise | none |
| `service_role` | SELECT (seed + form lists); INSERT/UPDATE catalogs **only** via SQL Editor seed, not the field form | SELECT + **INSERT**; no UPDATE; no DELETE |

Also:

- `ENABLE ROW LEVEL SECURITY` on all five tables.
- No `WITH CHECK (true)` to `anon`.
- Revoke accidental `GRANT ALL TO PUBLIC` if the SQL template would create it.
- Catalog `UPDATE`/`DELETE` not needed for field use; omit policies. Seed runs as service role in SQL Editor (bypasses RLS in Supabase).
- Event **UPDATE/DELETE** policies: **absent** (append-only even for service_role if we can; if service_role bypasses RLS, append-only is enforced in the Python service and by not shipping an update API). Document this honestly: **UNRESOLVED** how complete append-only is against a leaked service role. MVP-0 still must not expose that key to the browser.

Before field use: confirm with a privilege probe (read-only, same spirit as `monthly_resource_plan_r1_security_verify.sql`) that `anon` cannot INSERT events.

---

## 12. Error handling

| Case | User sees |
|------|-----------|
| Secret key missing | «Запись недоступна: нет ключа сервера.» Form disabled. |
| Catalog empty (no P1 seed) | «Нет систем. Обратитесь к администратору.» |
| Incomplete cascade | Native Streamlit validation; no insert |
| Unmapped without name | «Укажите название операции.» |
| Result ≠ PASS and empty reason | «Укажите причину / проблему.» |
| people/duration invalid | Block save |
| XOR / system mismatch (service) | «Нельзя сохранить: объект и система не совпадают.» (or operation/system) |
| Unique/check from Postgres | «Не сохранено. Проверьте данные.» + technical detail in expander, not a stack dump |
| Network / API | «Нет связи с базой. Повторите.» |

Never upsert on failure. Never delete the FAIL to “fix” a PASS.

---

## 13. Unmapped-operation path

Form option **«Другая операция (нет в каталоге)»**:

- `operation_id = NULL`
- `unmapped_operation_name` = typed name
- `unmapped_operation_code` = optional

DB XOR CHECK rejects mixed or empty operation identity.

Do not insert a catalog row `UNKNOWN`.

Later classification of unmapped events is out of MVP-0 (schema UNRESOLVED). Events remain valid history.

---

## 14. Labor-hours calculation

Field:

```
labor_hours = people_count × duration_hours
```

Example: 2 people × 4 h = **8 чел·ч**. Store all three columns. UI does not let the user edit `labor_hours` separately in MVP-0 (avoids drift).

CHECK enforces equality so a buggy client cannot store 2 × 4 = 99.

This is **total event labor**, not a category split, not completion %, not baseline consumption.

---

## 15. Append-oriented event rule

- INSERT only.
- No unique constraint that would collapse FAIL+PASS.
- Service has no `update()` / `upsert()` / `delete()` for events.
- Same object + same operation + new result = new `event_id`.

Journal must not `DISTINCT ON (object_id, operation_id)`.

---

## 16. Future migration to `pnr_event_labor`

Keep the concept. Do not build the table now.

Compatible evolution:

```
pnr_execution_events          (MVP-0 fact: what happened + crew total)
        │
        └── later: pnr_event_labor (why hours: PRODUCTIVE / REWORK / …)
```

**Migration without losing events:**

1. Create `pnr_event_labor` as in schema v0.1.
2. For each existing event with `labor_hours > 0` and no child rows, insert **one** component:
   - `labor_category = PRODUCTIVE` is **wrong** if some hours were constraint loss.
   - Safer backfill category: a dedicated `UNSPECIFIED` **or** leave events without children until a human splits them.
   - **Recommended:** do **not** auto-tag historical totals as `PRODUCTIVE`. Either skip backfill or use an explicit `UNSPECIFIED` value added by a later ADR. Forcing PRODUCTIVE would invent cause.
3. Keep `people_count`, `duration_hours`, `labor_hours` on the event as the **crew capture** (how many people, how long, total hours). `pnr_event_labor` becomes the **cause split** that must sum to `labor_hours` when fully decomposed.
4. Do not drop event labor columns in the same increment as adding `pnr_event_labor`.
5. New form versions can later add optional cause lines; old events stay queryable.

`people_count` / `duration_hours` were omitted in schema v0.1; MVP-0 puts them on the event because the field form needs them. That is an allowed simplification, not a deletion of `pnr_event_labor`.

---

## 17. Explicit deferred scope

Not in MVP-0:

- tables listed in section 2
- measurements / evidence / defects / constraints / state engine / signed acceptance
- Agent Runtime, Commissioning Agent
- SMR tables, monthly planning/passport/admission
- `boq_master_api` changes
- Facility / Person / Project masters
- QR/NFC, sensors
- dashboards beyond journal KPIs
- catalog admin UI (seed is SQL)
- EOS-SEC agent write pipeline

Future additions remain possible:

```
pnr_execution_events
      → pnr_event_labor

pnr_operations
      → pnr_operation_normative_map → pnr_normative_items (GESN)

pnr_operations
      → pnr_operation_commercial_map → boq_master_api

pnr_operations
      → pnr_operation_acceptance_map → pnr_acceptance_requirements
      → (later) acceptance instances

pnr_execution_events
      → measurements / evidence / state
```

MVP-0 must not: write PNR facts into `daily_progress_*`; unique-lock “current result”; store fake completion %; clone BOQ.

---

## 18. Implementation increments

Recommended sequence is **kept**. Safer than reversing UI-before-schema. One change vs a naive copy of `daily_progress_form_submissions`: **RLS and grants live in MVP-0.1**, not after first live save.

| Increment | Deliverable | Out |
|-----------|-------------|-----|
| **MVP-0.1** | Schema SQL for the five tables + indexes + checks + RLS/grants. Manual apply in SQL Editor. No seed. | No Streamlit, no SMR, no BOQ |
| **MVP-0.2** | P1 minimum seed SQL (four catalog rows). | No extra invented catalog |
| **MVP-0.3** | `services/` PNR read-write module: secret-key client, catalog reads, event INSERT, validations. Unit tests with fakes. | No page |
| **MVP-0.4** | Isolated Streamlit field form (Russian). Save + success/error. | No journal required yet |
| **MVP-0.5** | Journal tab/page + optional KPI counts | No analytics |
| **MVP-0.6** | Live sanity: FAIL then PASS on ШСАУ-P1 / PNR-AUT-003; confirm two rows; confirm anon cannot insert. | No production announcement automation |

Do not merge 0.4–0.6 into one “big page” if it hides a failed write path. 0.3 before 0.4 is mandatory so the form is not a pile of inline SQL.

**Why not form-first:** the existing shift form shipped with open anon INSERT. PNR must not repeat that. Schema+RLS first, then a service that fails closed, then UI.

---

## Quality bar for later implementation

- Only `C:/csv_fix_pnr`
- Do not touch `C:/csv_fix`, `agents/**`, `docs/agentic_architecture/**`, SMR tables, `boq_master_api`, Agent Runtime
- Do not expand to 12 tables
- Do not block save on incomplete GESN/BOQ/acceptance catalogs
- ADR and schema design files stay as architecture; this plan is the MVP cut

---

## Document control

| Item | Value |
|------|--------|
| Authorizes SQL now | No (starts at MVP-0.1 after review) |
| Authorizes Streamlit now | No |
| Authorizes seed now | No |
| Table count | **5** |
| Next | Review this plan and start MVP-0.1 schema implementation |
