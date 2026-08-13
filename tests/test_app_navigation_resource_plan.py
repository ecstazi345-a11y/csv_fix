"""
Navigation contract tests for custom st.navigation (app.py).

Does NOT import app.py (would execute Streamlit). Parses NAV_SECTIONS source.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PY = ROOT / "app.py"


class ResourcePlanNavigationTests(unittest.TestCase):
    def _nav_monthly_section_block(self) -> str:
        text = APP_PY.read_text(encoding="utf-8")
        match = re.search(
            r'"▌ Контур месячного плана"\s*:\s*\[(.*?)\]',
            text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "Monthly plan NAV_SECTIONS block not found")
        return match.group(1)

    def test_page22b_in_custom_navigation(self) -> None:
        block = self._nav_monthly_section_block()
        self.assertIn("22B_План_ресурсов_месяца.py", block)

    def test_page22b_between_page22_and_page23(self) -> None:
        block = self._nav_monthly_section_block()
        pages = re.findall(r'"([^"]+\.py)"', block)
        self.assertIn("22_Admission_AI_Action_Engine.py", pages)
        self.assertIn("22B_План_ресурсов_месяца.py", pages)
        self.assertIn("23_Admission_War_Room_ограничений.py", pages)
        i22 = pages.index("22_Admission_AI_Action_Engine.py")
        i22b = pages.index("22B_План_ресурсов_месяца.py")
        i23 = pages.index("23_Admission_War_Room_ограничений.py")
        self.assertEqual(i22b, i22 + 1)
        self.assertEqual(i23, i22b + 1)

    def test_page22b_title_override(self) -> None:
        text = APP_PY.read_text(encoding="utf-8")
        self.assertIn(
            '"22B_План_ресурсов_месяца.py": "План ресурсов месяца"',
            text,
        )


if __name__ == "__main__":
    unittest.main()
