# Новый компьютер → запуск csv_fix

> **Время:** ~15–20 минут.  
> **Путь проекта (рекомендуется):** `C:\csv_fix`  
> **Репозиторий:** https://github.com/ecstazi345-a11y/csv_fix

---

## Чеклист

- [ ] **1. Установить Cursor**  
  Скачать с [cursor.com](https://cursor.com) и установить.

- [ ] **2. Установить Git** (если ещё нет)  
  [git-scm.com](https://git-scm.com) — нужен для `git clone`.

- [ ] **3. Установить Python 3.12** (если ещё нет)  
  [python.org](https://www.python.org/downloads/) — при установке включить **«Add Python to PATH»**.

- [ ] **4. Клонировать репозиторий**

```powershell
cd C:\
git clone https://github.com/ecstazi345-a11y/csv_fix.git csv_fix
cd C:\csv_fix
```

> **Не клонируйте** внутрь уже существующей `C:\csv_fix\csv_fix` — получится сломанный пустой git (см. `AI_WORKLOG.md`).

- [ ] **5. Скопировать `.env` вручную**  
  Файл **не в git**. Скопируйте с рабочего ПК (флешка, облако, менеджер паролей) в корень:

```
C:\csv_fix\.env
```

Минимум для витрины: `SUPABASE_URL`, `SUPABASE_KEY`.  
Для синков Airtable: `AIRTABLE_TOKEN`, `AIRTABLE_BASE_ID` и ID таблиц (см. `PROJECT_CONTEXT.md` §7).

- [ ] **6. Создать и активировать виртуальное окружение**

```powershell
cd C:\csv_fix
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Если PowerShell блокирует скрипты (один раз на ПК):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

- [ ] **7. Установить зависимости**

```powershell
pip install -r requirements.txt
pip check
```

- [ ] **8. Проверить подключение к Supabase** (опционально)

```powershell
.\.venv\Scripts\python.exe -c "from services.supabase_client import get_client; get_client(); print('Supabase: OK')"
```

- [ ] **9. Запустить Streamlit**

```powershell
cd C:\csv_fix
.\.venv\Scripts\streamlit.exe run app.py
```

- [ ] **10. Открыть витрину в браузере**  
  **http://localhost:8501**

- [ ] **11. Открыть проект в Cursor**  
  `File → Open Folder` → `C:\csv_fix`

- [ ] **12. Восстановить контекст для AI-агента**  
  В новом чате Cursor вставьте:

```
Ты работаешь с проектом csv_fix.
Сначала прочитай AGENT_MEMORY.md, NEXT_STEPS.md и PROJECT_CONTEXT.md.
Кратко восстанови контекст и скажи, какой следующий шаг по NEXT_STEPS.md.
```

---

## После запуска (по необходимости)

**Обновить данные из Airtable:**

```powershell
cd C:\csv_fix
.\ОБНОВИТЬ_ВСЕ_ДАННЫЕ.bat
```

или:

```powershell
.\.venv\Scripts\python.exe update_all_sync.py
```

---

## Если что-то не работает

| Симптом | Что проверить |
|---------|----------------|
| Страницы пустые / ошибка Supabase | `.env` в корне, ключи верные |
| `streamlit` не найден | Активирован `.venv`, путь `.\.venv\Scripts\streamlit.exe` |
| Синк падает | Airtable-переменные в `.env` |
| Порт занят | Закрыть другой Streamlit или указать `--server.port 8502` |

Подробнее: `PROJECT_CONTEXT.md` §6–7, `AGENT_MEMORY.md`.

---

*Создано: 2026-05-15 (P0.2)*
