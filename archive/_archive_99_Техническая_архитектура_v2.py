# ============================================================
# ARCHIVED — не Streamlit page (вне pages/).
# Содержимое перенесено в конструктор v2:
#   pages/10B_Конструктор_месячного_плана.py → модуль 4
# Исходник handbook:
#   docs/v2_technical_architecture_handbook.py
#
# Этот файл сохранён как reference snapshot. Не показывается в sidebar.
# ============================================================

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from docs.v2_technical_architecture_handbook import (  # noqa: E402
    inject_doc_styles,
    render_header,
    render_v2_technical_architecture_handbook,
)

# Standalone preview (не запускать как Streamlit page):
#   python archive/_archive_99_Техническая_архитектура_v2.py
if __name__ == "__main__":
    print("Handbook module: docs/v2_technical_architecture_handbook.py")
    print("Rendered in: pages/10B_Конструктор_месячного_плана.py (module 4)")
