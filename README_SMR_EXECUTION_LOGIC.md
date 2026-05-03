Правильный откат для фильтрации и учета по неделям 

Сейчас делаем так:

1. Основное сопоставление оставляем месячное.
2. Недельный фильтр используем только для факта.
3. Не считаем “план недели”.
4. Не считаем “невыполненный план недели”.
5. Показываем: что реально сделали за выбранную неделю.

## в июне надо попробовать так:

BOQ + IWP + System + Discipline + Building + Crew + Week_Key + Planned_Qty_Week + Planned_Value_Week

И тогда:

сумма недель = месячный план






0. Контроль качества данных
0.1 Ошибки классификации факта
1. Сводка СМР за период
2. План / Факт / Вне плана
3. Где сломался план
4. Факт вне плана
5. План без факта
6. Контроль звеньев
7. ТОП проблем / Кто ломает план


Monthly Passport Plan = план
Daily Progress Raw = сырой факт
Daily Progress Clean/Agg = очищенный и агрегированный факт
SMR Reconciliation = план / факт / вне плана
SMR Month Summary = KPI карточки
SMR Plan Line Control = где сломался план
SMR Crew Control = контроль звеньев
SMR Data Quality Issues = ошибки ввода мастеров
Streamlit = витрина для стройки


проблема была не в Streamlit и не в Supabase,
а в ошибках классификации данных :
Project / Facility / IWP / System_Label / Discipline

Оставляем рабочий набор view

Рабочие view:

daily_progress_clean
daily_progress_monthly_agg_clean
smr_plan_work_key
smr_reconciliation
smr_plan_line_control
smr_month_summary
smr_crew_control
smr_problem_aggregation
smr_validation_work_key
smr_data_quality_issues
smr_data_quality_check


## daily_progress_clean
Очищенный слой Daily Progress. Нормализует пробелы, неразрывные пробелы и грязные значения.

## daily_progress_monthly_agg_clean
Агрегированный факт по очищенным данным.

## smr_plan_work_key
Уникальный плановый ключ работы:
project_code + month_key + boq_code + iwp_id_export + system_label

Нужен, чтобы одна строка факта не умножалась на несколько строк плана.

## smr_validation_work_key
Проверяет, сходится ли RAW факт и SMR факт по ключу работы.

## smr_data_quality_issues
Показывает ошибки классификации:
- WRONG_FACILITY
- WRONG_DISCIPLINE

Если raw_ev > 0, значит мастер записал факт не туда.


Старые view не удаляем, но в Streamlit больше на них не опираемся.

Старые/вторичные:

monthly_plan_vs_fact
work_plan_fact_reconciliation
work_plan_fact_by_plan_line
daily_progress_monthly_agg
daily_progress_sum...
boq_sum...

Пока не трогаем.


🚀 SMR EXECUTION LOGIC (План / Факт / Деньги)
📌 Цель системы

Понять:

где выполняем не по плану
где делаем вне плана
какие звенья ломают выполнение
сколько денег не конвертируется в результат

🧱 УРОВЕНЬ 1 — ИСТОЧНИКИ ДАННЫХ (SOURCE OF TRUTH)
1. monthly_passport_plan

План работ на месяц

Содержит:

boq_code
iwp_id_export
system_label
crew (plan_crew)
plan_qty_month
plan_pv_workvalue_auto
budget_status

📌 Это единственный источник плана

2. daily_progress_raw

Сырой факт с площадки (каждая смена)

Содержит:

quantity_today
ev_day_value
crew_id
boq
iwp_id
system_label

📌 Это источник реального исполнения

3. daily_progress_monthly_agg

Агрегация факта по месяцу

Содержит:

actual_qty_total
ev_total
crew_id
boq
iwp_id
system_label

📌 Это основа для сопоставления с планом

🧠 УРОВЕНЬ 2 — РАБОЧИЕ ВИТРИНЫ (CORE VIEWS)
4. smr_plan_line_control

Главная витрина "30 строк плана vs 500 строк факта"

Одна строка = одна строка Monthly Passport

Содержит:

plan_qty
plan_value
actual_qty (сумма факта)
ev_value (сумма факта)
fact_crew
plan_crew

📌 Показывает:

где не выполнено
где выполнено
где неправильное звено
5. smr_reconciliation

Контроль структуры выполнения

Статусы:

MATCHED → план выполнен
PLAN_ONLY → план есть, факта нет
FACT_ONLY → сделали вне плана

📌 Показывает:

хаос
выполнение вне фронта
дырки в планировании
6. smr_month_summary

Сводка для карточек (верх экрана)

Содержит:

plan_total
approved_plan
matched_ev
fact_only_ev
plan_only_value
execution_percent

📌 Это единственный источник KPI

7. smr_crew_control

Контроль звеньев

Содержит:

plan_crew
fact_crew
ev_value
отклонения

📌 Показывает:

кто работает не по плану
кто делает чужую работу
где развал управления
8. smr_data_quality_check
Проверяет, не выпали ли записи из-за пустых project_code, month_key, boq, iwp_id, system_label.

9. smr_problem_aggregation
Агрегирует проблемные зоны по статусам, звеньям, зданиям и дисциплинам.
Показывает, где концентрируются потери.


⚠️ ГЛАВНЫЕ ПРАВИЛА
❌ НЕЛЬЗЯ
считать план из fact таблиц
суммировать plan_value после join (будет дублирование)
смешивать источники в одном KPI
✅ МОЖНО
план → только из monthly_passport_plan
факт → только из daily_progress
сопоставление → через ключ:
project_code + month_key + boq_code + iwp_id + system_label
🧩 СТРУКТУРА STREAMLIT
Экран: Исполнение / План-Факт
1. Карточки (smr_month_summary)
План всего
Approved
Факт (EV)
Вне плана
Остаток
% выполнения
2. План / Факт / Вне плана (smr_reconciliation)
3. Где сломался план (smr_plan_line_control)
4. Контроль звеньев (smr_crew_control)
🎯 СМЫСЛ
План = намерение
Факт = реальность
Система = показывает разрыв

Деньги теряются в:
- PLAN_ONLY (не сделали)
- FACT_ONLY (сделали не то)
- WRONG_CREW (нет управления)
🚀 ДАЛЬШЕ
Оставляем только 4 view:
smr_plan_line_control
smr_reconciliation
smr_month_summary
smr_crew_control
Остальные view не удаляем, но не используем
Streamlit переподключаем только к этим 4
🔥 КОНЕЧНАЯ ЦЕЛЬ
Начальник участка открывает страницу и видит:

- где потеряли деньги
- кто виноват
- что делать завтра
📌 После этого

Следующий шаг:

👉 я дам тебе SQL для этих 4 витрин
👉 и мы зачистим Supabase до понятной архитектуры
👉 потом аккуратно доведём Streamlit


# Пример анли ИИ после настройки витрин в SQL Supabase

🔴 1. Главная проблема сразу видна

Смотри на reconciliation:

MATCHED → ≈ 5.88 млн
FACT_ONLY → ≈ 1.75 млн
PLAN_ONLY → 0 (по value)

👉 Это идеально совпадает с тем, что ты говорил руками:

5.88 млн по плану
1.75 млн вне плана

✔ значит:
логика смр_reconciliation — РАБОТАЕТ ПРАВИЛЬНО

🟡 2. execution_status — это уже управленческая правда

Смотри:

NOT_STARTED → 36 строк
UNDERPERFORM → 17 строк (~3.47 млн)
WRONG_CREW → 19 строк (~2.57 млн)
OK → почти нет

👉 Это очень сильный вывод:

📌 у тебя не проблема “люди не работают”
📌 у тебя проблема:
🔴 хаотичное исполнение (WRONG_CREW)
🔴 недовыполнение (UNDERPERFORM)
🔴 фронт не запущен (NOT_STARTED)
🟢 3. smr_month_summary — вот где деньги

Ты получил:

по зданиям / дисциплинам:

есть approved_plan
есть matched_ev
есть остаток
есть % выполнения

👉 это уже:

📊 не просто аналитика
📊 это управленческая панель начальника участка

⚠️ 4. Почему у тебя раньше была “каша”

Вот корень проблемы:

❌ раньше ты делал:
агрегация = через JOIN

👉 и:

строки дублировались
фильтры ломали суммы
цифры "прыгали"
✅ сейчас:

ты сделал:

смр_reconciliation = FULL OUTER JOIN (чистый слой)
смр_plan_line_control = агрегация по плановой строке
смр_month_summary = агрегат сверху

👉 это правильная архитектура уровня EPC

🔥 5. Самое важное — что у тебя теперь есть

Ты построил 3 слоя:

🧱 1. reconciliation (истина факта)

👉 отвечает на вопрос:

что сделали не по плану?

🧱 2. plan_line_control (где сломали план)

👉 отвечает:

где косяк, в каких кодах, какими звеньями

🧱 3. month_summary (деньги)

👉 отвечает:

сколько денег сделали и сколько потеряли

💣 6. Теперь ключевой инсайт (очень важный)

Ты сам сказал:

мне нужно понять кто дров наломал

👉 вот ответ:

🔴 WRONG_CREW

👉 это:

начальник участка потерял управление

🟠 FACT_ONLY

👉 это:

мастера работают вне плана
или план — мусор

🟡 UNDERPERFORM

👉 это:

фронт есть, но не вытягивают

⚫ NOT_STARTED

👉 это:

план есть — но не исполняется

🚀 7. Что делаем дальше (правильный следующий шаг)

Теперь НЕ ТРОГАЕМ SQL

👉 ты уже сделал правильное ядро

следующий шаг = Streamlit витрина

делаем 3 блока:

1️⃣ KPI сверху
План
Approved
Выполнено по плану
Вне плана
Остаток
% исполнения
2️⃣ Таблица "Где сломался план"

из:

smr_plan_line_control

с фильтрами:

месяц
здание
дисциплина
3️⃣ Таблица "Вне плана"

из:

smr_reconciliation
where reconciliation_status = 'FACT_ONLY'
4️⃣ Таблица "Контроль звеньев"

из:

smr_crew_control
⚡ 8. Коротко по состоянию

👉 ты сейчас сделал:

✔ правильную модель план-факт
✔ разделил факт и план
✔ убрал дубли
✔ получил управленческие статусы
✔ увидел реальные проблемы площадки

🧠 Главное, что нужно понять

Ты больше не считаешь:

“сколько сделали”

Ты считаешь:

📊 ПОЧЕМУ не сделали и ГДЕ потеряли деньги