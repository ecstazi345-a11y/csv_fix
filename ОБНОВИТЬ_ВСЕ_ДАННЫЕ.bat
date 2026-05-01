@echo off
chcp 65001 >nul
cd /d C:\csv_fix

echo Активирую виртуальное окружение...
call .venv\Scripts\activate.bat

echo Запускаю обновление всех данных...
python update_all_sync.py

echo.
echo ОБНОВЛЕНИЕ ЗАВЕРШЕНО
pause