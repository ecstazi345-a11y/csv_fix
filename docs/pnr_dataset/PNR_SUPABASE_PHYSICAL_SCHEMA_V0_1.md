# PNR Supabase Physical Schema v0.1 — Design

**Identifier:** PNR-SCHEMA-V0.1  
**Status:** DESIGN ONLY — not an implementation permit  
**Date:** 2026-09-08  
**Worktree:** `C:/csv_fix_pnr`  
**Branch context:** `wip/pnr-dataset-foundation`  
**Governs:** ADR-PNR-001 (refined)  
**This document contains no SQL, no migrations, and no authorization to create tables or write product data.**

Example values in this document (P1, 800 h, 1574.30 RUB/h, GESNp03-01-060-04, 37.44 h, fictional UUIDs) are **design fixtures only**. They must not be inserted into any database.

---

## 0. Purpose and quality bar

This document specifies the minimum viable physical contract for the twelve v0.1 entities so a later SQL increment can be reviewed against ADR-PNR-001.

It must:

- preserve four truth layers;
- give PNR a stable `system_id` via `eos_systems` without refactoring SMR;
- keep execution history append-oriented;
- allow unmapped operations without a fake catalog row;
- reference `boq_master_api` using repository-proven identity only.

It must not:

- clone BOQ;
- treat BOQ as GESN;
- derive physical completion from labor;
- model signed acceptance instances;
- couple to Agent Runtime or SMR fact tables;
- invent unsupported database columns.

---

## 1. Four truth layers (non-collapsible)

| Layer | Question | Store | v0.1 rule |
|-------|----------|--------|-----------|
| 1 Commercial | За что нам платят? | existing `boq_master_api` | referenced, not redesigned, not cloned |
| 2 Normative | Какая нормативная трудоёмкость в исходной смете / норме? | `pnr_normative_items` | source-authoritative; no auto-split |
| 3 Agreed baseline | Сколько труда согласовано как плановая трудовая база? | `pnr_labor_baselines` | versioned; approved history kept |
| 4 Execution reality | Что произошло и сколько труда потребовалось? | `pnr_execution_events` + `pnr_event_labor` | append-oriented; labor by cause |

There is **no** `completion_pct` column anywhere in v0.1.

---

## 2. Shared identity coexistence

`eos_systems` is shared Execution OS identity, not a PNR-private registry.

PNR tables that need a system take `system_id uuid` → `eos_systems.system_id`.

Existing SMR / planning / daily-progress tables keep `system` / `system_label` **text**. This design:

- does not migrate those tables;
- does not alter those columns;
- does not backfill product data;
- does not create Facility / Project / Person masters;
- does not add FKs from SMR into `eos_systems`.

Coexistence pattern:

```
SMR/planning row.system_label  = "P1"     (unchanged text)
eos_systems.system_code        = "P1"     (stable business code)
eos_systems.display_name       = "Система P1 — приточная вентиляция"  (mutable label)
eos_systems.legacy_system_label = "P1"    (optional correlation only)
pnr_objects.system_id          = eos_systems.system_id
```

If a display name later changes, `system_id` and `system_code` do not. Correlation via `legacy_system_label` may help humans match historical SMR text; it is not identity and is not maintained by SMR triggers.

**UNRESOLVED:** whether `legacy_system_label` should be unique. Not required in v0.1 because SMR labels are not proven unique in the audit.

---

## 3. Physical grain

```
eos_systems
  ├─ pnr_objects
  ├─ pnr_work_scopes
  │    └─ pnr_operations
  │         ├─ pnr_operation_commercial_map  →  boq_master_api (logical)
  │         ├─ pnr_operation_normative_map   →  pnr_normative_items
  │         └─ pnr_operation_acceptance_map  →  pnr_acceptance_requirements
  ├─ pnr_labor_baselines
  └─ (via object) pnr_execution_events
                    └─ pnr_event_labor
```

Event grain:

```
1 execution event
  = 1 attempt
  × 1 operation (catalogued XOR unmapped)
  × 1 commissioning object
  × defined time/context
  × defined result ∈ {PASS, FAIL, PARTIAL, BLOCKED}
```

Catalog operation belongs to one work scope. Work scope belongs to one system. Object belongs to one system. Event belongs to one object and therefore one system.

---

## 4. Global conventions

| Topic | v0.1 choice |
|-------|-------------|
| Surrogate PK | `uuid` on every new table |
| Timestamps | `timestamptz` |
| Money / hours | `numeric` — not float |
| Codes | `text`, trimmed, stable |
| Display names | `text`, mutable on catalogs |
| Soft delete on catalogs | `is_active boolean not null default true` — no hard delete of referenced rows |
| Person identity | omitted (no Person master) |
| Facility / project | omitted as masters; no invented FKs |
| `people_count` / duration | **omitted** — labor is stored as person-hours; reconstructing FTE from people × duration is deferred |
| RLS | **UNRESOLVED** — existing product uses RLS; policies are not designed here |
| Schema name | assumed `public`, same database as Execution OS |

Mutability classes used below:

- **Append-only:** insert permitted; update/delete of fact fields forbidden.
- **Versioned:** new row for a new approved version; prior approved rows remain.
- **Catalog:** code immutable; display fields updatable; no destructive delete if referenced.

---

## 5. Existing commercial reference — `boq_master_api`

**This table is not redesigned.**

### 5.1 How PNR should reference it

`pnr_operation_commercial_map` stores a **logical commercial reference**, not a copy of BOQ attributes.

### 5.2 Stable identifiers actually available (repository evidence)

Proven from this repository, not from a live catalog dump:

| Identifier | Evidence | What it is |
|------------|----------|------------|
| `airtable_record_id` | `boq_sync_upsert.py` upserts with `on_conflict=airtable_record_id` | Sync / source-row identity. Unique for the Airtable sync path. Not a commercial position code. |
| `boq_code` | Written by sync; used across planning, forms, views | Commercial position **code**. Used as a business identifier throughout the product. |
| Composite grain used by existing views | `sql/boq_execution_history_v1.sql`, `sql/monthly_scope_picker_v1.sql` | Operational BOQ grain is aggregated as `project_code + boq_code + facility_building + construction_discipline` (normalized). This exists because a single `boq_code` is **not** treated as unique by those views. |
| `is_deleted` | sync soft-delete | Rows can be logically deleted. |

Also written by sync and read by views: `name`, `description`, `facility_building`, `construction_discipline`, `unit_of_measure`, `project_name`, `project_code` (used in SQL even though the Python mapper shown does not set it), numeric qty/price/value fields, `last_synced_at`.

### 5.3 Identity risks

1. **No `CREATE TABLE` for `boq_master_api` exists in this repository.** PostgreSQL primary key, unique constraints, and types of that table are **not proven** here.
2. **`boq_code` is not a proven unique key.** Views aggregate multiple master rows. `form_app/daily_progress_form_app.py` explicitly `drop_duplicates(subset=["boq_code"])`.
3. **`airtable_record_id` is proven as the sync conflict key**, but it is Airtable row identity. Using it as the *meaning* of a commercial map would couple PNR commissioning operations to a source-system record, not to a commercial position. Soft-deleted Airtable rows remain.
4. **Project identity on BOQ is weak** (audit: no authoritative projects table; SQL uses `project_code` with a documented `БХК` fallback).

### 5.4 Can a PostgreSQL FK be safely enforced?

**No — not from current repository evidence.**

Enforcing `REFERENCES boq_master_api (...)` would require inventing which column is the PK or unique business key. This design **refuses** to invent a convenience column on `boq_master_api` and **refuses** to assume a UUID PK that is not in the repo.

v0.1 commercial map therefore:

- stores `boq_code text not null` as the primary commercial correlation;
- may store optional `airtable_record_id`, `project_code`, `facility_building`, `construction_discipline` as **correlation qualifiers**, not as a redesigned BOQ grain;
- does **not** declare a database FK to `boq_master_api`;
- enforces referential honesty at **application** level (lookup of a non-deleted master row before insert), until a later ADR proves a unique BOQ identity.

**UNRESOLVED:** whether a later proven unique key (if a live `\d boq_master_api` shows one) should replace this logical reference. Do not guess it now.

---

# Entity specifications (01–12)

Field tables use:

- **Req** = required (`NOT NULL`)
- **Null** = nullable
- Conceptual PostgreSQL types only — not executable SQL.

---

## 01. `eos_systems`

### 1. Purpose

Shared Execution OS registry of one physical engineering system with one durable `system_id`. Not PNR-owned. Consumed by PNR now; intended for SMR, Acceptance, Commercial, agents, and reality capture later **without** migrating those domains in v0.1.

### 2. Table grain

One row = one physical system.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `system_id` | `uuid` | Req | Durable identity |
| `system_code` | `text` | Req | Stable business code, e.g. `P1`. Does not change when the label changes. |
| `display_name` | `text` | Req | Human label; mutable |
| `description` | `text` | Null | Optional |
| `legacy_system_label` | `text` | Null | Correlation to existing SMR `system` / `system_label` text. Not identity. |
| `is_active` | `boolean` | Req | Catalog lifecycle |
| `created_at` | `timestamptz` | Req | Insert time |
| `updated_at` | `timestamptz` | Req | Last catalog edit |

Omitted: facility_id, project_id, parent system, geometry, QR — deferred.

### 6. PK

`system_id`

### 7. FK

None.

### 8. Business key

`system_code`

### 9. UNIQUE

- `system_code`

### 10. CHECK

- `length(trim(system_code)) > 0`
- `length(trim(display_name)) > 0`

### 11. Indexes

- PK
- unique `system_code`
- non-unique `legacy_system_label` (correlation lookups)

### 12. Lifecycle / mutability

Catalog. `system_id` and `system_code` immutable after insert. `display_name`, `description`, `legacy_system_label`, `is_active` updatable. No hard delete if any PNR row references `system_id`.

### 13. Source of truth

This table, once physically created. Until then, the contract exists only on paper. Existing SMR labels remain a **separate** operational text stream.

### 14. Relationships / cardinality

`eos_systems` 1 — * `pnr_objects`, `pnr_work_scopes`, `pnr_labor_baselines`.

### 15. Example (fictional)

| Field | Value |
|-------|--------|
| `system_id` | `11111111-0001-4000-8000-0000000000p1` |
| `system_code` | `P1` |
| `display_name` | `Система P1` |
| `legacy_system_label` | `P1` |
| `is_active` | `true` |

---

## 02. `pnr_objects`

### 1. Purpose

Commissioning objects on which operations are attempted (units, VFDs, dampers, panels, …). Not an equipment asset registry.

### 2. Table grain

One row = one commissioning object belonging to exactly one system.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `object_id` | `uuid` | Req | Identity |
| `system_id` | `uuid` | Req | Owning system |
| `object_code` | `text` | Req | Stable code within system |
| `object_name` | `text` | Req | Display name; mutable |
| `object_kind` | `text` | Null | Free-text kind (`SUPPLY_UNIT`, `VFD`, `FIRE_DAMPER`, `AUTOMATION_PANEL`, …). Not a closed enum in v0.1 — **UNRESOLVED** whether a controlled vocabulary is needed after real data. |
| `is_active` | `boolean` | Req | Catalog lifecycle |
| `created_at` | `timestamptz` | Req | |
| `updated_at` | `timestamptz` | Req | |

Omitted: serial numbers, QR/NFC, parent-child equipment tree, facility FK.

### 6. PK

`object_id`

### 7. FK

`system_id` → `eos_systems.system_id`

### 8. Business key

`(system_id, object_code)`

### 9. UNIQUE

`(system_id, object_code)`

### 10. CHECK

- `length(trim(object_code)) > 0`
- `length(trim(object_name)) > 0`

### 11. Indexes

- PK
- unique `(system_id, object_code)`
- `system_id`

### 12. Lifecycle / mutability

Catalog. `object_id`, `system_id`, `object_code` immutable (object does not move between systems in v0.1). Name/kind/`is_active` updatable. No hard delete if events reference the object.

### 13. Source of truth

PNR domain.

### 14. Relationships / cardinality

`eos_systems` 1 — * `pnr_objects`  
`pnr_objects` 1 — * `pnr_execution_events`

An object is **not** required to belong to a work scope. Work scopes classify operations, not objects. Events join object and operation.

### 15. Example (fictional)

| `object_id` | `object_code` | `object_name` |
|-------------|---------------|----------------|
| `22222222-0001-4000-8000-000000000001` | `P1-SU` | `Supply Unit P1` |
| `22222222-0001-4000-8000-000000000002` | `P1-VFD` | `VFD P1` |
| `22222222-0001-4000-8000-000000000003` | `P1-FD-01` | `Fire Damper P1-01` |
| `22222222-0001-4000-8000-000000000004` | `P1-AUT` | `Automation Panel P1` |

All with `system_id` = P1.

---

## 03. `pnr_work_scopes`

### 1. Purpose

Commissioning work scopes grouping operations for a system (e.g. Automation / Algorithms).

### 2. Table grain

One row = one work scope of one system.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `work_scope_id` | `uuid` | Req | |
| `system_id` | `uuid` | Req | Owning system |
| `scope_code` | `text` | Req | Stable within system, e.g. `AUT` |
| `scope_name` | `text` | Req | e.g. `Automation / Algorithms` |
| `is_active` | `boolean` | Req | |
| `created_at` | `timestamptz` | Req | |
| `updated_at` | `timestamptz` | Req | |

### 6. PK

`work_scope_id`

### 7. FK

`system_id` → `eos_systems.system_id`

### 8. Business key

`(system_id, scope_code)`

### 9. UNIQUE

`(system_id, scope_code)`

### 10. CHECK

- non-empty `scope_code`, `scope_name`

### 11. Indexes

- PK
- unique `(system_id, scope_code)`
- `system_id`

### 12. Lifecycle / mutability

Catalog. `work_scope_id`, `system_id`, `scope_code` immutable. Name/`is_active` updatable.

### 13. Source of truth

PNR domain.

### 14. Relationships / cardinality

`eos_systems` 1 — * `pnr_work_scopes`  
`pnr_work_scopes` 1 — * `pnr_operations`

Work scopes are **system-local** in v0.1 (P1 AUT is not the same row as P2 AUT). Cross-system reusable templates are omitted (prefer omission).

### 15. Example (fictional)

| Field | Value |
|-------|--------|
| `work_scope_id` | `33333333-0001-4000-8000-0000000000aut` |
| `system_id` | P1 |
| `scope_code` | `AUT` |
| `scope_name` | `Automation / Algorithms` |

---

## 04. `pnr_operations`

### 1. Purpose

Approved PNR operation catalog. Unmapped field work is **not** stored here.

### 2. Table grain

One row = one catalog operation in one work scope.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `operation_id` | `uuid` | Req | |
| `work_scope_id` | `uuid` | Req | Owning work scope (implies system) |
| `operation_code` | `text` | Req | e.g. `PNR-AUT-003` |
| `operation_name` | `text` | Req | e.g. `Проверка алгоритма` |
| `description` | `text` | Null | |
| `is_active` | `boolean` | Req | |
| `created_at` | `timestamptz` | Req | |
| `updated_at` | `timestamptz` | Req | |

No `UNKNOWN` sentinel row.

### 6. PK

`operation_id`

### 7. FK

`work_scope_id` → `pnr_work_scopes.work_scope_id`

System is derived: `operation → work_scope → system`. No denormalized `system_id` (avoid duplication).

### 8. Business key

`(work_scope_id, operation_code)`

### 9. UNIQUE

`(work_scope_id, operation_code)`

### 10. CHECK

- non-empty `operation_code`, `operation_name`

### 11. Indexes

- PK
- unique `(work_scope_id, operation_code)`
- `work_scope_id`

### 12. Lifecycle / mutability

Catalog. `operation_id`, `work_scope_id`, `operation_code` immutable. Name/description/`is_active` updatable. Deactivating does not rewrite events.

### 13. Source of truth

PNR catalog. Not inferred from events.

### 14. Relationships / cardinality

`pnr_work_scopes` 1 — * `pnr_operations`  
`pnr_operations` 1 — * maps (commercial, normative, acceptance)  
`pnr_operations` 0..1 — * `pnr_execution_events` (nullable on the event for unmapped attempts)

### 15. Example (fictional)

| Field | Value |
|-------|--------|
| `operation_id` | `44444444-0001-4000-8000-000000000003` |
| `work_scope_id` | AUT / P1 |
| `operation_code` | `PNR-AUT-003` |
| `operation_name` | `Проверка алгоритма` |

---

## 05. `pnr_normative_items`

### 1. Purpose

Authoritative normative / estimate **source positions** relevant to commissioning labor analysis. Layer 2. Not a commercial BOQ clone. Not an allocation table.

### 2. Table grain

One row = one source-document position as supplied (code + revision + quantity/hours as in the source).

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `normative_item_id` | `uuid` | Req | |
| `source_document` | `text` | Req | Estimate / norm document identity as supplied |
| `source_revision` | `text` | Null | Revision if the source has one |
| `section` | `text` | Null | Section as supplied |
| `norm_code` | `text` | Req | e.g. `GESNp03-01-060-04` |
| `norm_name` | `text` | Req | e.g. `central air-conditioning system` |
| `quantity` | `numeric` | Null | As supplied; do not invent |
| `unit` | `text` | Null | As supplied, e.g. `installation` |
| `normative_labor_hours` | `numeric` | Null | As supplied; **never calculated by split** |
| `stage_or_mode` | `text` | Null | As supplied, e.g. `no-load commissioning` |
| `notes` | `text` | Null | Provenance notes, not calculated hours |
| `is_active` | `boolean` | Req | |
| `created_at` | `timestamptz` | Req | |
| `updated_at` | `timestamptz` | Req | |

No `allocated_hours`, no `hours_per_operation`.

Hours may be NULL if the source position exists but labor is not stated. That is preferable to inventing 0.

### 6. PK

`normative_item_id`

### 7. FK

None (not bound to a system; operations provide system context through mapping).

### 8. Business key

`(source_document, coalesce(source_revision, ''), norm_code, coalesce(stage_or_mode, ''))`

Exact unique expression is **UNRESOLVED** until real estimate documents are inspected (same norm code may repeat by stage). v0.1 requires uniqueness sufficient to prevent accidental duplicate loads of the same source line; implementers must not collapse distinct source lines.

### 9. UNIQUE

Recommended unique: `(source_document, source_revision, norm_code, stage_or_mode)` using NULLS NOT DISTINCT if PostgreSQL version allows; otherwise a documented application uniqueness rule.

**UNRESOLVED:** PostgreSQL version / `NULLS NOT DISTINCT` availability in the current Supabase project is not proven in this repository.

### 10. CHECK

- non-empty `source_document`, `norm_code`, `norm_name`
- `quantity is null or quantity >= 0`
- `normative_labor_hours is null or normative_labor_hours >= 0`

### 11. Indexes

- PK
- `(norm_code)`
- `(source_document, source_revision)`

### 12. Lifecycle / mutability

Catalog / source snapshot. Do not silently overwrite `normative_labor_hours` because a later revision exists — load a new row with a new `source_revision` (or new item) and deactivate the old one. **UNRESOLVED:** whether revisioning should mirror baseline `SUPERSEDED` status; v0.1 uses `is_active` plus `source_revision` only.

### 13. Source of truth

The estimate / GESN source document, stored here. Not `boq_master_api`. Not actuals.

### 14. Relationships / cardinality

`pnr_normative_items` * — * `pnr_operations` via `pnr_operation_normative_map`

### 15. Example (fictional)

| Field | Value |
|-------|--------|
| `normative_item_id` | `55555555-0001-4000-8000-000000000060` |
| `source_document` | `Estimate-PNR-P1-revA` |
| `source_revision` | `A` |
| `norm_code` | `GESNp03-01-060-04` |
| `norm_name` | `central air-conditioning system` |
| `quantity` | `1` |
| `unit` | `installation` |
| `normative_labor_hours` | `37.44` |
| `stage_or_mode` | `no-load commissioning` |

---

## 06. `pnr_labor_baselines`

### 1. Purpose

Versioned customer-agreed / contractual labor baseline at **system** grain (layer 3). Not actual. Not GESN. Not BOQ.

### 2. Table grain

One row = one version of one baseline type for one system.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `baseline_id` | `uuid` | Req | |
| `system_id` | `uuid` | Req | System this baseline covers |
| `baseline_type` | `text` | Req | v0.1: `CUSTOMER_AGREED_PLAN` |
| `version_no` | `integer` | Req | Monotonic per `(system_id, baseline_type)` |
| `status` | `text` | Req | `DRAFT` / `APPROVED` / `SUPERSEDED` |
| `effective_from` | `date` | Null | Inclusive; required when `APPROVED` |
| `effective_to` | `date` | Null | Exclusive/inclusive **UNRESOLVED**; see invariants. Null = open-ended |
| `labor_hours` | `numeric` | Req | Agreed person-hours |
| `labor_rate_ex_vat` | `numeric` | Null | RUB/hour excl. VAT if agreed |
| `labor_amount_ex_vat` | `numeric` | Null | RUB excl. VAT if agreed |
| `currency_code` | `text` | Req | Default conceptual value `RUB` |
| `notes` | `text` | Null | |
| `created_at` | `timestamptz` | Req | |
| `approved_at` | `timestamptz` | Null | Set when status becomes `APPROVED` |

No `completion_pct`. No operation_id — a system baseline is **not** allocated to operations.

### 6. PK

`baseline_id`

### 7. FK

`system_id` → `eos_systems.system_id`

### 8. Business key

`(system_id, baseline_type, version_no)`

### 9. UNIQUE

`(system_id, baseline_type, version_no)`

Partial unique **intent** (may be application-level if partial indexes are deferred): at most one `APPROVED` row per `(system_id, baseline_type)` with `effective_to is null`.

### 10. CHECK

- `baseline_type in ('CUSTOMER_AGREED_PLAN')` — closed v0.1 vocab; extend only by ADR
- `status in ('DRAFT', 'APPROVED', 'SUPERSEDED')`
- `version_no >= 1`
- `labor_hours >= 0`
- `labor_rate_ex_vat is null or labor_rate_ex_vat >= 0`
- `labor_amount_ex_vat is null or labor_amount_ex_vat >= 0`
- `effective_to is null or effective_from is null or effective_to >= effective_from`
- if `status = 'APPROVED'` then `effective_from is not null` and `approved_at is not null`
- **Consistency of amount:** if hours, rate, and amount are all present, `labor_amount_ex_vat = labor_hours * labor_rate_ex_vat` (numeric exact). Do not store a contradictory triple.
- if `status = 'DRAFT'`, amount/rate may be incomplete; if `APPROVED` and rate is present, amount must be present.

### 11. Indexes

- PK
- unique `(system_id, baseline_type, version_no)`
- `(system_id, baseline_type, status)`

### 12. Lifecycle / mutability

Versioned.

- `DRAFT`: mutable (hours/rate/amount/dates/notes).
- `APPROVED`: **immutable** fact fields. To change numbers, insert `version_no + 1` as `DRAFT`, then approve it and set the previous row to `SUPERSEDED` with `effective_to` populated.
- `SUPERSEDED`: immutable.
- No delete of `APPROVED` / `SUPERSEDED` rows.

### 13. Source of truth

Customer-agreed / contractual baseline as recorded in PNR. Not derived from actuals or GESN.

### 14. Relationships / cardinality

`eos_systems` 1 — * `pnr_labor_baselines`  
No FK to operations.

### 15. Example (fictional — do not insert)

| Field | Value |
|-------|--------|
| `baseline_id` | `66666666-0001-4000-8000-000000000001` |
| `system_id` | P1 |
| `baseline_type` | `CUSTOMER_AGREED_PLAN` |
| `version_no` | `1` |
| `status` | `APPROVED` |
| `effective_from` | `2026-09-01` |
| `effective_to` | `null` |
| `labor_hours` | `800` |
| `labor_rate_ex_vat` | `1574.30` |
| `labor_amount_ex_vat` | `1259440.00` |
| `currency_code` | `RUB` |

A later approved 900 h baseline would be `version_no = 2`; version 1 remains with `status = SUPERSEDED`.

---

## 07. `pnr_operation_commercial_map`

### 1. Purpose

N:M map from catalog operations to existing BOQ commercial positions. Layer 1 relation only. No copied BOQ qty/price. No allocated labor.

### 2. Table grain

One row = one association between one operation and one referenced BOQ code (plus optional qualifiers).

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `map_id` | `uuid` | Req | |
| `operation_id` | `uuid` | Req | PNR operation |
| `boq_code` | `text` | Req | Commercial code as used in `boq_master_api` |
| `airtable_record_id` | `text` | Null | Optional sync-row correlation; **not** the commercial meaning |
| `project_code` | `text` | Null | Optional qualifier matching existing view grain |
| `facility_building` | `text` | Null | Optional qualifier |
| `construction_discipline` | `text` | Null | Optional qualifier |
| `notes` | `text` | Null | |
| `created_at` | `timestamptz` | Req | |

No `allocated_hours`. No copied `unit_price`.

### 6. PK

`map_id`

### 7. FK

`operation_id` → `pnr_operations.operation_id`  
**No FK** to `boq_master_api` (section 5.4).

### 8. Business key

v0.1: `(operation_id, boq_code)`

Qualifiers are correlation, not part of uniqueness, until BOQ identity is proven unique.

**UNRESOLVED:** if live data shows the same `boq_code` meaning different commercial positions by facility, uniqueness must be widened. Do not silently pick `airtable_record_id` as the business key.

### 9. UNIQUE

`(operation_id, boq_code)`

### 10. CHECK

- `length(trim(boq_code)) > 0`

### 11. Indexes

- PK
- unique `(operation_id, boq_code)`
- `boq_code`
- `operation_id`

### 12. Lifecycle / mutability

Association catalog. Rows may be inserted/removed if the association was wrong. This is not execution history; removing a map does not delete events. Do not use this table as a journal.

### 13. Source of truth

PNR mapping decision. Commercial attributes remain in `boq_master_api`.

### 14. Relationships / cardinality

`pnr_operations` * — * logical BOQ positions (N:M).  
1 operation may map to many BOQ codes. 1 BOQ code may map to many operations.

### 15. Example (fictional)

PNR-AUT-003 maps to `boq_code = '1500-04-01-01'` (illustrative code only). No hours allocated.

---

## 08. `pnr_operation_normative_map`

### 1. Purpose

N:M map from catalog operations to normative source items. Records **coverage relation**, not an hour split.

### 2. Table grain

One row = one association between one operation and one normative item.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `map_id` | `uuid` | Req | |
| `operation_id` | `uuid` | Req | |
| `normative_item_id` | `uuid` | Req | |
| `coverage_kind` | `text` | Req | `COVERED` / `PARTIAL` / `SHARED` |
| `notes` | `text` | Null | Qualitative only |
| `created_at` | `timestamptz` | Req | |

No `allocated_hours`. `SHARED` means several operations relate to the same source item; it does **not** authorize `hours / n`.

### 6. PK

`map_id`

### 7. FK

`operation_id` → `pnr_operations.operation_id`  
`normative_item_id` → `pnr_normative_items.normative_item_id`

### 8. Business key

`(operation_id, normative_item_id)`

### 9. UNIQUE

`(operation_id, normative_item_id)`

### 10. CHECK

- `coverage_kind in ('COVERED', 'PARTIAL', 'SHARED')`

### 11. Indexes

- PK
- unique `(operation_id, normative_item_id)`
- `normative_item_id`

### 12. Lifecycle / mutability

Association catalog, same mutability as commercial map. `coverage_kind` may be corrected; that is not labor allocation.

### 13. Source of truth

PNR mapping decision. Hours remain on `pnr_normative_items` as supplied.

### 14. Relationships / cardinality

N:M. Default `coverage_kind = 'COVERED'` is acceptable when the relation is simple. Do not over-model percentages.

### 15. Example (fictional)

PNR-AUT-003 ↔ GESNp03-01-060-04 with `coverage_kind = SHARED` (the 37.44 h remain on the normative item; they are not copied onto the operation).

---

## 09. `pnr_acceptance_requirements`

### 1. Purpose

Catalog of required acceptance **evidence / document types**.  
Example type: «Акт индивидуального испытания оборудования».  
This is **not** «Протокол №47 dated 18.09.2026 signed by X file Y».

### 2. Table grain

One row = one requirement type, reusable across operations/systems.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `requirement_id` | `uuid` | Req | |
| `requirement_code` | `text` | Req | Stable code |
| `requirement_name` | `text` | Req | Type title |
| `description` | `text` | Null | |
| `is_active` | `boolean` | Req | |
| `created_at` | `timestamptz` | Req | |
| `updated_at` | `timestamptz` | Req | |

No `document_number`, `signed_at`, `file_url`, `signatory`. Those belong to a future instance entity.

### 6. PK

`requirement_id`

### 7. FK

None (not system-bound in v0.1).

### 8. Business key

`requirement_code`

### 9. UNIQUE

`requirement_code`

### 10. CHECK

- non-empty code and name

### 11. Indexes

- PK
- unique `requirement_code`

### 12. Lifecycle / mutability

Catalog. Code immutable. Name/description/`is_active` updatable.

### 13. Source of truth

PNR / acceptance-type catalog. Not proof of an issued document.

### 14. Relationships / cardinality

`pnr_acceptance_requirements` * — * `pnr_operations` via `pnr_operation_acceptance_map`

### 15. Example (fictional)

| Field | Value |
|-------|--------|
| `requirement_id` | `99999999-0001-4000-8000-000000000047` |
| `requirement_code` | `ACT-ALG-SAU` |
| `requirement_name` | `Протокол проверки алгоритмов САУ` |

Second example type: `ACT-INDIV-EQ` / `Акт индивидуального испытания оборудования`.

---

## 10. `pnr_operation_acceptance_map`

### 1. Purpose

Which catalog operations contribute to which acceptance requirement **types**.  
**Does not** mean the document exists, is signed, or is accepted.

### 2. Table grain

One row = one operation ↔ one requirement type, with a role.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `map_id` | `uuid` | Req | |
| `operation_id` | `uuid` | Req | |
| `requirement_id` | `uuid` | Req | |
| `requirement_role` | `text` | Req | `REQUIRED` / `SUPPORTING` / `CONDITIONAL` |
| `notes` | `text` | Null | Condition text if `CONDITIONAL` |
| `created_at` | `timestamptz` | Req | |

No `satisfied boolean`. That would fake acceptance status.

### 6. PK

`map_id`

### 7. FK

`operation_id` → `pnr_operations.operation_id`  
`requirement_id` → `pnr_acceptance_requirements.requirement_id`

### 8. Business key

`(operation_id, requirement_id)`

### 9. UNIQUE

`(operation_id, requirement_id)`

### 10. CHECK

- `requirement_role in ('REQUIRED', 'SUPPORTING', 'CONDITIONAL')`

### 11. Indexes

- PK
- unique `(operation_id, requirement_id)`
- `requirement_id`

### 12. Lifecycle / mutability

Association catalog. Not an acceptance journal.

### 13. Source of truth

PNR mapping of expected evidence types.

### 14. Relationships / cardinality

N:M.

### 15. Example (fictional)

PNR-AUT-003 ↔ `ACT-ALG-SAU` with `requirement_role = REQUIRED`.

This does **not** create Протокол №47.

---

## 11. `pnr_execution_events`

### 1. Purpose

Append-oriented commissioning attempt journal. Layer 4 — *what happened?*

### 2. Table grain

One row = one attempt of one operation (catalogued XOR unmapped) on one object at one time/context with one result.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `event_id` | `uuid` | Req | Identity of the attempt |
| `object_id` | `uuid` | Req | Commissioning object (implies system) |
| `operation_id` | `uuid` | Null | Catalog operation; **XOR** with unmapped fields |
| `unmapped_operation_code` | `text` | Null | Optional code as reported in the field |
| `unmapped_operation_name` | `text` | Null | Required when unmapped — what was attempted |
| `occurred_on` | `date` | Req | Calendar date of the attempt (reporting grain) |
| `occurred_at` | `timestamptz` | Null | Optional precise time |
| `result` | `text` | Req | `PASS` / `FAIL` / `PARTIAL` / `BLOCKED` |
| `result_reason` | `text` | Null | e.g. temperature sensor signal absent |
| `recorded_at` | `timestamptz` | Req | Insert time |
| `recorded_by_label` | `text` | Null | Free-text actor label only — **not** a Person FK |

No `system_id` denormalized (derived via object).  
No `is_current`.  
No `completion_pct`.  
No overwrite of `result`.

### 6. PK

`event_id`

### 7. FK

`object_id` → `pnr_objects.object_id`  
`operation_id` → `pnr_operations.operation_id` (nullable)

**Exactly-one (XOR) rule — justified:** the attempt has a single answer to “which operation was performed?”. Storing both a catalog id and an unmapped description would create two truths. Storing neither would be a fact without a verb. A fake catalog row `UNKNOWN` is rejected by ADR-PNR-001.

Classification of unmapped work onto a later catalog operation is **not** done by mutating this row. That process is deferred (**UNRESOLVED** mechanism).

### 8. Business key

There is **no** natural unique key such as `(object_id, operation_id, occurred_on)`. The same operation may be attempted twice on the same day. Surrogate `event_id` is the identity.

### 9. UNIQUE

PK only. Do **not** unique `(object, operation, date)`.

### 10. CHECK — XOR and vocabulary

Enforceable CHECK (conceptual):

- `result in ('PASS', 'FAIL', 'PARTIAL', 'BLOCKED')`
- exactly one of:
  - **catalogued:** `operation_id is not null` AND `unmapped_operation_name is null` AND `unmapped_operation_code is null`
  - **unmapped:** `operation_id is null` AND `unmapped_operation_name is not null` AND `length(trim(unmapped_operation_name)) > 0`
- unmapped code, if present, only allowed in the unmapped branch (already implied)

Optional `occurred_at` must not contradict `occurred_on` if both present (application-level if timezone conversion is non-trivial). **UNRESOLVED:** timezone policy for `occurred_at` vs `occurred_on`.

### 11. Indexes

- PK
- `object_id`
- `operation_id` (partial, where not null)
- `(object_id, occurred_on)`
- `occurred_on`

### 12. Lifecycle / mutability

**Append-only** for fact fields: `object_id`, `operation_id`, unmapped fields, `occurred_on`, `occurred_at`, `result`, `result_reason`.

A later PASS is a **new row**. FAIL is never updated to PASS.

`recorded_by_label` may be filled at insert; later “who recorded this” correction is **UNRESOLVED** and must not become a stealth rewrite of the attempt.

No delete.

Labor rows may be inserted later against the same `event_id` (event can exist before labor is broken down). That does not mutate the event.

### 13. Source of truth

PNR execution reality. Not `daily_progress_*`.

### 14. Relationships / cardinality

`pnr_objects` 1 — * events  
`pnr_operations` 0..1 — * events  
events 1 — * `pnr_event_labor`

System context: `event → object → eos_systems`. Application invariant: if `operation_id` is set, that operation’s work scope must belong to the **same** `system_id` as the object. Enforce at application level in v0.1 (cross-table CHECK would require a trigger). **UNRESOLVED:** trigger vs application enforcement.

### 15. Example (fictional)

Attempt 1:

| Field | Value |
|-------|--------|
| `event_id` | `aaaaaaa1-0001-4000-8000-000000000001` |
| `object_id` | Automation Panel P1 |
| `operation_id` | PNR-AUT-003 |
| `occurred_on` | `2026-09-08` |
| `result` | `FAIL` |
| `result_reason` | `temperature sensor signal absent` |

Attempt 2:

| Field | Value |
|-------|--------|
| `event_id` | `aaaaaaa1-0001-4000-8000-000000000002` |
| `object_id` | Automation Panel P1 |
| `operation_id` | PNR-AUT-003 |
| `occurred_on` | `2026-09-09` |
| `result` | `PASS` |
| `result_reason` | `null` |

Both rows remain. The FAIL row is unchanged.

Unmapped example (not part of P1 happy path): `operation_id = null`, `unmapped_operation_name = 'Прозвонка нестандартной цепи'`.

---

## 12. `pnr_event_labor`

### 1. Purpose

Labor components of one execution event. Layer 4 — *how much labor, and why?*

### 2. Table grain

One row = one labor-cause component of one event.  
v0.1: at most one row per `(event_id, labor_category)`.

### 3–5. Proposed fields

| Field | Type | Null | Meaning |
|-------|------|------|---------|
| `event_labor_id` | `uuid` | Req | |
| `event_id` | `uuid` | Req | Parent attempt |
| `labor_category` | `text` | Req | `PRODUCTIVE` / `REWORK` / `DEFECT_CORRECTION` / `CONSTRAINT_LOSS` |
| `person_hours` | `numeric` | Req | Person-hours for this cause |
| `notes` | `text` | Null | |
| `recorded_at` | `timestamptz` | Req | |

Omitted: `people_count`, `duration_hours`, `crew_id`, person FK, cost. Cost can be analyzed later against a baseline rate; mixing rate into actuals in v0.1 would conflate layers 3 and 4.

### 6. PK

`event_labor_id`

### 7. FK

`event_id` → `pnr_execution_events.event_id`

### 8. Business key

`(event_id, labor_category)`

### 9. UNIQUE

`(event_id, labor_category)`

If two productive slices must be distinguished later, that is a new grain (**UNRESOLVED**); v0.1 sums them into one `PRODUCTIVE` row.

### 10. CHECK

- `labor_category in ('PRODUCTIVE', 'REWORK', 'DEFECT_CORRECTION', 'CONSTRAINT_LOSS')`
- `person_hours > 0`

Zero-hour categories are represented by **absence of a row**, not a zero row.

### 11. Indexes

- PK
- unique `(event_id, labor_category)`
- `event_id`

### 12. Lifecycle / mutability

Insert-only for a given `(event_id, labor_category)`. Do not update `person_hours` or `labor_category` in place.

Correction policy if a wrong number was entered: **UNRESOLVED** (compensating row would break the unique category key; a full event-labor rewrite would be destructive). Until resolved, treat inserts as careful operational writes; do not add an `is_correction` attribute in v0.1 (over-modeling).

Deleting labor rows is forbidden once recorded. Adding a missing category to an existing event is allowed (event without labor is valid).

### 13. Source of truth

PNR actual labor. Not baseline. Not GESN. Not BOQ.

### 14. Relationships / cardinality

`pnr_execution_events` 1 — 0..4 `pnr_event_labor` in v0.1 (one per category).

Total event labor = `sum(person_hours)`. That sum is **not** physical completion.

### 15. Example (fictional)

Parent: FAIL event `aaaaaaa1-…0001` (PNR-AUT-003, BLOCKED/FAIL with sensor absent).

| `labor_category` | `person_hours` |
|------------------|----------------|
| `PRODUCTIVE` | `2` |
| `CONSTRAINT_LOSS` | `6` |

One event, two labor rows, total 8 person-hours. The PASS event may have its own labor rows; it is not an update of the FAIL event.

---

# Cross-entity invariants

| # | Invariant | Enforcement |
|---|-----------|-------------|
| 1 | Execution event belongs to one object, hence one system | `object_id` NOT NULL FK; system derived |
| 2 | Object belongs to one system | `pnr_objects.system_id` NOT NULL FK; immutable |
| 3 | Catalog operation belongs to one work scope | `pnr_operations.work_scope_id` NOT NULL FK; immutable |
| 4 | Event operation is catalogued XOR unmapped | CHECK on `pnr_execution_events` |
| 5 | Event result ∈ {PASS, FAIL, PARTIAL, BLOCKED} | CHECK |
| 6 | Event labor belongs to one event | `event_id` NOT NULL FK |
| 7 | Labor category vocabulary | CHECK |
| 8 | Labor hours cannot be negative; v0.1 requires `person_hours > 0` | CHECK |
| 9 | `people_count` / duration | **Omitted** in v0.1. Labor is person-hours only. |
| 10 | Baseline hours/rates/amounts cannot be negative; approved triple consistent | CHECK |
| 11 | No destructive overwrite of attempt history | Append-only lifecycle on events; no unique-on-latest-result |
| 12 | No destructive overwrite of approved baseline history | Status machine + new version rows |
| 13 | No automatic normative-hour allocation | No allocated-hours columns; mapping-only tables |
| 14 | Commercial mapping N:M | Unique `(operation_id, boq_code)` allows many maps per side |
| 15 | Normative mapping N:M | Unique `(operation_id, normative_item_id)` |
| 16 | Acceptance mapping ≠ actual acceptance | No instance table; no `satisfied` flag |
| 17 | System identity stable if display name changes | `system_id` + `system_code` immutable; `display_name` mutable |
| 18 | Event object and catalog operation share a system | Application-level in v0.1 (same `system_id` via object vs work_scope) |
| 19 | Unmapped events do not require a catalog row | XOR; no `UNKNOWN` operation |
| 20 | SMR fact tables are not written | Documented non-goal; no FKs to `daily_progress_*` |

---

# P1 conceptual sanity walkthrough

**No database writes. Fictional IDs only.**

## Setup

1. `eos_systems`: `P1` / «Система P1».
2. Objects: Supply Unit P1, VFD P1, Fire Damper P1-01, Automation Panel P1 — all `system_id = P1`.
3. Work scope: `AUT` / «Automation / Algorithms» on P1.
4. Operation: `PNR-AUT-003` / «Проверка алгоритма» in that work scope.
5. Baseline v1 APPROVED on P1: 800 h × 1574.30 = 1,259,440 RUB excl. VAT. This baseline is a **system** fact. It is **not** assigned to PNR-AUT-003. It is **not** split across objects.
6. Normative item: GESNp03-01-060-04 / 1 installation / 37.44 h / no-load commissioning. Mapped to PNR-AUT-003 as `SHARED` (or `PARTIAL`) **without** moving 37.44 onto the operation.
7. Commercial map: PNR-AUT-003 ↔ an existing `boq_code` in `boq_master_api` (logical; no FK).
8. Acceptance map: PNR-AUT-003 ↔ requirement type «Протокол проверки алгоритмов САУ», role `REQUIRED`. No signed protocol row exists.

Objects Supply Unit / VFD / Fire Damper are in the model to show that P1 has many commissioning objects. The attempts below are on **Automation Panel P1**. Other objects have zero events in this walkthrough.

## Attempt 1 — remains visible

| | |
|--|--|
| Object | Automation Panel P1 |
| Operation | PNR-AUT-003 |
| Date | 2026-09-08 |
| Result | `FAIL` (walkthrough uses FAIL as specified; `BLOCKED` is the sibling vocabulary member for constraint-stopped work — see note) |
| Reason | temperature sensor signal absent |
| Labor | PRODUCTIVE 2 h; CONSTRAINT_LOSS 6 h |
| Event count | 1 event, 2 labor rows |

Note: the prompt’s narrative uses FAIL for attempt 1 and also describes a BLOCKED labor example. v0.1 result vocabulary includes both `FAIL` and `BLOCKED`. This walkthrough records attempt 1 as **`FAIL`** as specified for the two-attempt history, with labor still split PRODUCTIVE / CONSTRAINT_LOSS. Choosing `BLOCKED` instead of `FAIL` would be an equally valid single event; it would **not** require a second event. Do not duplicate the event to store both words.

## Attempt 2 — does not overwrite attempt 1

| | |
|--|--|
| Object | Automation Panel P1 |
| Operation | PNR-AUT-003 |
| Date | 2026-09-09 |
| Result | `PASS` |
| Event | **new** `event_id` |
| Attempt 1 FAIL row | unchanged |

Current operational reading “PNR-AUT-003 on Automation Panel P1 is PASS” is a **projection** (latest `occurred_on` / `recorded_at`). It is not stored as a mutable status.

## Same operation — maps, not allocations

```
PNR-AUT-003
  → boq_master_api.boq_code (commercial; N:M; no hours copied)
  → pnr_normative_items GESNp03-01-060-04 (37.44 h stay on the item)
  → acceptance requirement type «Протокол проверки алгоритмов САУ»
  → (system P1) customer-agreed baseline 800 h   ← NOT via the operation
```

**Do not** conclude that PNR-AUT-003 “owns” 800 h or 37.44 h.

## Analytical questions this model **can** answer (once data exist)

Join path: labor → event → object → system; optional join event → operation → maps.

For system P1:

- actual total labor = sum of `person_hours` for events whose object.system is P1
- productive / rework / defect_correction / constraint_loss = the same sum filtered by `labor_category`
- FAIL / PASS / PARTIAL / BLOCKED attempt counts = count of events by `result`
- actual labor by operation = sum hours grouped by `operation_id` (unmapped events group under unmapped name, not a fake catalog id)
- actual labor by normative mapping = sum hours of events whose catalog operation maps to a given `normative_item_id`  
  **Caveat:** this is **associated** actual labor, not a share of 37.44. Unmapped events are excluded from that join unless later classified.
- actual labor vs customer-agreed system baseline = `sum(actual hours on P1)` compared to the **currently approved** P1 baseline (800 h in the example), and separately compared to superseded versions  
  This ratio is **labor consumption**, never physical completion, never acceptance.

## Questions v0.1 **cannot** yet answer

- What measured value was recorded (no `pnr_measurements`)?
- What photo/file/protocol file proves the PASS (no `pnr_evidence`)?
- What defect object exists independently of a FAIL reason string (no `pnr_defects`)?
- What constraint object blocked the work (reason text only; no `pnr_constraints`)?
- What is the physical state of P1 / of Supply Unit P1 (no state engine)?
- Does «Протокол №47» exist, who signed it, where is the file (no acceptance instances)?
- Is the REQUIRED acceptance requirement satisfied?
- Who (Person master) spent the 8 hours?
- Which Facility / Project master does P1 belong to?
- How should 37.44 normative hours or 800 baseline hours be **allocated** to PNR-AUT-003? — **forbidden**, not missing.
- What is SMR daily progress for P1 in this journal? — wrong domain.

**P1 SANITY WALKTHROUGH: PASS** (conceptual; no writes).

---

# Design quality gate

| Check | Result |
|-------|--------|
| Unnecessary duplication | `system_id` not copied onto operations or events; derived. Baseline not copied onto operations. |
| Hidden coupling to SMR | No FK to `daily_progress_*`. Legacy label on `eos_systems` is optional correlation only. |
| Hidden coupling to Agent Runtime | None. No run_id / agent_id. |
| Free-text identity | System identity is `system_id` + `system_code`. SMR text remains outside. `recorded_by_label` is explicitly non-identity. `object_kind` left open — flagged UNRESOLVED. |
| Ambiguous grains | Event grain stated; baselines are system-version; maps are associations; BOQ map uniqueness flagged UNRESOLVED vs composite grain. |
| Destructive history | Events append-only; baselines versioned; FAIL/PASS are two rows. |
| Impossible FK assumptions | No FK to `boq_master_api`. No Person/Facility/Project FKs. |
| BOQ cloning | Rejected; map stores codes/qualifiers only. |
| GESN/BOQ conflation | Separate tables and layers. |
| Baseline/actual conflation | Separate tables; no shared hours column. |
| Labor/completion conflation | No completion percentage column. |
| Over-engineering | Omitted: people_count, evidence, measurements, allocation %, acceptance instances, operation classification table, system_id denorm. Coverage_kind kept to three values. |

**DESIGN QUALITY GATE: PASS**, with UNRESOLVED items listed rather than silently decided.

---

# Unresolved (do not expand scope to “fix”)

1. Live PostgreSQL PK/UNIQUE of `boq_master_api` (no `CREATE TABLE` in repo) — FK not enforced.
2. Whether commercial map uniqueness must include facility/discipline/project because `boq_code` is not unique.
3. Whether `legacy_system_label` should be unique.
4. `object_kind` controlled vocabulary vs free text.
5. Precise unique key of `pnr_normative_items` pending real estimate documents; `NULLS NOT DISTINCT` availability.
6. Normative item revision lifecycle vs simple `is_active`.
7. Baseline `effective_to` inclusive vs exclusive; overlapping approved periods.
8. Timezone consistency `occurred_on` vs `occurred_at`.
9. Cross-table invariant “event.object.system = operation.work_scope.system” — trigger vs application.
10. Mechanism to classify an unmapped event onto a later catalog operation without mutating the attempt.
11. Correction of mistaken `pnr_event_labor` hours under UNIQUE(category).
12. RLS policies for new tables.
13. Whether a later live `\d` of `boq_master_api` reveals a key that would allow a real FK — revisit then, do not invent now.
14. `people_count` / duration reconstruction of person-hours.
15. Whether `FAIL` vs `BLOCKED` operational guidance needs a later playbook (vocabulary is closed; usage nuance is not).

---

# Deferred (named only)

`pnr_measurements`, `pnr_evidence`, `pnr_defects`, `pnr_constraints`, physical state engine, signed acceptance instances (`pnr_acceptance_records` / `pnr_acceptance_instances`), Facility master, Person master, Project master, SMR migration onto `eos_systems`, Agent Runtime, Commissioning Agent, QR/NFC, robot/sensor integration.

---

# Document control

| Item | Value |
|------|--------|
| Authorizes SQL | No |
| Authorizes CREATE TABLE | No |
| Authorizes Supabase change | No |
| Authorizes product data | No |
| Entity count | **12** (+ existing `boq_master_api` as external reference, not redesigned) |
| Next | Review this schema design before SQL implementation |
