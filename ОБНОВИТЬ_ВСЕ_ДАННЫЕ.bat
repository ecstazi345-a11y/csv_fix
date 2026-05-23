@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Активирую виртуальное окружение...
call .venv\Scripts\activate.bat

set PYTHONIOENCODING=utf-8
echo Запускаю 4 синка: Daily Progress, BOQ, Monthly Passport, Crew_Register...
python update_all_sync.py

echo.
echo ОБНОВЛЕНИЕ ЗАВЕРШЕНО
pause