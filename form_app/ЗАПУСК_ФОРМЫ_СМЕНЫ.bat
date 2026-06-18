@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8

echo Запуск формы ввода смены (порт 8502)...
streamlit run form_app/daily_progress_form_app.py --server.port 8502

pause
