# P1 Engineering Context and Physical Execution Architecture

**Status:** AUTHORITATIVE CHECKPOINT — Passport v0.2.2
**Date:** 2026-09-14
**Worktree:** `C:/csv_fix_pnr`
**Branch:** `wip/pnr-dataset-foundation`
**Committed HEAD at checkpoint:** `b60b141b3152786839e1933fc28426c36c56df66`
**This document:** architecture and implementation-status truth for Page60 / P1 Engineering Context Passport and the DYNAMIS physical execution chain.

This document does **not** authorize SQL, seed, Supabase writes, product data changes, Execution Event writes, or Agent Runtime work.

Related, non-competing documents:

- `docs/pnr_dataset/PNR_DATASET_PROGRESS.md` — append-only **implementation progress** log (FIELD-1A…1D, Foundation Seed).
- `docs/pnr_dataset/ADR_PNR_001_SHARED_SYSTEM_AND_DOMAIN_BOUNDARY.md` — domain boundary ADR.
- `docs/agentic_architecture/**` — Agent Runtime. Out of scope. Do not treat as PNR Dataset law.

---

## 1. Product identity

DYNAMIS target asset:

> «Целевой актив — система цифровых сотрудников, которая получает структурированную модель физического мира и управляет потоком его исполнения в пределах своих полномочий».

**Page60** is not the target asset and not merely a dashboard.
It is a human / digital-employee **work surface for physical execution**.

**Engineering Context Passport** is a structured engineering representation of a system and its source-backed context.

The Passport is **not**:

- Required Work;
- Execution History;
- Remaining Work;
- Proven State;
- Next Work;
- a replacement for physical execution orchestration.

---

## 2. Authoritative DYNAMIS physical execution chain

```
SOURCE DOCUMENTS
      ↓
ENGINEERING CONTEXT PASSPORT
      ↓
OPERATIONAL PHYSICAL OBJECT GRAPH
      ↓
PHYSICAL OBJECT
      ↓
OBJECT CONTEXT
      ↓
REQUIRED STATE
      ↓
GATE
      ↓
REQUIRED WORK
      ↓
EXECUTOR
      ↓
OPERATION
      ↓
EXECUTION EVENT
      ↓
MEASUREMENT / OBSERVATION
      ↓
EVIDENCE
      ↓
VALIDATION
      ↓
PROVEN STATE
      ↓
NEXT WORK
```

This is the **DYNAMIS execution chain**.

It is **not** a Page60 screen layout.
It is **not** authorization to implement all downstream layers.

---

## 3. Current implementation status

| Link | Status |
|------|--------|
| SOURCE DOCUMENTS | Encoded in Passport through DSS / DTS / REQ / MTO with per-fact provenance. |
| ENGINEERING CONTEXT PASSPORT | **IMPLEMENTED.** P1 Passport v0.2.2. Live on Page60 right-side 70% engineering work surface. |
| OPERATIONAL PHYSICAL OBJECT GRAPH | **PARTIAL / ENGINEERING CONTEXT ONLY.** Section 06 is a preliminary read-only physical structure. Not a persisted Physical Object Registry. Graph-node identities must not be fabricated. |
| PHYSICAL OBJECT | **PARTIAL.** Left rail can select a persisted object or a prototype object. Coverage is incomplete. Selection does **not** rebuild the system Passport. |
| OBJECT CONTEXT | **NOT YET IMPLEMENTED** as the next complete executable layer. UI distinguishes selected object from system Passport, but does not yet provide the structured object context required for orchestration. |
| REQUIRED STATE | **NOT IMPLEMENTED.** |
| GATE | **NOT IMPLEMENTED.** |
| REQUIRED WORK | **NOT PART OF PASSPORT.** Motor RW prototype exists only inside the isolated/collapsed execution prototype and is not authoritative downstream architecture. |
| EXECUTOR | **NOT MODELED** as an execution actor. The current Page60 field user must not be interpreted as the final executor model. |
| OPERATION | Existing catalog / unmapped selection exists only in the execution prototype / write path. |
| EXECUTION EVENT | Existing structured event write path exists through `create_structured_execution_event`. Prototype physical objects cannot write. |
| MEASUREMENT / OBSERVATION | Existing fields exist in the collapsed execution form. Law: **OBSERVATION != MEASUREMENT**. |
| EVIDENCE | **NOT CONNECTED.** |
| VALIDATION | **NOT IMPLEMENTED.** |
| PROVEN STATE | **NOT COMPUTED.** Do not infer from the current prototype. |
| NEXT WORK | **NOT IMPLEMENTED.** |

---

## 4. Passport v0.2.2 Page60 architecture

**Layout:** 30/70 — `st.columns([3, 7], gap="large")`

**LEFT — navigation / control rail:**

- project;
- title;
- discipline;
- system;
- Passport context (system as a whole);
- selected physical object.

Selecting an object does not open an object-specific Passport.

**RIGHT — P1 Engineering Context Passport** when the selected system context is П-1.

Passport title:

«Паспорт инженерного контекста системы П-1»

**12 accepted sections:**

01. Идентификация системы
02. Назначение и функциональная граница
03. Обслуживаемые помещения и физические зоны
04. Физическая среда и функциональный поток
05. Проектные характеристики и требуемые режимы
06. Операционный граф физических объектов системы П-1
07. Энергетические и технологические контуры
08. Автоматизация и функциональная логика
09. Внешние интерфейсы и зависимости
10. Источники, ревизии и происхождение данных
11. Конфликты, неопределённость и отсутствующий контекст
12. Документальная модель системы

**Tabs:**

| Tab | Sections |
|-----|----------|
| Обзор | 01–05 |
| Физическая система | 06–07 |
| Функциональная логика | 08–09 |
| Источники | 10 + 12 |
| Конфликты | 11 |

The existing execution form remains isolated in the collapsed full-width expander
«Фиксация физического исполнения — текущий прототип»
and must not redefine Passport semantics.

Presentation law (v0.2.1 / v0.2.2):

- per-fact provenance is retained in the structured model;
- the UI may group consecutive facts only when provenance is identical;
- mixed sources must not be shown as one common source;
- user-facing Passport language is professional Russian;
- genuine technical identifiers are not translated (П-1, 795-U-030A/B, ВЕРОСА, DSS/DTS/REQ/MTO, document codes, ШСАУ, ПЧ, ИСУБ).

---

## 5. Two-graph model

These are two different graphs. They must not be collapsed into one UI widget or one table.

### GRAPH 1 — Операционный граф физических объектов

Semantic model:

```
Система
  → установка
    → узел
      → оборудование
        → компонент
          → связь
```

Purpose: answers «С чем мы имеем дело?»

Exact current heading:

«Операционный граф физических объектов системы П-1»

A hierarchy / tree alone is **not** the final operational graph.
The future graph must support **typed relationships** between physical objects.

Examples of future relationship semantics (not implemented in this checkpoint):

- входит в состав;
- обслуживает;
- соединён с;
- управляется;
- получает питание;
- получает тепло;
- зависит от;
- функционально связан;
- сблокирован с.

Do **not** implement these relationships in this checkpoint.

### GRAPH 2 — Операционный граф физического исполнения DYNAMIS

Semantic model:

```
Объект
  → требуемое состояние
    → Gate
      → работа
        → исполнитель
          → операция
            → событие
              → измерение / наблюдение
                → подтверждающие материалы
                  → проверка
                    → доказанное состояние
                      → следующая работа
```

Executable law:

```
STATE
  → GATE
    → WORK
      → EXECUTOR
        → OPERATION
          → EVENT
            → EVIDENCE
              → VALIDATION
                → NEW STATE
                  → NEXT WORK
```

The graphs will ultimately be joined through canonical physical identity / `physical_object_id`.
Do **not** implement this join now.

---

## 6. Fundamental dataset laws

Architectural invariants:

- **РАБОТА != ОПЕРАЦИЯ != СОБЫТИЕ ИСПОЛНЕНИЯ**
- **OBSERVATION != MEASUREMENT**
- **EXECUTION STATUS != EVALUATION RESULT != OBJECT STATE**
- **FAIL != BLOCKED**
- **Progress != State != Health != Closure**

State must be derived from proven facts / evidence / validation.
State must not be manually asserted merely because a user selected a status.

A repeated attempt creates a **new** execution event.
It must not overwrite the previous event.

---

## 7. Engineering context / provenance law

Documents are sources of engineering assertions, not final knowledge units.

Target transformation:

```
DOCUMENT-CENTRIC
  → ENTITY / RELATIONSHIP / EVENT / REQUIREMENT / STATE-CENTRIC
```

Every significant engineering fact should preserve provenance:

```
SOURCE
  → DOCUMENT
    → REVISION
      → source location when genuinely known
        → extracted assertion
          → verification status
```

Do not fabricate source locations.
AI must not silently resolve contradictory engineering facts.

Current example (Conflict 01 — no automatic winner):

| Source | Values |
|--------|--------|
| DSS 0015 / 06C | 18 515 м³/ч; 1034 Па |
| DTS 0033 / 01D | 18 515 × 1,06 = 19 625 м³/ч; 800 Па |

Status: **КОНФЛИКТ / ТРЕБУЕТ ИНЖЕНЕРНОЙ ПРОВЕРКИ**

---

## 8. Current P1 physical model status

Section 06 currently includes a **preliminary** engineering structure, approximately:

```
П-1
  → П1.1 / 795-U-030A [рабочая]
      → ВЕРОСА-500-194-02-61-УХЛ3
          → входная часть
          → фильтрация
          → воздухонагреватель
          → вентиляторный узел
      → ШСАУ П1.1
      → блочный ИТП П1.1
  → П1.2 / 795-U-030B [резервная]
  → воздушный тракт П-1
  → внешние связи
```

П1.2 exists as standby context. Its child structure must **not** be automatically copied from П1.1 without source-backed identity validation.

Air path and external relationships are context nodes, not automatically persisted equipment identities.

The current structure is **preliminary engineering context**, not a final asset registry.

Related ventilation systems of the compressor room (В1, В2, АВ1/АВ2, ПЕ1/ПЕ2) are functionally related to П-1 and **do not form part of П-1**.

---

## 9. Next authorized architectural step

**NEXT ARCHITECTURAL STEP:**

```
OBJECT CONTEXT
  → REQUIRED STATE
    → GATE
```

This is the next **design** increment.
It must be designed first on **one real П1.1 physical object** before broad implementation.

Required Work is **not** the immediate next implementation.

Intended sequence (design only; not implemented by this checkpoint):

1. select one physical object;
2. resolve its identity;
3. understand its parent / system position;
4. define its engineering function;
5. define inputs / outputs;
6. define source-backed relationships;
7. define required state;
8. define conditions / gates that prove readiness or permit transition;
9. only then derive Required Work.

No implementation of this sequence is authorized by this document.

---

## 10. Forbidden drift

Until separately authorized:

- Passport must not become Required Work;
- Passport must not become execution history;
- Passport must not become remaining-work logic;
- physical graph nodes must not silently become persisted registry identities;
- selecting an object must not be interpreted as an object-specific Passport implementation;
- current prototype events must not be used to compute Proven State;
- Next Work must not be fabricated;
- П1.2 physical child structure must not be cloned from П1.1;
- AI must not silently resolve source conflicts;
- Agent Runtime must remain separate from PNR Dataset.

---

## 11. Security / data boundary of this checkpoint

This architecture checkpoint and the uncommitted Page60/Passport workstream:

- do not add SQL migration;
- do not write to Supabase;
- do not write product execution events as part of the Passport increments;
- do not modify production data;
- do not modify Agent Runtime;
- do not add new authorization semantics;
- do not add a new autonomous write path.

The existing FIELD-1B/1D structured write path (`create_structured_execution_event`) remains unchanged and remains gated: prototype physical objects cannot write.

---

## 12. Accumulated uncommitted work recorded by this checkpoint

Uncommitted Page60 / Passport workstream as of 2026-09-14 (not yet staged or committed):

| Increment | Result |
|-----------|--------|
| FIELD UI Language Gate | User-facing professional Russian execution form |
| Vertical Slice v0.1 | Isolated execution prototype + prototype motor/fan keys |
| Passport v0.2 | 30/70 layout; 12-section Passport; 5 tabs |
| Passport v0.2.1 | Compact presentation; provenance grouping; left-rail system vs object distinction |
| Passport v0.2.2 | Product language cleanup; no internal development wording on Passport |

This document does not authorize git add / commit / push.
