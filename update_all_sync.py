import subprocess
import sys


scripts = [
    "daily_progress_sync_upsert.py",
    "boq_sync_upsert.py",
    "monthly_passport_sync_airtable.py",
]


def run_script(script_name: str):
    print("\n" + "=" * 80)
    print(f"Запускаю: {script_name}")
    print("=" * 80)

    result = subprocess.run([sys.executable, script_name])

    if result.returncode != 0:
        print(f"ОШИБКА: {script_name} завершился с кодом {result.returncode}")
        sys.exit(result.returncode)

    print(f"ГОТОВО: {script_name}")


def main():
    print("СТАРТ ОБНОВЛЕНИЯ ВСЕХ ДАННЫХ")

    for script in scripts:
        run_script(script)

    print("\nВСЕ СИНКИ УСПЕШНО ЗАВЕРШЕНЫ")


if __name__ == "__main__":
    main()