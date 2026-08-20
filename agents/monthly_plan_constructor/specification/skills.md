# Skills — MONTHLY_PLAN_CONSTRUCTOR v0.1

| # | Skill (EN) | Label (RU) | Input | Action | Output |
|---|------------|------------|-------|--------|--------|
| 1 | `get_working_scope` | Получить рабочий состав | project_code | READ scope view | scope rows |
| 2 | `calculate_availability` | Рассчитать доступность | scope + adjustments | merge not_required once + frozen BOQ metrics | availability df |
| 3 | `apply_existing_month_plan` | Учесть существующий месячный план | plan lines | aggregate already_planned | updated availability |
| 4 | `exclude_unavailable` | Исключить недоступное | classified rows | exclude completed / no remainder / fully planned / invalid | exclusions |
| 5 | `detect_conflicts` | Проверить конфликты | human_issues | filter blockers | conflicts |
| 6 | `build_candidates` | Сформировать кандидатный состав | open rows | build Candidate structs | candidates |
| 7 | `build_human_exceptions` | Сформировать исключения для человека | issues | package real exceptions | human_issues |
| 8 | `prepare_handoff` | Подготовить результат для следующего этапа | candidates + issues | build handoff contract | handoff |

Python: `agents/monthly_plan_constructor/skills.py`
