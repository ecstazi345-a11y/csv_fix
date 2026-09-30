"""
Orchestrate Airtable → Supabase syncs with truthful 4/4 reporting.

Exit 0 only when all four child syncs succeed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEALTH_DIR = ROOT / ".runtime" / "sync"
HEALTH_PATH = HEALTH_DIR / "last_sync_status.json"

# Порядок: факт → BOQ → план месяца → трудозатраты звеньев (Crew_Register)
SYNCS: list[tuple[str, str, str]] = [
    ("daily_progress", "Daily Progress", "daily_progress_sync_upsert.py"),
    ("boq", "BOQ", "boq_sync_upsert.py"),
    ("monthly_passport", "Monthly Passport", "monthly_passport_sync_airtable.py"),
    ("crew_register", "Crew Register", "monthly_labor_summary_sync_upsert.py"),
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_health_artifact(payload: dict) -> None:
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    # Atomic replace within same directory.
    fd, tmp_name = tempfile.mkstemp(
        prefix="last_sync_status_",
        suffix=".json",
        dir=str(HEALTH_DIR),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, HEALTH_PATH)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def run_script(script_name: str) -> int:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, script_name],
        env=env,
        cwd=str(ROOT),
    )
    return int(result.returncode)


def main() -> int:
    started_at = _utc_now_iso()
    total = len(SYNCS)
    results: list[dict[str, str]] = []
    failed_sync: str | None = None
    completed = 0

    print("=" * 64)
    print("AUTOMATIC DATA SYNC")
    print("=" * 64)
    print("СТАРТ ОБНОВЛЕНИЯ ВСЕХ ДАННЫХ (4 синка Airtable -> Supabase)")

    skip_remaining = False
    for key, label, script in SYNCS:
        if skip_remaining:
            results.append({"key": key, "label": label, "status": "SKIPPED"})
            print(f"{len(results)}/{total} {label:<22} SKIPPED")
            continue

        print("\n" + "=" * 80)
        print(f"Запускаю: {script}")
        print("=" * 80)
        code = run_script(script)
        if code == 0:
            completed += 1
            results.append({"key": key, "label": label, "status": "SUCCESS"})
            print(f"{len(results)}/{total} {label:<22} SUCCESS")
            print(f"ГОТОВО: {script}")
        else:
            failed_sync = key
            results.append({"key": key, "label": label, "status": "FAILED"})
            print(f"{len(results)}/{total} {label:<22} FAILED")
            print(f"ОШИБКА: {script} завершился с кодом {code}")
            skip_remaining = True

    finished_at = _utc_now_iso()
    overall_ok = failed_sync is None and completed == total
    overall_status = "SUCCESS" if overall_ok else "FAILED"
    exit_code = 0 if overall_ok else 1

    print("\n" + "=" * 64)
    for index, row in enumerate(results, start=1):
        print(f"{index}/{total} {row['label']:<22} {row['status']}")
    print(f"OVERALL RESULT: {overall_status}")
    print(f"COMPLETED: {completed}/{total}")
    if failed_sync:
        failed_label = next(r["label"] for r in results if r["key"] == failed_sync)
        print(f"FAILED: {failed_label}")
    else:
        print("FAILED: —")
    print(f"EXIT CODE: {exit_code}")
    print("=" * 64)

    if overall_ok:
        print("\nВСЕ 4 СИНКА УСПЕШНО ЗАВЕРШЕНЫ")

    artifact = {
        "started_at": started_at,
        "finished_at": finished_at,
        "overall_status": overall_status,
        "completed": completed,
        "total": total,
        "failed_sync": failed_sync,
        "results": [
            {"key": r["key"], "status": r["status"]} for r in results
        ],
    }
    try:
        write_health_artifact(artifact)
        print(f"HEALTH: {HEALTH_PATH}")
    except Exception as exc:
        print(f"HEALTH WRITE FAILED: {type(exc).__name__}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
