# Профессиональный паспорт цифрового сотрудника
# Production Shift Auditor Agent (PSAA)

**Document:** PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1  
**Version:** v0.1 (Initial Passport)  
**Status:** DESIGN + S01 CURRENT / PROVEN (fixture)  
**Standard:** PROFESSIONAL_PASSPORT_TEMPLATE_V1_0  
**Language:** Russian (English terms where architecturally useful)

---

## 1. Professional Identity

| Поле | Значение |
|------|----------|
| **Код** | `PRODUCTION_SHIFT_AUDITOR` |
| **Имя** | Production Shift Auditor Agent / Цифровой аудитор производственного исполнения |
| **Версия** | 0.1 |
| **Контур** | производственное исполнение (смена) |
| **Security tier** | TIER_0_READ_ONLY_DETERMINISTIC |

**Кто:** цифровой аудитор достоверности сменной производственной отчётности.

## 2. Why / Business Problem

Сменная отчётность мастера содержит заявленные трудозатраты и объёмы. Нужна профессиональная проверка математической целостности и честная фиксация ограничений данных до управленческой приёмки.

## 3. Responsibility

Исследовать достоверность сменной отчётности в пределах реализованных навыков; формировать `ShiftAuditArtifact`; передавать человеку вопросы, требующие решения.

### OWNED (v0.1)
- S01 Mathematical Integrity (детерминированно)
- Узкий trusted READ `daily_progress_active`
- Структурированный профессиональный артефакт с provenance

### SHARED
- EOS-SEC AgentExecutionContext / trusted READ executor
- Observability event contracts (Class-A lifecycle, best-effort)
- Константа целевого производительного фонда 8 чел·ч/чел (как в планировании)

### NOT OWNED
- Constructor Agent / месячное планирование
- Accept/reject смены
- Operation Registry / Labor Intelligence Library / TCE / зарплата
- Запись в `daily_progress_*` / Airtable
- LLM reasoning

## 4. Organizational Position

Отдельная профессиональная роль. Не tenant Constructor. Не клонирует Constructor packages, planning state, handoff.

## 5. Mission (v0.1)

По входу `ShiftAuditInput` (fixture или trusted READ) выполнить **S01** и вернуть `ShiftAuditArtifact`.

## 6. Skills

| Код | Навык | Статус |
|-----|-------|--------|
| S01 | Mathematical Integrity | **CURRENT** |
| S02 | Technological Integrity | TARGET |
| S03 | Physical Integrity | TARGET |
| S04 | Operation Cost Analysis | TARGET |
| S05 | Temporal Integrity | TARGET |
| S06 | Statistical Anomalies | TARGET |
| S07 | Causal Investigation | TARGET |
| S08 | Evidence Verification | TARGET |
| S09 | Shift Acceptance Conclusion | TARGET |
| S10 | Operation Classification | TARGET |
| S11 | Labor Benchmark Comparison | TARGET |
| S12 | Labor Intelligence Preparation | TARGET |

## 7. Tools

| Tool | Политика | Статус |
|------|----------|--------|
| `load_shift_daily_progress` | PUBLISHABLE_READ, allowlisted | CURRENT |

Write tools: **запрещены**.

## 8. Business Artifact

`ShiftAuditArtifact` — математические показатели, пооперационная детализация, наблюдения, missing data, clarification questions, раздельные статусы:
- arithmetic / math integrity
- data completeness
- professional credibility (NOT_EVALUATED в v0.1)
- managerial acceptance (NOT_IN_SCOPE)

**Не** ACCEPTED/REJECTED.

## 9. Security / EOS-SEC

- Registry: `PRODUCTION_SHIFT_AUDITOR` в `security/agent_execution_context.py`
- Manifest: `agents/production_shift_auditor/specification/security_manifest.json`
- Credentials только в infrastructure trusted executor
- Master free text = untrusted data
- Observability ≠ product write

## 10. Runtime

Тонкий модуль `agents/production_shift_auditor/runtime.py`. Без нового агентного runtime, без LangGraph, без Django/Streamlit UI в v0.1.

## 11. Current / Proven vs Target

| | |
|--|--|
| **CURRENT** | S01 + fixture proof; trusted READ adapter; EOS-SEC registration |
| **TARGET** | S02–S12; live-data professional campaigns; accept/reject; immutable shift versions |
| **NOT IN SCOPE (v0.1)** | LLM; UI; Constructor changes; Operation Registry; payroll |

## 12. Failure Conditions

- Смешение project/crew/date/shift → fail-closed diagnostic
- Конфликт `crew_size` → diagnostic, без суммирования по строкам
- `direct_work_hours` без доказанной семантики → `HOUR_FIELD_UNPROVEN`, без silent convert

## 13. Passport status

**Initial Passport v0.1** — design contract + S01 implementation evidence (fixture).  
Final Passport — после расширенного professional proof.
