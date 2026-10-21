"""Human Surface Golden Path — Work Context only filter, aliases, command grammar."""

from __future__ import annotations

import unittest
from pathlib import Path

from agents.human_surface.human_review_batch import (
    BatchResolution,
    prepare_batch_from_text,
)
from agents.human_surface.human_review_command import (
    HumanReviewCommandError,
    prepare_human_review_surface,
)
from agents.human_surface.human_review_focus import (
    build_focus_set_from_work_context,
    durable_approved_composition_rows,
    filter_candidates_by_work_context,
    resolve_focus_alias,
    validate_focus_set_against_surface,
)
from agents.human_surface.human_review_intent import (
    ReviewIntentKind,
    default_review_intent_interpreter,
)
from agents.human_surface.mission_draft import WorkingContext
from agents.human_surface.result_view import (
    build_module5_result_summary_from_records,
    filter_records_by_work_context,
    module5_filter_options,
    order_records_by_candidate_ids,
    select_workspace_records,
)
from tests.test_human_surface_human_review_v2 import (
    FIXED_AT,
    RUN_ID,
    _FakeRuntime,
    _lifecycle,
)
from tests.test_human_surface_module5_result_ux import _registry

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "pages" / "53_AI_Центр_управления_агентами.py"


class GoldenPathWorkContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = _FakeRuntime(_lifecycle())
        self.surface = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        self.context = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="1",
            titles=("16160-13",),
            discipline="Автоматизация",
            systems=(),
            packages="Все",
        )

    def test_work_context_scopes_candidates(self) -> None:
        scoped = filter_candidates_by_work_context(self.surface.candidates, self.context)
        self.assertEqual(len(scoped), 5)
        self.assertTrue(all(item.facility == "16160-13" for item in scoped))
        self.assertTrue(all(item.discipline == "Автоматизация" for item in scoped))

    def test_focus_from_work_context_aliases(self) -> None:
        focus = build_focus_set_from_work_context(
            self.surface, self.context, created_at=FIXED_AT
        )
        self.assertEqual(focus.size, 5)
        cid = resolve_focus_alias(focus, 2)
        self.assertEqual(cid, focus.ordered_candidate_ids[1])
        validate_focus_set_against_surface(focus, self.surface)

    def test_stale_focus_fails_closed(self) -> None:
        from dataclasses import replace

        focus = build_focus_set_from_work_context(
            self.surface, self.context, created_at=FIXED_AT
        )
        stale = replace(focus, expected_checkpoint_id="other")
        with self.assertRaises(HumanReviewCommandError):
            validate_focus_set_against_surface(stale, self.surface)

    def test_command_cannot_affect_outside_context(self) -> None:
        focus = build_focus_set_from_work_context(
            self.surface, self.context, created_at=FIXED_AT
        )
        # Alias beyond current Work Context candidate set fails closed.
        with self.assertRaises(HumanReviewCommandError):
            prepare_batch_from_text(
                "№99 исключить. Остальные принять.",
                focus=focus,
                surface=self.surface,
            )

    def test_accept_all_grammar(self) -> None:
        interpreter = default_review_intent_interpreter()
        for phrase in (
            "добавить все",
            "все добавить",
            "принять все",
            "все принять",
            "все ок",
            "всё ок",
            "остальные добавить",
            "остальные принять",
        ):
            draft = interpreter.interpret(phrase)
            self.assertEqual(len(draft.operations), 1, phrase)
            self.assertEqual(draft.operations[0].kind, ReviewIntentKind.ACCEPT_REMAINDER, phrase)

    def test_exception_plus_remainder_preview_no_write(self) -> None:
        focus = build_focus_set_from_work_context(
            self.surface, self.context, created_at=FIXED_AT
        )
        preview = prepare_batch_from_text(
            "№2 исключить — работа в октябре не требуется.\nОстальные принять.",
            focus=focus,
            surface=self.surface,
        )
        self.assertEqual(preview.counts.exclude, 1)
        self.assertEqual(preview.counts.accept, focus.size - 1)
        self.assertEqual(self.runtime.resume_calls, 0)
        excluded = [
            op
            for op in preview.draft.operations
            if op.resolution is BatchResolution.EXCLUDE
        ]
        self.assertEqual(excluded[0].candidate_id, focus.ordered_candidate_ids[1])

    def test_decisions_survive_context_change_projection(self) -> None:
        """Surface totals are package-wide durable state, not Work Context session."""
        self.assertEqual(self.surface.not_reviewed_count, 7)
        other = WorkingContext(
            titles=("16160-13",),
            discipline="Вентиляция",
        )
        focus_a = build_focus_set_from_work_context(
            self.surface, self.context, created_at=FIXED_AT
        )
        focus_b = build_focus_set_from_work_context(
            self.surface, other, created_at=FIXED_AT
        )
        self.assertEqual(focus_a.size, 5)
        self.assertEqual(focus_b.size, 1)
        # Changing context only changes current focus size; surface package unchanged.
        again = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        self.assertEqual(len(again.candidates), 7)
        self.assertEqual(durable_approved_composition_rows(again), ())


class GoldenPathModule5InheritanceTests(unittest.TestCase):
    def test_result_inherits_work_context(self) -> None:
        registry = _registry()
        # Tag facilities on records for filter.
        from dataclasses import replace

        records = tuple(
            replace(
                item,
                facility="16160-13" if item.outcome == "CANDIDATE" else "16160-17",
                discipline="Автоматизация",
            )
            for item in registry.records
        )
        context = WorkingContext(titles=("16160-13",), discipline="Автоматизация")
        scoped = filter_records_by_work_context(records, context)
        summary = build_module5_result_summary_from_records(scoped)
        self.assertEqual(summary.proposed, sum(1 for r in scoped if r.outcome == "CANDIDATE"))
        labels = " ".join(label for _id, label, _e in module5_filter_options(summary))
        self.assertIn("Кандидаты ·", labels)
        cand = select_workspace_records(
            scoped, registry.professional, view_id="candidates"
        )
        ordered = order_records_by_candidate_ids(
            cand, tuple(item.candidate_id for item in cand)
        )
        self.assertEqual(len(ordered), len(cand))


class GoldenPathPageGuards(unittest.TestCase):
    def test_page_golden_path_shape(self) -> None:
        text = PAGE.read_text(encoding="utf-8")
        self.assertIn("_render_decision_command_panel", text)
        self.assertIn("Черновик кандидатного состава месяца", text)
        self.assertNotIn("Рабочий срез (Focus Set)", text)
        self.assertNotIn("dynamis_hr_focus_facility_", text)
        self.assertIn("submit_human_review_batch", text)
        self.assertIn("submit_human_review_decision", text)
        self.assertIn("prepare_human_review_surface", text)
        self.assertIn("Быстрая команда", text)
        # Command panel under Module 5 result analysis (not Candidates-only).
        self.assertIn("_render_decision_command_panel(surface, focus, context=context)", text)


if __name__ == "__main__":
    unittest.main()
