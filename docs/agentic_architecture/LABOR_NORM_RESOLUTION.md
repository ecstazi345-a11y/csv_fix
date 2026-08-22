# Labor Norm Resolution

**Status:** TARGET ARCHITECTURE v0.1<br>
**Date:** 2026-08-22<br>
**Implementation in this checkpoint:** NONE (no GESN connector, no scraping, no new tables)

---

## 1. Critical law

```
MISSING INTERNAL HISTORY ≠ STOP THE ENTIRE PLANNING FLOW
```

Отсутствие собственного исторического P50 **не** означает отсутствие физически существующей работы.

Physical candidate package может существовать при:

- `VALIDATED` norm;
- `PROVISIONAL` norm;
- `UNRESOLVED` norm.

Норма труда — отдельная атрибутированная оценка. Она нужна для:

- resource planning;
- economic analysis;
- capacity estimation;
- tender estimation;
- production forecasting.

Она **не** является единственным условием существования candidate work.

---

## 2. LaborNormResolver

Future shared service / capability / tool.

Условное техническое имя: `LaborNormResolver`.

Пока **не** обязательно отдельный AI Agent.

Потребители в будущем:

- Constructor Agent;
- Resource Agent;
- Economic Agent;
- Tender / Estimation Agent;
- Execution analytics.

Если автономия и сложность вырастут — может эволюционировать в специализированного агента.<br>
Когда это делать — OPEN.

Constructor **не** становится Normative Estimator, Resource или Economic Agent.<br>
Он только прикладывает metadata нормы к пакету, если resolver вернул результат.

---

## 3. Source hierarchy

Приоритет определяется **качеством, сопоставимостью и доказанностью**, не магическим номером. Ниже — канонический порядок поиска.

### Level 1 — PROJECT_HISTORY

Фактическая производительность **этого же проекта** на сопоставимой операции и условиях.

Пример: доказанный executed quantity + productive direct work hours.

### Level 2 — COMPANY_HISTORY

Корпоративная история аналогичных проектов / операций.

### Level 3 — OFFICIAL_NORMATIVE

Официальные нормативные источники, например применимые **ГЭСН / ФСНБ** и иные официальные базы.

**ГЭСН не объявлять автоматически «истинной фактической производительностью бригады».**

Это normative benchmark / сметно-нормативная база — исходный ориентир.

Всегда сохранять:

- reference;
- edition / version;
- work item mapping;
- units.

Сейчас: **не** реализовывать scraping.<br>
**Не** подключать нелегальные / недоказанные источники.<br>
Legal/licensed access — OPEN.

### Level 4 — TECHNOLOGICAL / VENDOR / INDUSTRY STANDARD

Технологические карты; инструкции производителей; пусконаладочные процедуры; отраслевые нормативы; производственные стандарты.

Особенно важно для ПНР, КИПиА, специализированного оборудования, работ, для которых ГЭСН слишком груб.

### Level 5 — INDUSTRY_BENCHMARK

Доказуемые отраслевые / международные benchmarks.

Обязателен provenance.<br>
Запрещено: «мировая практика = 1,7 чел·ч» без конкретного источника.

### Level 6 — EXPERT_APPROVED

Временная экспертная оценка, явно подтверждённая человеком, если более сильного источника нет.

Обязательно:

- author;
- date;
- scope;
- reason;
- expiry / review condition.

---

## 4. No invented labor norms

**LLM не имеет права** придумать labor norm из общего знания и сохранить её как authoritative.

Запрещено:

> «по мировой практике эта работа обычно занимает примерно…»

без проверяемого источника.

LLM **может**:

- найти candidate source;
- сопоставить work description;
- объяснить различия единиц / состава работ;
- предложить человеку выбор.

Authoritative norm **должна** иметь provenance.

---

## 5. Three different labor values

Они **не** одна цифра.

| Вид | Смысл |
|-----|--------|
| **NORMATIVE / BENCHMARK NORM** | Внешняя или официальная базовая норма (ГЭСН и т.п.) |
| **OBSERVED PRODUCTIVITY** | Фактическая историческая производительность: P50, P80 или другие статистики |
| **PLANNING NORM** | Норма, **принятая** для данного месяца / условий выполнения |

Пример:

```
ГЭСН / benchmark:                 2.1 чел·ч/ед.
Компания historical P50:          1.6 чел·ч/ед.
Плановая норма сентября (условия): 1.9 чел·ч/ед.
```

Каждое значение хранит смысл и происхождение. Не затирать одно другим.

Текущий продукт Page10B использует `p50_hours_per_unit` из `monthly_scope_picker_view` и `labor_hours = qty × P50`, `labor_cost = hours × 3000` (константа страницы, **не** verified payroll). Это **не** отменяет разделение трёх величин в целевой архитектуре.

---

## 6. LaborNormResolution — conceptual contract

Минимум полей (имена стабилизировать при реализации сервиса):

| Поле | Назначение |
|------|------------|
| `operation_id` | если таксономия операций появится |
| `boq_code` | связь с ведомостью |
| `work_type` | тип работы |
| `unit` | единица |
| `norm_value` | чел·ч / ед. (или явно указанная единица) |
| `norm_low` | optional |
| `norm_high` | optional |
| `source_type` | см. ниже |
| `source_reference` | конкретная ссылка |
| `source_version` | редакция |
| `source_date` | дата источника |
| `confidence` | качество оценки |
| `conditions` | условия применимости |
| `adjustment_factors` | future; не универсальная формула сейчас |
| `provisional` | временная / под пересмотр |
| `review_after_quantity` | после какого факта пересмотреть |
| `resolved_at` | когда резолв выполнен |

`source_type`:

```
PROJECT_HISTORY
COMPANY_HISTORY
OFFICIAL_NORMATIVE
TECHNOLOGICAL_STANDARD
VENDOR
INDUSTRY_BENCHMARK
EXPERT_APPROVED
```

---

## 7. Confidence / provenance

Каждая норма должна иметь:

- SOURCE
- REFERENCE
- VERSION
- CONFIDENCE
- CONDITIONS
- PROVISIONAL / VALIDATED STATUS

Пример A — своя история:

```
Норма:        1.42 чел·ч/м²
Источник:     PROJECT_HISTORY
Выборка:      6840 м²
Productive hours: 9710 чел·ч
Confidence:   HIGH
Conditions:   height <= 4 m; normal access
```

Пример B — нет своей истории:

```
Норма:        1.75 чел·ч/м²
Источник:     OFFICIAL_NORMATIVE
Reference:    конкретная нормативная позиция + редакция
Confidence:   MEDIUM
Provisional:  TRUE
Review:       после первых 100 м² собственного факта
```

---

## 8. Resolution flow

```
WORK ITEM
  → SEARCH PROJECT HISTORY
       если enough comparable trustworthy data → project statistical profile
  → else SEARCH COMPANY HISTORY
  → else SEARCH OFFICIAL NORMATIVE
  → else SEARCH TECHNOLOGICAL / VENDOR / INDUSTRY SOURCE
  → else SEARCH VERIFIED INDUSTRY BENCHMARK
  → else HUMAN EXPERT REQUEST
```

Если никакой источник не доказан:

```
NORM_STATUS = UNRESOLVED
```

Но:

- physical candidate **не обязательно** блокируется;
- Resource / Economic readiness **может** быть `BLOCKED` / `INCOMPLETE`.

Unknown norm **не** становится silently zero.<br>
Zero hours как «норма» без provenance запрещены.

---

## 9. History quality

```
HISTORY EXISTS ≠ HISTORY IS TRUSTWORTHY
```

Не считать любой historical P50 правильным.

Известная порча нормы:

- paid hours without executed quantity;
- простои;
- ожидание;
- обучение;
- непроизводительные часы;
- ошибочная классификация;
- paid direct hours without EV.

Для production norm использовать **валидированные productive direct hours** и **доказанный executed quantity**.

Comparability checks (тот же метод, высота, доступ, материал) — future capability; принцип обязателен уже сейчас.

---

## 10. Conditions / adjustment factors

Future architecture должна уметь нести условия:

height; restricted access; weather; learning curve; shift pattern; congestion; material handling; welding class; diameter; material; installation method; equipment type.

**Не** реализовывать сейчас универсальную формулу коэффициентов.<br>
Зафиксировано как future capability.

---

## 11. Continuous learning loop

Стратегическая петля — долгосрочный цифровой актив компании:

```
EXTERNAL / NORMATIVE BENCHMARK
  → PLANNING NORM
  → EXECUTION
  → VALIDATED PRODUCTIVE HOURS
  → OBSERVED PRODUCTIVITY
  → PROJECT P50 / P80
  → COMPANY HISTORY
  → BETTER FUTURE PLANNING NORM
```

Execution OS постепенно создаёт собственную корпоративную production norm knowledge base.

---

## 12. Constructor package example

```
70 physical candidate works
  52 VALIDATED (internal)
  11 PROVISIONAL (official/tech benchmark)
   7 UNRESOLVED
```

Constructor **не** выкидывает 7 из physical package.

Передаёт `labor_norm_status` по позициям и summary в handoff.

Resource инициирует resolution / exception по unresolved, если capacity нужно финализировать.<br>
Economic показывает uncertainty.<br>
Человек видит только необходимый вопрос, не 70 строк «поставьте норму руками».

---

## 13. Relation to current MPCA write path

MPCA-002 write: missing P50 → `LABOR_NORM_MISSING`, **zero writes** plan lines.

Это закон **записи** строки плана с derived labor, не закон physical candidacy.

Не смешивать:

- нельзя записать labor_hours без доказанной нормы;
- можно держать физическую работу в candidate package со статусом UNRESOLVED.

---

## 14. Open items

- exact ГЭСН connector и лицензии;
- operation taxonomy;
- mapping BOQ → operation → source;
- confidence formula;
- adjustment factor model;
- persistence schema норм;
- момент, когда resolver становится агентом.
