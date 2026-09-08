# ADR-PNR-001 — Shared System Identity & PNR Domain Boundary

**Identifier:** ADR-PNR-001  
**Title:** Shared physical system identity and PNR commissioning-reality domain boundary  
**Status:** ACCEPTED — architecture law; does not authorize schema creation or product change  
**Date:** 2026-09-08  
**Refined:** 2026-09-08 — acceptance semantics; separate normative layer; four truth layers; v0.1 entity list 01–12  
**Worktree:** `C:/csv_fix_pnr`  
**Branch context:** `wip/pnr-dataset-foundation`  
**Scope of this document:** architecture decisions only. No tables, SQL, migrations, product code, or data changes are authorized by this ADR.

This ADR is refined in-place. Previously accepted laws remain in force unless a subsection below explicitly **supersedes** them.

---

## 1. Status

This ADR is **ACCEPTED** as Execution OS law for the PNR Dataset / Commissioning Execution Reality contour.

Acceptance means:

- subsequent PNR schema design, data modeling, and product work must not violate the laws recorded here;
- this ADR is **not** an implementation permit;
- field-level schema design may be refined later without violating these laws;
- Agent Runtime remains a separate workstream and is out of scope.

Two refinements are incorporated and supersede earlier v0.1 naming / layering only:

1. **Acceptance semantics** — v0.1 models acceptance *requirement types*, not signed document instances.
2. **Normative layer** — GESN / estimate truth is stored in `pnr_normative_items`, distinct from `boq_master_api`.

Rejected alternatives are recorded in section 4. They remain rejected until a later ADR explicitly supersedes this one.

---

## 2. Context

Execution OS already operates as a production system for construction execution (primarily SMR daily progress, monthly planning / admission / passport, and commercial BOQ reference).

A new **subject contour** is now required inside the same product and the same database:

**PNR Dataset / Commissioning Execution Reality**

Purpose:

create a digital model of **actual physical execution of commissioning (пусконаладочные работы)**.

This is:

- a new **domain** inside the existing Execution OS;
- **not** a new product;
- **not** a separate Supabase database;
- **not** Agent Runtime.

The intended future chain is:

```
Physical System
  → Commissioning Object
  → Work Scope
  → Operation
  → Execution Event
  → Labor
  → Measurement / Evidence
  → Physical Result / State
  → Acceptance
  → Commercial Recognition
```

The chain is directional architecture, not an implemented pipeline. Measurement, evidence, physical state, signed acceptance instances, and commercial recognition mechanics beyond mapping are deferred (section 15).

PNR exists because commissioning execution has a different grain, different objects, and different truths from SMR daily progress. Reusing SMR fact tables, monthly planning tables, cloning the BOQ master, or treating BOQ as a GESN master would destroy that distinction.

Four truth layers must remain separate for the life of the domain (section 8):

1. Commercial truth — `boq_master_api` — *за что нам платят?*
2. Normative truth — `pnr_normative_items` — *какая нормативная трудоёмкость в исходной смете / норме?*
3. Agreed labor baseline — `pnr_labor_baselines` — *сколько труда согласовано как плановая трудовая база?*
4. Execution reality — `pnr_execution_events` + `pnr_event_labor` — *что реально произошло и сколько труда реально потребовалось?*

---

## 3. Audit findings

The following findings are recorded as **authoritative for this ADR**. They come from a prior read-only audit of the existing Execution OS. This document does not invent additional database facts, table inventories, or field lists beyond those findings and the explicit refinements above.

| # | Finding | Architectural implication |
|---|---------|---------------------------|
| 1 | There is **no** authoritative `projects` table. | PNR must not assume a shared Project master exists. Project identity, if needed later, is a separate increment. |
| 2 | Facility exists predominantly as **text labels** (`facility` / `facility_building`). | There is no shared Facility master to own. Facility master is deferred. |
| 3 | System exists predominantly as **text labels** (`system` / `system_label`). | Current SMR/product usage of system is label-level, not a registry. `eos_systems` is additive shared identity; labels are not rewritten. |
| 4 | There is **no** unified authoritative `system_id` registry. | `eos_systems` is the intended shared registry. Its minimum viable *contract* is designed in the schema design document. Physical creation remains unauthorized by this ADR. |
| 5 | A Physical Asset / Equipment registry was **not found**. | PNR must not assume equipment identity exists. QR/NFC, robots, sensors are deferred. |
| 6 | An authoritative Person / Employee master was **not found**. | PNR labor facts must not assume a Person master. Shared Person master is deferred. |
| 7 | BOQ commercial master already exists: `boq_master_api`. | This is the operational **commercial** reference. It must not be cloned inside PNR. It is **not** a GESN / estimate master. |
| 8 | Product GESN / Estimate model is currently **absent**. | **Superseded in part:** PNR now owns `pnr_normative_items` as a commissioning-relevant normative source store. This is not a product-wide GESN platform and not a BOQ clone. Hours still must not be invented or auto-allocated. |
| 9 | `daily_progress_*` is **SMR execution fact**. | It must not become the PNR execution journal. |
| 10 | Monthly planning / admission / constraints have their own subject semantics. | They must not be reused as PNR tables. |

No claim is made here about columns, row counts, RLS, or undocumented tables beyond the audit list above. Identity risks for `boq_master_api` are recorded in the schema design document from repository evidence, without inventing a convenience PK.

---

## 4. Decision

Execution OS adopts the following architectural laws for PNR.

### Law 1 — Shared physical system identity

Do **not** create `pnr_systems` as an independent PNR-only registry.

Architectural direction:

`eos_systems` = shared Execution OS physical system identity.

One physical engineering system should be able to receive one durable `system_id` for use by multiple domains:

- SMR
- PNR
- Acceptance
- Commercial
- future agents
- future reality capture

**Physical creation of `eos_systems` is not authorized by this ADR.**  
The follow-on schema design **must** specify the minimum viable contract, because PNR needs stable system identity.

Existing SMR tables are not migrated.  
Existing `system` / `system_label` columns are not modified.  
There is no backfill of product data.  
No Facility master, Project master, or Person master is created.

`eos_systems` must be able to **coexist** with existing text identities without forcing a refactor: PNR uses `system_id`; SMR continues to use text labels; any label stored on `eos_systems` is a correlation aid, not a second master and not a rewrite of SMR.

### Law 2 — PNR owns commissioning reality

PNR domain is responsible for commissioning execution reality and its immediate catalogs/mappings (see section 5).

PNR does **not** own SMR Daily Progress, monthly planning, monthly passport, admission constraints, Agent Runtime, or the general BOQ master.

### Law 3 — Commercial master is not cloned

Do **not** create `pnr_commercial_items` as a copy of the existing BOQ.

Use existing `boq_master_api` as commercial reference.

PNR-specific mapping `pnr_operation_commercial_map` links:

PNR Operation ↔ existing BOQ commercial position.

Relationship is potentially N:M. Do not assume 1 operation = 1 BOQ or 1 BOQ = 1 operation.

`boq_master_api` is not modified in this step.  
`boq_master_api` is **not** a GESN master.

### Law 4 — Four truth layers are distinct

**Supersedes** the earlier “three labor truths” formulation: commercial truth is a fourth layer, and GESN/estimate is no longer an unhosted concept.

The following must never be collapsed into one table or one field meaning:

| Layer | Store | Question |
|-------|--------|----------|
| 1. COMMERCIAL TRUTH | existing `boq_master_api` | За что нам платят? |
| 2. NORMATIVE TRUTH | `pnr_normative_items` | Какая нормативная трудоёмкость содержится в исходной смете / норме? |
| 3. AGREED LABOR BASELINE | `pnr_labor_baselines` | Сколько труда согласовано / принято как плановая трудовая база? |
| 4. EXECUTION REALITY | `pnr_execution_events` + `pnr_event_labor` | Что реально произошло и сколько труда реально потребовалось? |

Actual labor (layer 4) must additionally distinguish at least:

- `PRODUCTIVE`
- `REWORK`
- `DEFECT_CORRECTION`
- `CONSTRAINT_LOSS`

Illustrative design context only (not product data, not to be written to the database by this ADR):

- System P1
- Customer-agreed baseline: 800 person-hours
- Labor rate: 1574.30 RUB/hour excl. VAT
- Labor amount: 1,259,440 RUB excl. VAT
- Normative example: GESNp03-01-060-04 / 1 installation / 37.44 normative person-hours / no-load commissioning

### Law 5 — Normative hours must not be invented

If one BOQ position or one normative/GESN position is linked to several operations, it is **forbidden** to auto-distribute labor by `hours / operation count` or any other arbitrary split.

The normative source stays authoritative as supplied in `pnr_normative_items`.  
`pnr_operation_normative_map` is a relation, not an allocation engine.  
Actual execution events later reveal actual labor distribution.

### Law 6 — Event history is append-oriented

Core PNR fact concept:

> 1 execution event = 1 attempt to perform 1 operation on 1 commissioning object at a defined time/context with a defined result.

Execution result vocabulary v0.1:

`PASS` | `FAIL` | `PARTIAL` | `BLOCKED`

Example: Operation X FAIL on 08.09 and Operation X PASS on 09.09 are **two** facts. FAIL is not overwritten by PASS.

### Law 7 — Event and labor are separate

- Execution Event answers: **what happened?**
- Event Labor answers: **how much labor did it require, and why?**

One execution event may contain several labor components. Multiple labor categories do **not** justify duplicating the physical execution event.

### Law 8 — SMR fact and PNR fact are different

PNR execution events must **not** be written to:

- `daily_progress_raw`
- `daily_progress_active`
- `daily_progress_form_submissions`

SMR Daily Progress and PNR Execution Event have different grain and different subject semantics. Future analytical links may exist; a shared fact table must not.

### Law 9 — Physical completion, labor consumption, and acceptance are different axes

Never treat `actual labor / baseline labor` as physical completion percentage.

Example: 430 / 800 = 53.75% **labor budget consumption**. That is not 53.75% physical commissioning completion.

Distinct axes:

- LABOR CONSUMPTION
- PHYSICAL COMPLETION / STATE
- ACCEPTANCE STATUS

Mapping an operation to an acceptance **requirement type** does **not** prove that a signed acceptance document exists.

### Law 10 — Reality must not be lost because the catalog is incomplete

The future execution model must allow recording a real operation/event even if the operation is not yet in the approved PNR operation catalog.

An UNKNOWN / UNMAPPED operation path is required at **event** level. Do not invent a fake catalog row such as `UNKNOWN`. Reality outranks catalog completeness. Later classification may assign unmapped work to standard / one-off / defect correction / extra work / third-party work / etc.

### Rejected alternatives

| Rejected | Reason |
|----------|--------|
| `pnr_systems` as PNR-only registry | Would fork physical identity from SMR, Acceptance, Commercial, and future agents. |
| Separate Supabase database for PNR | PNR is a domain, not a product. |
| Clone of `boq_master_api` as `pnr_commercial_items` | Duplicates the existing commercial master. |
| Treating `boq_master_api` as a GESN / estimate master | Commercial truth ≠ normative truth. |
| `pnr_acceptance_documents` / `pnr_operation_document_map` as v0.1 names | Ambiguous: v0.1 does not model signed document instances. **Superseded by** `pnr_acceptance_requirements` / `pnr_operation_acceptance_map`. |
| PNR events in `daily_progress_*` | Wrong grain and wrong subject. |
| Reuse of monthly planning / admission / passport / constraint tables as PNR storage | Different semantics. |
| Overwrite FAIL with later PASS | Destroys execution history. |
| One row per labor category as a substitute for the event | Mixes “what happened” with “why labor was spent”. |
| `actual / baseline` as physical % complete | Confuses labor consumption with physical state and acceptance. |
| Auto-split of GESN / normative / BOQ hours across operations | Invents labor. |
| Fake catalog row `UNKNOWN` | Hides unmapped semantics inside the catalog. Prefer event-level unmapped fields. |
| Blocking event capture until the operation catalog is complete | Loses reality. |
| Migrating SMR labels or backfilling product data into `eos_systems` in this increment | Additive coexistence only. |
| Creating Facility / Project / Person masters in this increment | Out of scope. |

---

## 5. Domain ownership

### PNR owns

| Concern | Notes |
|---------|--------|
| Commissioning Objects | Physical/logical objects on which commissioning is performed. |
| Work Scopes | Grouping of commissioning work against a system. |
| Operations | Approved operation catalog. Unmapped path lives on the **event**, not as a fake catalog row. |
| Execution Events | Append-oriented commissioning attempts (Laws 6–8). |
| Event Labor | Labor components of an event, with cause categories (Laws 4, 7). |
| PNR Labor Baselines | Customer-agreed / contractual baseline (layer 3), versioned. Not GESN and not actual. |
| Normative items | `pnr_normative_items` — commissioning-relevant estimate/GESN source positions (layer 2). |
| Operation ↔ Normative mappings | `pnr_operation_normative_map`. N:M. No auto-allocation. |
| Operation ↔ Commercial mappings | To existing `boq_master_api`, not a cloned commercial catalog. N:M. |
| PNR Acceptance Requirements | Catalog of required evidence / document **types**, not signed instances. |
| Operation ↔ Acceptance Requirement mappings | Which operations contribute to which requirement types. Mapping ≠ actual acceptance. |

Future measurement / evidence / defect / constraint / state / signed-acceptance-instance entities may be added later **after** they are proven by real execution data. They are not v0.1 implementation.

### PNR does not own

| Concern | Owner / status |
|---------|----------------|
| SMR Daily Progress (`daily_progress_raw`, `daily_progress_active`, `daily_progress_form_submissions`) | Existing SMR execution fact. |
| Monthly Planning | Existing planning contour. |
| Monthly Passport | Existing planning contour. |
| Admission constraints | Existing admission contour. |
| Agent Runtime | Separate workstream. |
| General BOQ master (`boq_master_api`) | Existing operational commercial reference. |
| Shared Facility master | Does not exist; deferred. |
| Shared Person / Employee master | Does not exist; deferred. |
| Shared Project master | Does not exist; deferred. |
| Physical Asset / Equipment registry | Not found; deferred. |
| Product-wide GESN platform | Not claimed. `pnr_normative_items` is PNR-scoped source storage only. |
| Commissioning Agent | Deferred. |
| Signed acceptance instances (`pnr_acceptance_records` / `pnr_acceptance_instances`) | Named as future concept only; not designed in v0.1. |

PNR may **reference** objects it does not own (notably `boq_master_api`, and `eos_systems` once physically created). Reference is not ownership. `eos_systems` is shared Execution OS identity, not a PNR-owned registry.

---

## 6. Shared System identity decision

**Decision:** physical engineering system identity is an Execution OS shared concern, not a PNR private registry.

| Construct | Role | This increment |
|-----------|------|----------------|
| `eos_systems` | Shared durable `system_id` | **Contract designed** in schema design document. **Not physically created** by this ADR. |
| `pnr_systems` | PNR-only system registry | **Rejected** |
| Existing `system` / `system_label` | Current product text labels, primarily SMR/planning usage | **Unchanged; not migrated; not backfilled** |

Coexistence without refactor:

- PNR entities that need a system use `eos_systems.system_id`.
- Existing SMR / planning / daily-progress tables continue to store text `system` / `system_label`.
- `eos_systems` may hold an optional legacy label for correlation. That label is not an FK from SMR and is not a second identity.
- Display name on `eos_systems` may change; `system_id` and `system_code` remain stable (Law: identity ≠ label).
- No trigger, view rewrite, or column rename on SMR tables is implied.

Field-level contract is specified in `docs/pnr_dataset/PNR_SUPABASE_PHYSICAL_SCHEMA_V0_1.md`. That document is still not SQL and still not an implementation permit.

---

## 7. Commercial reference decision

**Decision:** PNR does not contain a commercial item master.

| Object | Decision |
|--------|----------|
| `boq_master_api` | Existing operational commercial reference. Unchanged. Not cloned. Not a GESN master. |
| `pnr_commercial_items` | Rejected. |
| `pnr_operation_commercial_map` | PNR-owned N:M mapping from PNR Operation to an existing BOQ commercial position. |

The map is a **relation**, not a copy of BOQ attributes. Commercial quantities, rates, and BOQ identity remain in `boq_master_api`.

Do not allocate BOQ labor automatically across operations.

How the map should reference `boq_master_api` (stable identifier, FK feasibility, identity risk) is a schema-design concern and must follow **repository-proven** identity, not an invented convenience column.

Commercial **recognition** (when commissioning work becomes billable/recognized) is downstream of the chain in section 2 and is not implemented in v0.1.

---

## 8. Labor and truth-layer model

Four layers remain distinct. Layers 2–4 are labor-related; layer 1 is commercial and must not be used as a labor master.

```
1. COMMERCIAL     boq_master_api
                  pay / commercial position
                  do not clone; do not treat as GESN

2. NORMATIVE      pnr_normative_items
                  source-authoritative estimate / GESN hours
                  do not invent; do not split via pnr_operation_normative_map

3. BASELINE       pnr_labor_baselines
                  customer-agreed / contractual labor
                  versioned; approved history is preserved
                  example context only: 800 person-hours on system P1

4. ACTUAL         pnr_execution_events + pnr_event_labor
                  what happened + labor by cause
```

Actual labor cause categories (v0.1):

| Category | Intent |
|----------|--------|
| `PRODUCTIVE` | Labor that advanced the intended operation. |
| `REWORK` | Labor repeating work already attempted. |
| `DEFECT_CORRECTION` | Labor correcting a defect. |
| `CONSTRAINT_LOSS` | Labor lost to a constraint / blockage. |

Illustrative event (design context only, not database seed):

- Operation: PNR-AUT-003 / Проверка алгоритма
- Result: BLOCKED
- PRODUCTIVE = 2 person-hours
- CONSTRAINT_LOSS = 6 person-hours
- Total event labor = 8 person-hours
- Still **one** execution event

A system-level baseline (800 h on P1) must **not** be treated as belonging entirely to one operation. Do not allocate it.

Normative labor (layer 2) must not be derived from baseline (layer 3) or actual (layer 4). Actual must not overwrite baseline. Commercial (layer 1) must not stand in for any of them.

---

## 9. Execution event grain

The atomic PNR fact is the **execution event**.

Grain:

```
1 execution event
  = 1 attempt
  to perform 1 operation
  on 1 commissioning object
  at a defined time / context
  with a defined result
```

Physical chain:

```
System → Commissioning Object → Work Scope → Operation → Execution Event → Event Labor
```

Work Scope and Operation are catalog constructs hanging off the system. The event binds an **object** plus either a catalog operation or unmapped operation information.

This grain is intentionally different from SMR Daily Progress, which (by existing product use) is a daily execution fact stream for construction progress, not a commissioning-attempt journal.

Implications:

- repeating the same operation on later dates produces new events, not updates in place;
- a blocked/failed attempt is a first-class fact;
- event identity is not “current status of the operation”; current status, if computed later, is a **projection** over the event history;
- physical state engine is deferred; event grain must still be correct so a later state engine has history to read.

---

## 10. Event / Labor separation

| Entity | Question | Must not answer |
|--------|----------|-----------------|
| `pnr_execution_events` | What happened? | How many hours of which cause? |
| `pnr_event_labor` | How much labor, and why? | What physical attempt occurred? |

Rules:

- labor components are children of an event, not siblings that replace the event;
- several labor categories on one attempt remain one event;
- absence of labor records must not erase the event (an attempt may be recorded before labor is allocated);
- labor totals are sums of components, not a second fact of “what happened”.

This separation is what allows Law 9: labor consumption can move without implying physical completion.

---

## 11. Append-oriented history rule

PNR execution history is **append-oriented**.

Required:

- a later PASS does not replace an earlier FAIL;
- corrections, if ever needed, are new facts or explicit compensation records — not silent mutation of the original attempt;
- “current result of operation X on object Y” is a derived view, not the stored grain.

Forbidden:

- upsert of the same operation/object to the latest result;
- deleting FAIL because PASS arrived;
- collapsing a multi-day attempt sequence into one mutable status row as the system of record.

Approved labor baselines are likewise historically preserved: a new approved version does not destroy the previous approved version.

Field-level implementation (immutability vs. status-plus-history, identifiers, timestamps) is specified in the schema design document. The law is behavioral: **history of attempts and approved baselines is preserved**.

---

## 12. Physical completion vs labor vs acceptance rule

Three independent axes:

| Axis | Measures | Must not be inferred from |
|------|----------|---------------------------|
| LABOR CONSUMPTION | Actual labor against a baseline or budget | Physical state or acceptance signature |
| PHYSICAL COMPLETION / STATE | What is physically true of the object/system after work | Labor ratios |
| ACCEPTANCE STATUS | Whether required evidence/documents are actually satisfied | Hours spent, informal “done”, or requirement mapping alone |

Worked distinction:

```
430 actual person-hours / 800 baseline
  = 53.75% labor budget consumption
  ≠ 53.75% physical commissioning completion
  ≠ 53.75% accepted
```

v0.1 stores:

- labor facts and baselines;
- operation → acceptance **requirement type** maps.

v0.1 does **not** store:

- a fake completion percentage derived from labor;
- a physical state engine;
- actual signed acceptance-document instances.

`pnr_operation_acceptance_map` ≠ actual acceptance.

---

## 13. Unmapped-operation rule

Catalog completeness is not a precondition for recording reality.

The execution model must allow:

1. an event against a known catalog operation;
2. an event against an operation that is **unknown / unmapped** at capture time, described on the event itself.

Do **not** insert a fake `UNKNOWN` row into `pnr_operations`.

Unmapped work remains real. Later it may be classified as, for example:

- standard operation (promoted into catalog)
- one-off operation
- defect correction
- extra work
- third-party work

Schema design must provide an enforceable rule so that an execution event contains **either** a catalog `operation_id` **or** unmapped operation information, and must justify whether exactly-one (XOR) semantics is appropriate.

---

## 14. Current PNR v0.1 entity boundary

This is the **current target set**, not permission to create tables. Future schema design may refine field-level implementation without violating the laws in this ADR.

**Supersedes** the earlier 10-entity list (`pnr_acceptance_documents`, `pnr_operation_document_map`, missing normative store).

### Shared identity

| # | Entity | Notes |
|---|--------|--------|
| 01 | `eos_systems` | Shared Execution OS physical system identity. Contract designed; **not created** by this ADR. Not a PNR-owned table. |

### Physical PNR

| # | Entity | Notes |
|---|--------|--------|
| 02 | `pnr_objects` | Commissioning objects. Belong to one system. |
| 03 | `pnr_work_scopes` | Work scopes. Belong to one system. |
| 04 | `pnr_operations` | Approved operations catalog. Belong to one work scope. |

### Normative / commercial / baseline

| # | Entity | Notes |
|---|--------|--------|
| 05 | `pnr_normative_items` | Authoritative estimate / GESN source positions for commissioning labor analysis. |
| 06 | `pnr_labor_baselines` | Versioned agreed labor baselines (layer 3). |
| 07 | `pnr_operation_commercial_map` | Operation ↔ `boq_master_api`. N:M. |
| 08 | `pnr_operation_normative_map` | Operation ↔ `pnr_normative_items`. N:M. No auto-allocation. |

Existing external commercial reference (unchanged): `boq_master_api`.

### Acceptance requirements

| # | Entity | Notes |
|---|--------|--------|
| 09 | `pnr_acceptance_requirements` | Catalog of required output / evidence / document **types**. Not signed instances. |
| 10 | `pnr_operation_acceptance_map` | Operation ↔ acceptance requirement. Mapping ≠ actual acceptance. |

### Physical execution reality

| # | Entity | Notes |
|---|--------|--------|
| 11 | `pnr_execution_events` | Append-oriented commissioning attempts. Catalogued **or** unmapped. |
| 12 | `pnr_event_labor` | Labor components of an event. |

No other PNR tables are in the v0.1 target. Names above are architectural entity names; physical column design is in the schema design document.

---

## 15. Explicit non-goals / deferred items

The following are **not** v0.1 implementation and are not authorized by this ADR:

- `pnr_measurements`
- `pnr_evidence`
- `pnr_defects`
- `pnr_constraints`
- physical state engine
- signed acceptance instances (`pnr_acceptance_records` / `pnr_acceptance_instances` — names reserved, not designed)
- shared Facility master
- shared Person master
- shared Project master
- SMR migration to `eos_systems`
- Agent Runtime integration
- Commissioning Agent
- QR/NFC asset tags
- robot / sensor integration
- physical `CREATE TABLE` / SQL for any of the 12 entities
- modification of `boq_master_api`
- modification of `daily_progress_*`
- modification of monthly planning / admission / passport
- changes to `docs/agentic_architecture/**` or `agents/**`

These remain future increments, each requiring its own design decision where it would touch these laws.

---

## 16. Consequences

Positive:

- PNR can be designed as a domain inside Execution OS without forking a second product or database.
- Physical system identity, when physically introduced, can be shared rather than PNR-private, while SMR labels remain untouched.
- Commercial truth remains singular (`boq_master_api`).
- Normative truth has a PNR-owned home that is not a BOQ clone.
- Commissioning history can accumulate as attempts, not as a mutable status.
- Labor can be analyzed by cause without cloning events.
- Incomplete catalogs cannot veto capture of field reality.
- SMR and PNR facts stay separable for analytics and for operational semantics.
- Acceptance requirement mapping cannot be mistaken for a signed act/protocol.

Binding constraints on later work:

- Schema v0.1 must respect event grain, append-oriented history, event/labor split, four truth layers, no hour invention, no BOQ clone, no PNR writes into `daily_progress_*`, XOR/unmapped event path, and versioned baselines.
- `eos_systems` physical creation, when authorized separately, is additive and must not silently rewrite existing `system` / `system_label` data.
- UI, agents, and reports must not present labor-consumption ratio as physical completion or acceptance.
- Agent Runtime must not be used as a substitute PNR journal.

---

## 17. Risks

| Risk | Why it matters | Mitigation in this ADR |
|------|----------------|------------------------|
| Provisional / legacy labels become a second master | Audit shows only text labels today. | `pnr_systems` rejected. `eos_systems.system_id` is identity; any legacy label is correlation only. |
| BOQ identity is not a clean PK | Product code uses `boq_code` and a composite grain; sync uses `airtable_record_id`. | Schema design must not invent a FK convenience column. FK enforcement is allowed only if repository evidence supports it. |
| Pressure to split normative or BOQ hours | Empty “hours per operation” columns invite invention. | Law 5. Maps have no allocated-hours field. |
| No Person master | Labor may be captured without who performed it. | Person master deferred; schema must not pretend one exists. |
| No Facility / Asset / Project registry | Objects may exist without stable facility/equipment/project identity. | Those masters deferred; do not invent them inside PNR. |
| SMR users may want one “progress” table | Convenience would collapse grains. | Law 8. |
| Requirement map mistaken for signed acceptance | Operators think mapping = акт exists. | Law 9 / section 12. Instances deferred. |
| Status views mistaken for system of record | Operators think in “current PASS/FAIL”. | Current status is a projection over append-only events. |
| Unmapped operations accumulate without classification | Reality is kept, but catalog never catches up. | Unmapped path is required; classification is a later process, not a capture blocker. |
| Example numbers leak into product data | 800 h / 1574.30 RUB / 37.44 h used as seed. | Explicitly design context only; not written to DB. |
| `eos_systems` contract designed, table not created | PNR schema depends on an identity that does not yet physically exist. | Design first; SQL later after review. No SMR refactor in between. |

---

## 18. Next architectural step

**Next:** review `docs/pnr_dataset/PNR_SUPABASE_PHYSICAL_SCHEMA_V0_1.md` before any SQL implementation.

That schema design may:

- specify physical tables, keys, and field-level types for entities 01–12;
- specify the `eos_systems` minimum viable contract and coexistence with text labels;
- specify unmapped-operation XOR (or justified alternative);
- document how commercial mapping references `boq_master_api` using proven identity only.

That step may **not**:

- create tables or run SQL;
- migrate SMR;
- clone BOQ;
- implement deferred entities in section 15;
- treat this ADR as an implementation permit.

---

## Document control

| Item | Value |
|------|--------|
| ADR | ADR-PNR-001 |
| Type | Architecture law / domain boundary |
| Authorizes code | No |
| Authorizes SQL | No |
| Authorizes Supabase change | No |
| Authorizes product data change | No |
| Supersedes (in-place refinements) | v0.1 names `pnr_acceptance_documents`, `pnr_operation_document_map`; “three labor truths” without a normative store; 10-entity list |
| Related existing product | Execution OS (`boq_master_api`, `daily_progress_*`, monthly planning / admission) — referenced, not modified |
| Related workstream (out of scope) | Agent Runtime |
| Companion design | `docs/pnr_dataset/PNR_SUPABASE_PHYSICAL_SCHEMA_V0_1.md` |
| Follow-on | Review schema design before SQL implementation |
