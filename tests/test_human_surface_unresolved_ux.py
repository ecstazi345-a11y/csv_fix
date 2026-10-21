"""Unresolved-first Human Review UX — Work Context drives the operable list."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.human_surface.human_review_command import (
    HumanReviewCandidateContext,
    HumanReviewSurfaceSnapshot,
)
from agents.human_surface.human_review_focus import (
    build_focus_set_from_work_context,
    recorded_decision_table_dicts,
    unresolved_context_groups,
    unresolved_focus_rows,
    unresolved_table_dicts,
)
from agents.human_surface.mission_draft import WorkingContext

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "pages" / "53_AI_Центр_управления_агентами.py"
APP = REPO_ROOT / "app.py"
FIXED_AT = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _cand(
    cid: str,
    *,
    facility: str,
    discipline: str,
    label: str,
    system: str = "SYS-1",
    iwp: str = "IWP-1",
    boq: str | None = None,
    planned: float = 0.0,
    proposed: float = 10.0,
) -> HumanReviewCandidateContext:
    return HumanReviewCandidateContext(
        candidate_id=cid,
        facility=facility,
        discipline=discipline,
        system=system,
        iwp=iwp,
        boq_code=boq or f"BOQ-{cid}",
        name=f"Work {cid}",
        unit="м",
        remaining_qty=planned + proposed,
        already_planned_qty=planned,
        constructor_proposed_qty=proposed,
        current_decision_label=label,
        warning_lines=(),
        human_approved_qty=proposed if label == "ПРИНЯТО" else None,
    )


def _candidates() -> tuple[HumanReviewCandidateContext, ...]:
    items: list[HumanReviewCandidateContext] = []
    # 13 accepted + 2 deferred (reviewed), 11 unresolved — live package shape.
    for i in range(13):
        items.append(
            _cand(
                f"acc-{i}",
                facility="16160-13",
                discipline="Автоматизация",
                label="ПРИНЯТО",
            )
        )
    for i in range(2):
        items.append(
            _cand(
                f"def-{i}",
                facility="16160-13",
                discipline="Автоматизация",
                label="ПЕРЕНЕСЕНО",
            )
        )
    # Unresolved: 5 in Automation@16160-13, 2 Ventilation@16160-13, 4 Automation@16160-17.
    for i in range(5):
        items.append(
            _cand(
                f"un-auto-{i}",
                facility="16160-13",
                discipline="Автоматизация",
                label="НЕ РАССМОТРЕНО",
                planned=3.0 if i == 0 else 0.0,
            )
        )
    for i in range(2):
        items.append(
            _cand(
                f"un-vent-{i}",
                facility="16160-13",
                discipline="Вентиляция",
                label="НЕ РАССМОТРЕНО",
                system="SYS-V",
                iwp="IWP-V",
            )
        )
    for i in range(4):
        items.append(
            _cand(
                f"un-17-{i}",
                facility="16160-17",
                discipline="Автоматизация",
                label="НЕ РАССМОТРЕНО",
                system="SYS-17",
            )
        )
    return tuple(items)


def _surface() -> HumanReviewSurfaceSnapshot:
    cands = _candidates()
    return HumanReviewSurfaceSnapshot(
        run_id="run-a0c70277-486b-439d-a6be-7599411ffc37",
        mission_id="mission",
        package_id="3ef26b0e-1f5c-41ef-a06e-e39758749273",
        professional_status="WAITING_FOR_HUMAN_REVIEW",
        expected_checkpoint_id="ckpt",
        interrupt_id="int",
        candidates=cands,
        reviewed_count=15,
        accepted_count=13,
        changed_qty_count=0,
        excluded_count=0,
        deferred_count=2,
        needs_data_count=0,
        not_reviewed_count=11,
    )


class UnresolvedUxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.surface = _surface()

    def test_1_unresolved_visible_with_focus_aliases(self) -> None:
        focus = build_focus_set_from_work_context(
            self.surface,
            WorkingContext(titles=("16160-13",), discipline="Автоматизация"),
            created_at=FIXED_AT,
        )
        rows = unresolved_table_dicts(self.surface, focus)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r["Состояние"] == "ТРЕБУЕТ РЕШЕНИЯ" for r in rows))
        # Aliases correspond to Focus order for the same candidate_ids.
        focus_rows_unresolved = unresolved_focus_rows(self.surface, focus)
        self.assertEqual(
            [r["candidate_id"] for r in rows],
            [r.candidate_id for r in focus_rows_unresolved],
        )
        self.assertEqual(
            [r["№"] for r in rows],
            [str(r.alias_number) for r in focus_rows_unresolved],
        )
        by_id = {r["candidate_id"]: r for r in rows}
        self.assertEqual(by_id["un-auto-0"]["Тип кандидата"], "Доп. объём")
        self.assertEqual(by_id["un-auto-1"]["Тип кандидата"], "Новые возможности")
        self.assertEqual(by_id["un-auto-0"]["Уже запланировано"], "3")

    def test_2_unresolved_list_obeys_work_context(self) -> None:
        vent = build_focus_set_from_work_context(
            self.surface,
            WorkingContext(titles=("16160-13",), discipline="Вентиляция"),
            created_at=FIXED_AT,
        )
        rows = unresolved_table_dicts(self.surface, vent)
        self.assertEqual(
            {r["candidate_id"] for r in rows}, {"un-vent-0", "un-vent-1"}
        )
        self.assertTrue(all(r["Дисциплина"] == "Вентиляция" for r in rows))

        title17 = build_focus_set_from_work_context(
            self.surface,
            WorkingContext(titles=("16160-17",), discipline="Автоматизация"),
            created_at=FIXED_AT,
        )
        rows17 = unresolved_table_dicts(self.surface, title17)
        self.assertEqual(len(rows17), 4)
        self.assertTrue(all(r["Титул"] == "16160-17" for r in rows17))

    def test_3_package_wide_unresolved_remains_11(self) -> None:
        self.assertEqual(self.surface.not_reviewed_count, 11)
        groups = unresolved_context_groups(self.surface)
        self.assertEqual(sum(int(g["Осталось"]) for g in groups), 11)
        keys = {(g["Титул"], g["Дисциплина"]) for g in groups}
        self.assertIn(("16160-13", "Вентиляция"), keys)
        self.assertIn(("16160-17", "Автоматизация"), keys)

    def test_4_recorded_decisions_separate_from_unresolved(self) -> None:
        recorded = recorded_decision_table_dicts(self.surface)
        self.assertEqual(len(recorded), 15)
        statuses = [r["Статус решения"] for r in recorded]
        self.assertEqual(statuses.count("ПРИНЯТО"), 13)
        self.assertEqual(statuses.count("ПЕРЕНЕСЕНО"), 2)
        recorded_ids = {r["candidate_id"] for r in recorded}
        self.assertFalse(any(cid.startswith("un-") for cid in recorded_ids))

    def test_5_zero_unresolved_context_still_locates_others(self) -> None:
        # A context with no candidates: unresolved list empty, groups still show 11.
        empty_focus = build_focus_set_from_work_context(
            self.surface,
            WorkingContext(titles=("99999-00",), discipline="Нет такой"),
            created_at=FIXED_AT,
        )
        self.assertEqual(unresolved_table_dicts(self.surface, empty_focus), ())
        groups = unresolved_context_groups(self.surface)
        self.assertEqual(sum(int(g["Осталось"]) for g in groups), 11)


class WorkspaceLayoutNavigationGuards(unittest.TestCase):
    def test_navigation_protected_and_wide_in_app(self) -> None:
        app = APP.read_text(encoding="utf-8")
        self.assertIn('st.set_page_config(layout="wide")', app)
        self.assertIn("st.navigation", app)
        self.assertIn("NAV_SECTIONS", app)
        page = PAGE.read_text(encoding="utf-8")
        self.assertNotIn("st.navigation", page)
        self.assertNotRegex(page, r"st\.set_page_config\s*\(")
        config = (REPO_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        self.assertNotIn("showSidebarNavigation = false", config)

    def test_page_unresolved_first_ordering(self) -> None:
        text = PAGE.read_text(encoding="utf-8")
        unresolved_idx = text.index("Требуют решения в текущем рабочем контексте")
        recorded_idx = text.index("Принятые решения", unresolved_idx)
        draft_idx = text.index("Черновик кандидатного состава месяца", unresolved_idx)
        self.assertLess(unresolved_idx, recorded_idx)
        self.assertLess(recorded_idx, draft_idx)
        self.assertIn("Требуют решения:", text)
        self.assertIn("Где остались решения", text)
        self.assertIn("В текущем рабочем контексте нерешённых кандидатов нет", text)
        self.assertIn("unresolved_table_dicts", text)


if __name__ == "__main__":
    unittest.main()
