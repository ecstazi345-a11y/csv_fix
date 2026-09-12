# PNR Dataset Progress — Commissioning Execution Reality

**Purpose:** durable engineering memory for the PNR Dataset program. Not a chat log.

Checkpoints are **append-only**. Do not rewrite previous entries.

**Program:** PNR Dataset / Commissioning Execution Reality  
**Worktree:** `C:/csv_fix_pnr`  
**Branch:** `wip/pnr-dataset-foundation`  
**Design law:** ADR-PNR-001, schema v0.1 design, MVP-0 plan (those files remain architecture/plan; they are not this progress log)

This file is the authoritative PNR **implementation progress** checkpoint. It does not authorize SQL, seed, or product writes by itself.

## Current snapshot (not a checkpoint)

- **FIELD-1A** structured event contract — **DONE / LIVE**
- **FIELD-1B** structured write RPC — **DONE / LIVE PROVEN**
- **FIELD-1C** Russian field form (Page 60) — **DONE / TESTED**
- **PNR navigation** — **DONE**
- **FIELD-1D.1C** M:N work-scope ↔ operation bridge — **DONE / LIVE PROVEN**
- **FIELD-1D.1D** event work-scope context — **DONE / LIVE MIGRATION APPLIED / LIVE WRITE PROVEN**
- **FIELD-1D.1E** M:N operation read path / picker — **DONE / LIVE CODE PATH / COMMITTED / PUSHED**
- **FIELD-1D as a whole** — **NOT COMPLETE** (professional П-1 content layer remains)
- **NEXT:** Professional П-1 content layer (review/freeze before any seed)
- **Live execution events:** 4 (3 historical/pre-FIELD-1D.1D + 1 FIELD-1D.1D technical proof)
- **Code HEAD:** `499358637773876070a6d93967202941d5a00992`
- **Agent Runtime:** separate workstream; not touched by FIELD-1D.1E

Historical checkpoints below are append-only and are **not** rewritten.

---

============================================================
CHECKPOINT — 2026-09-12 — FIELD-1D.1D — EVENT SCOPE CONTEXT
============================================================

PROGRAM:
PNR Dataset / Commissioning Execution Reality

CURRENT INCREMENT:
FIELD-1D.1D — persist exact Work Scope context on new structured execution events

STATUS:
DONE  
LIVE MIGRATION APPLIED  
POST-MIGRATION LIVE PROOF = PASS  
ONE-EVENT LIVE WRITE PROOF = PASS  
CODE COMMITTED AND PUSHED

------------------------------------------------------------
ARCHITECTURAL PURPOSE
------------------------------------------------------------

Work Scope = professional context.  
Operation = reusable canonical professional action.  
Execution Event = append-only attempt/fact.

After FIELD-1D.1C, one canonical operation may belong to many work scopes via `pnr_work_scope_operations`. `operation_id` alone cannot reconstruct the professional section under which an attempt was performed.

FIELD-1D.1D persists that missing context on **new** structured events:

```
SYSTEM
  → PHYSICAL OBJECT
    → FUNCTIONAL POSITION
      → WORK SCOPE
        → OPERATION
          → EXECUTION EVENT
```

The important new persisted relationship is:

`work_scope_id` + `operation_id`

One (work scope, operation, object) may have many append-only attempts. Historical truth is not rewritten.

------------------------------------------------------------
IMPLEMENTATION
------------------------------------------------------------

`public.pnr_execution_events.work_scope_id` = `uuid NULL`

Rules:

- historical events are not backfilled;
- legacy / pre-FIELD-1D.1D events may retain `work_scope_id = NULL`;
- new structured events require `work_scope_id`;
- mapped operation requires an active Work Scope;
- mapped operation requires an **active** membership in `pnr_work_scope_operations`;
- composite identity `(work_scope_id, operation_id)` is enforced toward the bridge;
- unmapped operation still requires a valid Work Scope and does **not** require bridge membership;
- retry of an event with known `work_scope_id` must preserve that scope;
- retry of a historical event with `NULL` work_scope_id must supply its own valid current scope without rewriting the prior row;
- legacy `create_execution_event` is unchanged and may still write `work_scope_id = NULL`;
- no table-level CHECK tying `work_scope_id` to `execution_status`;
- `MATCH SIMPLE` is intentional (historical NULL + mapped `operation_id`, and unmapped `operation_id` NULL, remain legal);
- `is_active` membership is enforced by the structured RPC, not by the composite FK.

Page 60:

- persists the selected `work_scope_id`;
- includes `work_scope_id` in the save fingerprint;
- refuses structured save without a selected scope;
- canonical and unmapped paths both persist scope;
- operation picker still uses the **legacy owner** read path `pnr_operations.work_scope_id`;
- M:N picker/read path is **NOT IMPLEMENTED**.

Classification:

| Item | Status |
|------|--------|
| Nullable event `work_scope_id` | LIVE PROVEN |
| New structured write requires scope | LIVE PROVEN |
| Mapped pair persisted (`work_scope_id` + `operation_id`) | LIVE PROVEN |
| Historical rows remain `NULL` (no backfill) | LIVE PROVEN |
| Simple FK `work_scope_id` → `pnr_work_scopes` | LIVE PROVEN (OpenAPI) |
| Composite FK `(work_scope_id, operation_id)` → bridge | STATIC CONTRACT PROVEN |
| MATCH SIMPLE | STATIC CONTRACT PROVEN |
| Index `idx_pnr_execution_events_work_scope_id` | STATIC CONTRACT PROVEN |
| RPC EXECUTE grants / `security_definer` | STATIC CONTRACT PROVEN |
| M:N operation picker | NOT IMPLEMENTED |

Do not upgrade STATIC CONTRACT PROVEN items to LIVE PROVEN. PostgREST/OpenAPI did not authoritatively expose those constraint semantics.

------------------------------------------------------------
LIVE MIGRATION PROOF
------------------------------------------------------------

`FIELD_1D_1D_POST_MIGRATION_PROOF` = **PASS**

Migration file applied once in Supabase SQL Editor:

`sql/pnr_field_1d_1d_event_scope_context.sql`

At post-migration proof time (read-only, before the technical write):

- `LIVE_EVENT_COUNT` = 3
- all three historical events remained present
- their `work_scope_id` values remained `NULL`
- `AUT_ALGORITHMS` active = YES
- `PNR-AUT-003` active = YES
- bridge membership = exactly 1 and active
- structured RPC version = **FIELD_1D_1D_LIVE**
- simple FK = LIVE PROVEN
- composite FK / MATCH SIMPLE / index / RPC security = STATIC CONTRACT PROVEN

------------------------------------------------------------
ONE-EVENT LIVE WRITE PROOF
------------------------------------------------------------

`FIELD_1D_1D_ONE_EVENT_LIVE_PROOF` = **PASS**

This event is a **TECHNICAL PROOF EVENT**. It is **not** a production PNR fact. Do not describe it as production work, acceptance, or commercial result.

| Field | Value |
|-------|--------|
| `event_id` | `0fcb7de1-eade-46a7-a024-4d6afbd8fb0f` |
| `system_id` | `4ab41ec1-f88e-4514-a07d-6c72f5ba212f` |
| `object_id` | `1796501a-44a6-4d3a-855b-7ea16b9fdc2c` |
| `functional_position_id` | `2a94d792-a26a-45f7-baa8-9887c97b39bb` |
| `work_scope_id` | `51beb0ed-c651-41d1-9843-c5d9b8b222eb` |
| `operation_id` | `3d564073-778f-48ba-a42d-4bcb5641405f` |
| `source` | `FIELD_1D_1D_LIVE_PROOF` |
| `result` | `PASS` |
| `execution_status` | `COMPLETED` |
| `evaluation_status` | `CONFORMS` |
| `people_count` | 1 |
| `duration_hours` | 0 |
| `labor_hours` | 0 |
| measurements | 0 |
| blocked_details | 0 |
| partial_details | 0 |

Write path: `create_structured_execution_event` (exactly one call). Not Page 60. Not `create_execution_event`. Not direct INSERT.

Event count: BEFORE = 3, AFTER = 4.

Historical events preserved (still `work_scope_id = NULL`):

- `41bd0c13-7eaa-43bd-a7e5-23bb74e58ae9`
- `51f7935e-785a-4f66-9877-af19f821b772`
- `7e72c8bd-7b3f-413d-a5f9-dd799b2b1acb`

Therefore:

- WORK SCOPE CONTEXT PERSISTENCE = **LIVE PROVEN**
- STRUCTURED WRITE PATH = **LIVE PROVEN**
- APPEND-ONLY HISTORY = **PRESERVED**
- HISTORICAL IMMUTABILITY = **PROVEN**

Do not delete or rewrite the proof event. It is append-only technical history.

------------------------------------------------------------
CODE CHECKPOINT
------------------------------------------------------------

CODE COMMIT: `7376512a216d157aefd7f0cc7149ccf1c968437e`  
MESSAGE: `feat(pnr): persist event work scope context`  
PUSH: SUCCESS  
LOCAL == UPSTREAM: YES  
WORKTREE at push: CLEAN

Files in that commit (6):

- `pages/60_ПНР_Фиксация_факта.py`
- `services/pnr_service.py`
- `sql/pnr_field_1d_1d_event_scope_context.sql`
- `tests/test_page60_pnr_fact_form.py`
- `tests/test_pnr_field_1b_write.py`
- `tests/test_pnr_field_1d_1d_sql_contract.py`

------------------------------------------------------------
CURRENT DATASET STATE
------------------------------------------------------------

Live `pnr_execution_events` = **4**

- 3 historical / pre-FIELD-1D.1D events (`work_scope_id` NULL)
- 1 FIELD-1D.1D technical proof event (`source = FIELD_1D_1D_LIVE_PROOF`)

------------------------------------------------------------
BOUNDARIES / NOT DONE
------------------------------------------------------------

FIELD-1D.1D did **not**:

- implement the M:N operation picker / read path;
- stop Page 60 from reading operations through legacy `pnr_operations.work_scope_id`;
- seed 9 professional P-1 work scopes;
- freeze a canonical 47-operation Russian manifest in the database;
- materialize the full П-1 physical model;
- materialize П-1.1 / П-1.2;
- populate asset instances / endpoints / connections;
- create a new **production** PNR event;
- touch Agent Runtime.

FIELD-1D as a whole is **not** complete.

------------------------------------------------------------
NEXT INCREMENT (NOT IMPLEMENTED NOW)
------------------------------------------------------------

**NEXT:** M:N OPERATION READ PATH / PICKER

Purpose: Page 60 must stop treating `pnr_operations.work_scope_id` as the authoritative source for selectable operation membership.

The selectable operation set for a Work Scope must be resolved through `pnr_work_scope_operations`. The bridge becomes the authoritative membership relation.

The legacy owner column remains compatibility data until separately retired.

This checkpoint only records NEXT. It does not implement it.

---

============================================================
CHECKPOINT — 2026-09-12 — FIELD-1D.1E — M:N OPERATION READ PATH / PICKER
============================================================

PROGRAM:
PNR Dataset / Commissioning Execution Reality

CURRENT INCREMENT:
FIELD-1D.1E — M:N Operation Read Path / Picker

STATUS:
DONE
LIVE CODE PATH
COMMITTED AND PUSHED

------------------------------------------------------------
ARCHITECTURAL PURPOSE
------------------------------------------------------------

Page 60 canonical operation picker now uses `pnr_work_scope_operations`
as the authoritative Work Scope ↔ Operation membership relation instead of
`pnr_operations.work_scope_id`.

Architecture law:

- `pnr_operations` = canonical operation identity / catalog data;
- `pnr_work_scope_operations` = M:N membership of canonical operations in
  professional Work Scopes;
- `pnr_operations.work_scope_id` remains legacy compatibility ownership and
  is **not** membership authority for Page 60;
- one canonical operation may belong to multiple Work Scopes;
- Page 61 remains on the legacy reader for compatibility at this increment.

------------------------------------------------------------
READ PATH
------------------------------------------------------------

```
Page 60
  → selected work_scope_id
    → list_active_operations_for_work_scope
      → active pnr_work_scope_operations memberships
        → referenced active pnr_operations
          → Python composition
            → bridge sequence_no ordering
              → operation picker
```

Reader behavior:

- 1 DB read when no active memberships exist;
- otherwise 2 DB reads;
- no per-operation N+1 query;
- no PostgREST embedded relationship dependency;
- inactive membership excluded;
- inactive catalog operation excluded;
- legacy owner mismatch does not block an active M:N membership;
- non-null bridge `sequence_no` ordered first, ascending;
- NULL `sequence_no` ordered last with deterministic fallback
  (`operation_code`, then `operation_id`);
- unresolved catalog operation membership is skipped safely.

Classification:

| Item | Status |
|------|--------|
| Page 60 picker membership via `pnr_work_scope_operations` | LIVE CODE PATH |
| Inactive membership excluded | SYNTHETIC TEST PROVEN |
| Inactive catalog operation excluded | SYNTHETIC TEST PROVEN |
| Cross-scope M:N (owner A, member of B) | SYNTHETIC TEST PROVEN |
| Bridge `sequence_no` ordering / NULL last | SYNTHETIC TEST PROVEN |
| Legacy `list_active_operations` owner reader | PRESERVED |
| Page 61 | UNCHANGED (legacy reader) |
| Live catalog cross-scope proof | NOT AVAILABLE (no multi-scope seed yet) |

Do not describe synthetic test proofs as live production catalog proof.

------------------------------------------------------------
WRITE LAW
------------------------------------------------------------

FIELD-1D.1E changes the **read path only**.

Unchanged:

- `create_structured_execution_event`;
- FIELD-1D.1D structured RPC;
- SQL schema;
- event `work_scope_id` persistence;
- composite Work Scope + Operation validation;
- unmapped operation path;
- historical events;
- append-only event law.

------------------------------------------------------------
DATABASE
------------------------------------------------------------

SQL migration: **NONE**
Supabase touched during implementation: **NO**
PNR events created: **0**
LIVE DATA CHANGED: **NO**

Live `pnr_execution_events` remains **4**.

------------------------------------------------------------
CODE CHECKPOINT
------------------------------------------------------------

CODE COMMIT: `499358637773876070a6d93967202941d5a00992`
MESSAGE: `feat(pnr): use m2m operation membership in field picker`
PUSH: SUCCESS
LOCAL == UPSTREAM: YES
WORKTREE at push: CLEAN

Files in that commit (5):

- `pages/60_ПНР_Фиксация_факта.py`
- `services/pnr_service.py`
- `tests/test_page60_pnr_fact_form.py`
- `tests/test_pnr_field_1b_write.py`
- `tests/test_pnr_field_1d_1e_mn_picker.py`

NON-SCOPE FILES: NONE
ARCHITECTURE DRIFT: NO

------------------------------------------------------------
TEST EVIDENCE
------------------------------------------------------------

PNR regression: **179 passed**
`py_compile`: PASS
`git diff --check`: PASS

Synthetic M:N proof includes:

- cross-scope membership: an operation legacy-owned by Scope A is selectable
  for Scope B when Scope B has an active bridge membership;
- inactive membership exclusion;
- inactive catalog operation exclusion;
- bridge sequence ordering;
- NULL sequence ordering;
- unmapped regression;
- `work_scope_id` persistence regression;
- `operation_id` persistence regression;
- legacy reader preservation;
- FIELD-1D.1D write-path regression.

Current live catalog data cannot independently prove cross-scope M:N because
the professional multi-scope seed does not yet exist. Cross-scope M:N behavior
is therefore proven synthetically in tests.

------------------------------------------------------------
BOUNDARIES / NOT DONE
------------------------------------------------------------

FIELD-1D.1E did **not**:

- seed 9 professional П-1 Work Scopes;
- review/freeze a canonical Russian operation manifest in the database;
- claim the reconstructed Russian 47-operation list is already
  authoritatively frozen (it remains **PROPOSED** until human review/freeze);
- seed P-1.1 / P-1.2 physical decomposition;
- create a new live production PNR event;
- change Page 61 off the legacy reader;
- create a PNR Agent;
- touch Agent Runtime.

FIELD-1D as a whole is **not** complete.

FIELD-1D.1E completion law: Page 60 now reads canonical operation membership
through the M:N bridge while the frozen structured write contract remains
unchanged.

------------------------------------------------------------
NEXT INCREMENT (NOT IMPLEMENTED NOW)
------------------------------------------------------------

**NEXT:** Professional П-1 content layer.

Before any database seed:

1. review and freeze the professional Work Scope structure for П-1;
2. review and freeze the canonical Russian operation manifest;
3. define which canonical operations belong to which Work Scopes through
   `pnr_work_scope_operations`;
4. preserve separation between physical operations, measurements, test runs,
   evidence, documents, signatures, defects, and constraints;
5. only after human approval prepare the П-1 seed/migration plan.

This checkpoint only records NEXT. It does not implement it.
