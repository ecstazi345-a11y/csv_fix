import os
import subprocess
import sys

# Порядок: факт → BOQ → план месяца → трудозатраты звеньев (Crew_Register)
scripts = [
    "daily_progress_sync_upsert.py",
    "boq_sync_upsert.py",
    "monthly_passport_sync_airtable.py",
    "monthly_labor_summary_sync_upsert.py",
]


def run_script(script_name: str) -> None:
    print("\n" + "=" * 80)
    print(f"Запускаю: {script_name}")
    print("=" * 80)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run([sys.executable, script_name], env=env)

    if result.returncode != 0:
        print(f"ОШИБКА: {script_name} завершился с кодом {result.returncode}")
        sys.exit(result.returncode)

    print(f"ГОТОВО: {script_name}")


def main() -> None:
    print("СТАРТ ОБНОВЛЕНИЯ ВСЕХ ДАННЫХ (4 синка Airtable → Supabase)")

    for script in scripts:
        run_script(script)

    print("\nВСЕ 4 СИНКА УСПЕШНО ЗАВЕРШЕНЫ")


if __name__ == "__main__":
    main()
