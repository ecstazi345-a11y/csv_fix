# Permissions — MONTHLY_PLAN_CONSTRUCTOR

**Версия контракта:** v1.0 target professional envelope (2026-10-02)
**Канон:** `docs/agentic_architecture/CONSTRUCTOR_AGENT_ANATOMY.md`
Код полномочий v0.1 не меняется этим документом.

Пять классов: `AUTO` / `AUTO_WITH_TRACE` / `HUMAN_REVIEW_REQUIRED` / `HUMAN_DECISION_REQUIRED` / `FORBIDDEN`.
Целевой уровень на выходе: **HUMAN_DECISION_REQUIRED**.

## AUTO / AUTO_WITH_TRACE

- читать professional sources через professional tool contracts (`get_working_scope`, `get_physical_remainder`, `get_existing_month_plan`, `get_adjustments`, `get_system_context`, `get_work_package_context`, `get_labor_norm`, `get_execution_state`);
- нормализовать данные;
- считать remainder;
- исключать очевидные completed / no remainder / invalid headers;
- определять `available_to_add`;
- искать и предлагать labor norm (не invent);
- выявлять conflicts / anomalies;
- формировать recommendations (target);
- создавать Candidate Package;
- писать trace в объект run (не в product store).

## HUMAN_REVIEW_REQUIRED

- спорные кандидаты;
- unresolved labor norm на discovery (кандидат остаётся видимым);
- data conflicts;
- нестандартные корректировки;
- аномальные quantities / norms.

## HUMAN_DECISION_REQUIRED

- итоговое включение / исключение позиции;
- ручная labor norm либо подтверждение предложенной;
- подтверждение Reviewed Candidate Package;
- Human Confirm запуска handoff к Executability Agent.

Человек ревьюит подготовленный пакет массовыми решениями. Не собирает BOQ до миссии.

## FORBIDDEN (включая v0.1 product writes)

- invent quantity / planned_qty / physical remainder;
- invent labor norm (в том числе LLM);
- скрывать `UNRESOLVED`;
- удалять физического кандидата только из-за `LABOR_NORM_UNRESOLVED`;
- product INSERT / UPDATE / DELETE / UPSERT / RPC mutation;
- запись плана, корректировок, ограничений, статусов допуска;
- менять BOQ master;
- менять договорные цены;
- approve месяца / утверждать месячное обязательство;
- force include в обход Human Review;
- invent crew;
- вызовы LLM;
- фабриковать receiver acceptance;
- считать persisted handoff = получатель принял;
- считать Constructor completed = orchestration completed;
- передавать не-reviewed пакет;
- included `UNRESOLVED` в Reviewed Candidate Package.

## Current adapter (не профессия)

Текущие Python READ tools: `load_scope`, `load_adjustments`, `load_existing_month_plan_lines`.
Write tools: none.

## Future human-gated (описать, не реализовывать здесь)

- создание plan lines из reviewed кандидатов;
- force include после human decision;
- запись adjustment `not_required`;
- Orchestrator-driven launch / auto-handoff.
