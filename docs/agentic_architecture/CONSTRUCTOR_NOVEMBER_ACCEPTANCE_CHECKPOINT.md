# Constructor — November Acceptance Checkpoint

Durable transfer checkpoint. Purpose: recover the exact current state on
another computer / session without reconstructing history.
This is a checkpoint, not an architecture specification.

## 1. AUTHORITATIVE GIT CHECKPOINT

- Branch: `wip/increment-11c-persistent-shadow-stores`
- HEAD: `e40a441dea7e6b328bc79c76928622c274820e04`
  (`feat(agents): complete constructor candidate handoff flow`)
- Local == Remote at checkpoint creation.
- October Constructor end-to-end: **PASS** (live, real human decisions).

## 2. OCTOBER RESULT (immutable, do not modify)

- Human-Approved Monthly Candidate Package:
  `amp-d0fc158c5de1f60dc7dc4a01f5470546`
- Source Candidate Package: `3ef26b0e-1f5c-41ef-a06e-e39758749273`
- Source run: `run-a0c70277-486b-439d-a6be-7599411ffc37`
- Human Review: 26/26 resolved (22 accepted / 3 deferred / 1 excluded)
- Handoff: `eos-hof-83513cfa0868427d844dbb5ae9b452a7`
- Handoff status: `HANDOFF_PERSISTED`
- Source role: `MONTHLY_PLAN_CONSTRUCTOR`
- Target role: `MONTHLY_PLAN_ADMISSION_AGENT`
  (Инженер производственной готовности и допуска)
- Receiver: `RECEIVER_NOT_CONNECTED` (честно: приёмник ещё не подключён)
- Artifact content hash:
  `81eb83724fdebba8db08935a0947105c728608dfe5b4173d5b02ac89d863d30b`
- Observability baseline: 16 runs / 296 events. No Admission run exists.
- Professional law: an approved candidate package is HUMAN INTENT /
  PROPOSED MONTHLY SCOPE, **not** a production commitment. Production
  commitment exists only after Admission/Release (not built yet).

## 3. NOVEMBER ACCEPTANCE GOAL

Structured context (exact):

- PROJECT: `PRJ_001_БХК` / БХК
- MONTH: ноябрь 2026
- QUEUE: 1
- TITLE: 16160-13
- DISCIPLINE: Автоматизация
- SYSTEMS: Все системы
- PACKAGES: Все пакеты
- DIGITAL EMPLOYEE: `MONTHLY_PLAN_CONSTRUCTOR`
  (Инженер формирования месячного плана)
- PROFESSIONAL CONTOUR: формирование кандидатного состава месяца

Mission text (exact):

> «Сформировать кандидатный состав на ноябрь 2026
> по проекту PRJ_001_БХК, очередь 1, титул 16160-13,
> дисциплина Автоматизация.
> Рассмотреть работы по:
> — прокладке кабеля;
> — монтажу датчиков;
> — монтажу крышек кабельных лотков.
> Использовать актуальную производственную реальность,
> остатки, ранее запланированные и выполненные объёмы
> и существующие ограничения Constructor.»

Target work categories: прокладка кабеля; монтаж датчиков;
монтаж крышек кабельных лотков.

## 4. FIRST NATURAL LANGUAGE ATTEMPT (failed, recorded)

Exact user command:

> «БХК, ноябрь 2026, титул 16160-13, автоматизация.
> Сформировать кандидатный состав по работам:
> прокладка кабеля, монтаж датчиков,
> монтаж крышек кабельных лотков.»

Observed Quick Command parse:

- Project: БХК (resolved)
- Month: ноябрь 2026 (resolved)
- Title: **incorrectly split as `16160, 13`** (defect)
- Queue: unresolved
- Discipline: unresolved
- Agent: unresolved
- Professional contour: unresolved
- Structured mission text remained stale (still referenced October 2026)

## 5. INTERPRETATION

- This is a **Human Surface / Quick Command interpretation defect**.
- It is NOT evidence of a Constructor Core failure.
- Constructor Core has **NOT YET been tested for November**.
- No wording-to-BOQ semantic mapping exists; Constructor consumes
  structured scope, not free-text work names. Do not invent one ad hoc.

## 6. PRE-RUN VALIDATION (read-only, 2026-10-22)

Source reality for the structured November mission EXISTS:

- Project `PRJ_001_БХК` scope rows (monthly_scope_picker_view): 660
- Queue 1 facts (Work Context catalog): 530; facility rule 16160-13 → 1
- Title 16160-13 rows: 262
- Title + Автоматизация rows: 74; with planning remaining > 0: 23
- Work Context catalog: «ноябрь 2026» is an available month;
  systems and packages present for the slice
- BOQ name signals at Title + Автоматизация:
  - кабель («кабел»): 37 names (кабельные трассы, кабеленесущие системы)
  - датчики («датчик»): 5 names (датчики давления / температуры)
  - крышки лотков/лестниц («лотк» 11, «крышк» 3, e.g. монтаж крышки
    кабельной лестницы)
- November plan lines already planned: 0 (expected; candidates are
  proposed from remaining reality)
- November Constructor runs existing: **0** (16 runs, all October-era)
- October artifacts unchanged: YES (16 runs / 296 events,
  1 approved package, 1 handoff)

## 7
...[truncated 1792 chars]