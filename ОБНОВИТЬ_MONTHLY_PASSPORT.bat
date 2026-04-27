@echo off
cd /d C:\csv_fix
call .venv\Scripts\activate.bat
python monthly_passport_sync_airtable.py
pause