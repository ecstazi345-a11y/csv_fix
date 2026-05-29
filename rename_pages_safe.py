"""Safe rename of Streamlit pages — no emoji, two-phase with Test-Path checks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(r"c:\csv_fix")
PAGES = ROOT / "pages"

RENAMES: dict[str, str] = {
    "05_Паспорт_месяца.py": "10_Planning_Паспорт_месяца.py",
    "12_AI_Диагностика_плана.py": "11_Planning_AI_Диагностика_плана.py",
    "14_Конструктор_месячного_плана.py": "12_Planning_Конструктор_месячного_плана.py",
    "15_Контур_допуска_месячного_плана.py": "20_Admission_Контур_допуска_месячного_плана.py",
    "16_Управление_ограничениями_месячного_плана.py": (
        "21_Admission_Управление_ограничениями_месячного_плана.py"
    ),
    "13_AI_Action_Engine.py": "22_Admission_AI_Action_Engine.py",
    "06_Исполнение.py": "30_Execution_Исполнение.py",
    "07_Счётчик_звена.py": "31_Execution_Счётчик_звена.py",
    "07_Качество_данных.py": "32_Execution_Качество_данных.py",
    "08_Приемка_и_признание.py": "40_Commercial_Приёмка_и_признание.py",
    "09_Контроль_потерь.py": "41_Commercial_Контроль_потерь.py",
    "10_Экономика.py": "42_Commercial_Экономика.py",
    "11_Уведомления_заказчику.py": "43_Commercial_Уведомления_заказчику.py",
    "12_AI_Агенты.py": "50_AI_Агенты.py",
}

WAR_ROOM_FINAL = "23_Admission_War_Room_ограничений.py"
WAR_ROOM_STUB = '''import streamlit as st

st.set_page_config(layout="wide")

st.title("War Room ограничений")
st.caption("Совещания по ограничениям месячного плана — в разработке")

st.markdown(
    """
Страница будет использоваться для совещаний по ограничениям:
ТОП блокировок, просрочки, владельцы, стоимость под риском.

Пока без бизнес-логики.
"""
)
'''


def safe_rename(src: Path, dst: Path) -> bool:
    if not src.exists():
        print(f"SKIP: source not found -> {src.name!r}")
        return False
    if dst.exists():
        print(f"SKIP: target exists -> {dst.name!r}")
        return False
    src.rename(dst)
    print(f"OK: {src.name!r} -> {dst.name!r}")
    return True


def main() -> int:
    if not PAGES.is_dir():
        print(f"ERROR: pages dir missing: {PAGES}")
        return 1

    print("=== War Room: normalize filename ===")
    war_final = PAGES / WAR_ROOM_FINAL
    if not war_final.exists():
        for candidate in PAGES.glob("*War_Room*.py"):
            if candidate.name != WAR_ROOM_FINAL:
                safe_rename(candidate, war_final)
                break

    print("\n=== Phase 1: temp names ===")
    for old_name, new_name in RENAMES.items():
        src = PAGES / old_name
        final = PAGES / new_name
        tmp = PAGES / f"__renaming__{new_name}"
        if not src.exists():
            continue
        if final.exists():
            print(f"SKIP phase1: final exists -> {new_name}")
            continue
        safe_rename(src, tmp)

    print("\n=== Phase 2: final names ===")
    for tmp in sorted(PAGES.glob("__renaming__*.py")):
        final = PAGES / tmp.name.removeprefix("__renaming__")
        safe_rename(tmp, final)

    if not war_final.exists():
        war_final.write_text(WAR_ROOM_STUB, encoding="utf-8")
        print(f"CREATED: {WAR_ROOM_FINAL}")

    print("\n=== pages/ ===")
    for p in sorted(PAGES.glob("*.py")):
        print(repr(p.name))

    print("\n=== py_compile ===")
    compile_targets = [
        ROOT / "app.py",
        PAGES / "20_Admission_Контур_допуска_месячного_плана.py",
        PAGES / "21_Admission_Управление_ограничениями_месячного_плана.py",
        PAGES / WAR_ROOM_FINAL,
    ]
    for target in compile_targets:
        if target.exists():
            subprocess.run([sys.executable, "-m", "py_compile", str(target)], check=True)
            print(f"COMPILE OK: {target.name}")
        else:
            print(f"COMPILE SKIP (missing): {target.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
