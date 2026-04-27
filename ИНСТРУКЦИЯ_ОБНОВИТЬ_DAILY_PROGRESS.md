# Как обновить Daily Progress из Airtable в Supabase

## Что делает скрипт

Берёт данные из Airtable Daily Progress и обновляет таблицу Supabase:

Airtable → daily_progress_raw → daily_progress_active → агрегации → Streamlit

## Как запустить вручную

Открыть VS Code.

Открыть папку:

C:\csv_fix

В терминале выполнить:

```powershell
.venv\Scripts\Activate.ps1
python daily_progress_sync_upsert.py

# После успешного запуска должно быть:
Читаю Airtable...
Получено строк из Airtable: ...
Делаю upsert в Supabase...
Готово.

# Проверка в Supabase
select count(*) from daily_progress_raw;
select count(*) from daily_progress_active;

# Количество строк должно совпадать с Airtable.

---

## 2. Сделай кнопку-запуск

В папке `C:\csv_fix` создай файл:

```text
ОБНОВИТЬ_DAILY_PROGRESS.bat

# Вставь туда:

@echo off
cd /d C:\csv_fix
call .venv\Scripts\activate.bat
python daily_progress_sync_upsert.py
pause

# Теперь тебе не надо помнить команды.

# Просто два раза кликаешь:

ОБНОВИТЬ_DAILY_PROGRESS.bat

И Daily Progress обновляется.

# 3. Автоматическое обновление

Да, потом сделаем автоматом через Планировщик заданий Windows, например каждые 30 минут:

Airtable обновился
↓
каждые 30 минут запускается скрипт
↓
Supabase обновляется
↓
Streamlit показывает свежие данные

# ⚠️ Важно

Если не обновлять:

→ данные в Streamlit устаревают
→ план-факт становится неправильным
→ EV / деньги искажаются

# 🧭 Правильная дисциплина

Каждый день:

👉 нажать ОБНОВИТЬ_DAILY_PROGRESS.bat
или
👉 настроить автообновление (будет позже)


# 🔥 Архитектура

Airtable (ввод)
↓
daily_progress_raw (истина)
↓
daily_progress_active
↓
AGG
↓
Streamlit