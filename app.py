import re

import streamlit as st
from pathlib import Path

from streamlit.source_util import page_icon_and_name

st.set_page_config(layout="wide")

PAGES_DIR = Path(__file__).parent / "pages"

MENU_TITLE_OVERRIDES: dict[str, str] = {
    "01A_Engineering_Data_Architecture_Архитектура_данных_РД.py": "Архитектура данных РД",
    "10B_Конструктор_месячного_плана.py": "Конструктор месячного плана",
    "12_Planning_Паспорт_месяца.py": "Паспорт месячного плана",
    "21_Admission_Управление_ограничениями_месячного_плана.py": "Допуск месячного плана",
    "22_Admission_AI_Action_Engine.py": "Экономика месячного плана",
    "23_Admission_War_Room_ограничений.py": "Управление решениями по месячному плану",
    "30_Execution_Исполнение.py": "Прогресс",
    "33_Execution_Выгрузка_Daily_Progress_ПТО.py": "ОЖР",
    "40_Commercial_Приёмка_и_признание.py": "Инспекция и приёмка работ",
    "50_AI_Агенты.py": "Агенты",
}

_TECH_PREFIX_RE = re.compile(
    r"^(Planning|Admission|Execution|Commercial)(?:_| )+",
    re.IGNORECASE,
)

NAV_TOP_PAGES: list[str] = [
    "01A_Engineering_Data_Architecture_Архитектура_данных_РД.py",
    "02_ВОР_по_РД.py",
]

NAV_SECTIONS: dict[str, list[str]] = {
    "▌ Контур месячного плана": [
        "10B_Конструктор_месячного_плана.py",
        "21_Admission_Управление_ограничениями_месячного_плана.py",
        "22_Admission_AI_Action_Engine.py",
        "23_Admission_War_Room_ограничений.py",
        "12_Planning_Паспорт_месяца.py",
    ],
    "▌ Контур исполнения": [
        "30_Execution_Исполнение.py",
        "31_Execution_Счётчик_звена.py",
        "32_Execution_Качество_данных.py",
        "33_Execution_Выгрузка_Daily_Progress_ПТО.py",
    ],
    "▌ Контур признания": [
        "40_Commercial_Приёмка_и_признание.py",
        "41_Commercial_Контроль_потерь.py",
        "42_Commercial_Экономика.py",
        "43_Commercial_Уведомления_заказчику.py",
    ],
    "▌ Контур агентной оркестрации": [
        "50_AI_Агенты.py",
    ],
}

HIDDEN_PAGE_FILES: frozenset[str] = frozenset(
    {
        "01_Главная.py",
        "_10_Planning_Конструктор_месячного_плана.py",
        "_11_Planning_AI_Диагностика_плана.py",
        "_20_Admission_Контур_допуска_месячного_плана.py",
    }
)


def _render_home() -> None:
    st.title("AI Construction Control Center")

    st.caption("План → Допуск → Исполнение → Приемка → Деньги")

    st.markdown(
        """
## Единая витрина управления строительным проектом

Система показывает ключевую цепочку управления СМР:

- какие работы включены в план
- какой фронт допущен к выполнению
- какие работы реально выполнены
- где есть отклонения от плана
- какие объемы готовы к приемке и признанию
- где возникают потери, риски и основания для уведомлений заказчику

---

### Рабочие разделы

Используйте меню слева:

1. **Главная** — обзор системы  
2. **Допуск фронта** — готовность работ к выполнению  
3. **Допуск к оплате** — проверка возможности признания работ  
4. **Паспорт месяца** — месячный план работ  
5. **Исполнение** — план / факт / отклонения  
6. **Приемка и признание** — инспекция и подтверждение объемов  
7. **Контроль потерь** — причины отклонений и убытков  
8. **Экономика** — деньги, затраты, маржа  
9. **Уведомления заказчику** — фиксация событий и уведомления  
10. **AI-Агенты** — автономные цифровые управляющие: контроль процессов, анализ отклонений и усиление управленческих решений
"""
    )


def _default_menu_title(page_path: Path) -> str:
    _, inferred_name = page_icon_and_name(page_path)
    cleaned = _TECH_PREFIX_RE.sub("", inferred_name)
    return cleaned.replace("_", " ").strip()


def _page_from_file(page_path: Path, *, hidden: bool = False) -> st.Page:
    _, url_path = page_icon_and_name(page_path)
    title = MENU_TITLE_OVERRIDES.get(page_path.name, _default_menu_title(page_path))
    return st.Page(
        page_path,
        title=title,
        url_path=url_path,
        visibility="hidden" if hidden else "visible",
    )


def _pages_from_filenames(filenames: list[str]) -> list[st.Page]:
    pages: list[st.Page] = []
    for filename in filenames:
        page_path = PAGES_DIR / filename
        if page_path.is_file():
            pages.append(_page_from_file(page_path))
    return pages


def _hidden_pages() -> list[st.Page]:
    return [
        _page_from_file(PAGES_DIR / filename, hidden=True)
        for filename in sorted(HIDDEN_PAGE_FILES)
        if (PAGES_DIR / filename).is_file()
    ]


def _build_navigation_sections() -> dict[str, list[st.Page]]:
    sections: dict[str, list[st.Page]] = {
        "": [st.Page(_render_home, title="Главная", default=True), *_pages_from_filenames(NAV_TOP_PAGES)],
    }

    for section_name, filenames in NAV_SECTIONS.items():
        sections[section_name] = _pages_from_filenames(filenames)

    sections["▌ Контур агентной оркестрации"].extend(_hidden_pages())
    return sections


pg = st.navigation(_build_navigation_sections())
pg.run()
