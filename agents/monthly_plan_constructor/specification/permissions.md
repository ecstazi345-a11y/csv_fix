# Permissions — MONTHLY_PLAN_CONSTRUCTOR v0.1

## Автоматически разрешено

- читать scope / adjustments / existing plan lines;
- нормализовать month_key и ключи scope;
- рассчитывать remaining / available_to_add;
- сравнивать и агрегировать already_planned;
- классифицировать позиции;
- исключать из proposal с reason_code;
- формировать кандидатов и human_issues;
- писать trace и business actions в объект run (не в DB).

## Запрещено в v0.1

- product INSERT / UPDATE / DELETE / UPSERT;
- RPC mutation;
- запись в `monthly_plan_lines_v2`;
- запись в `monthly_scope_manual_adjustments`;
- запись в `monthly_plan_constraints`;
- перевод строк в `SENT_TO_ADMISSION`;
- approve месяца;
- force include;
- invent crew;
- invent planned_qty;
- invent physical quantity;
- вызовы LLM (OpenAI / Anthropic / YandexGPT / GigaChat и др.).

## Future human-gated (описать, не реализовывать)

- создание plan lines из кандидатов;
- выбор / подтверждение `planned_qty`;
- выбор `crew`;
- force include после human decision;
- отправка в Admission Agent;
- approve month plan;
- запись adjustment not_required.
