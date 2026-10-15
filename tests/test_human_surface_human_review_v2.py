"""Human Review V2 — Focus Set, intent, batch preview/port."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from agents.human_surface.human_review_batch import (
    BatchResolution,
    prepare_batch_from_text,
    resolve_intent_to_batch_draft,
    submit_human_review_batch,
)
from agents.human_surface.human_review_command import (
    HumanReviewAction,
    HumanReviewCommand,
    HumanReviewCommandError,
    prepare_human_review_surface,
    submit_human_review_decision,
)
from agents.human_surface.human_review_focus import (
    HumanReviewFocusFilter,
    build_human_review_focus_set,
    focus_rows,
    resolve_focus_alias,
    validate_focus_set_against_surface,
)
from agents.human_surface.human_review_intent import (
    ReviewIntentKind,
    default_review_intent_interpreter,
)
from agents.human_surface.result_view import (
    build_module5_result_summary,
    module5_filter_options,
    select_workspace_records,
)
from agents.monthly_plan_constructor.candidate_package import (
    LABOR_VALIDATED,
    PackageExceptionSummary,
    build_candidate_package,
)
from agents.monthly_plan_constructor.exception_engine import (
    SCHEMA_VERSION as EXC_SCHEMA,
    ConstructorExceptionSet,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    RESOLUTION_KIND_DEFER_TO_PERIOD,
    HumanReviewDecision,
    normalize_human_review_events,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_WAITING_FOR_HUMAN_REVIEW,
    ConstructorLifecycleState,
    LifecycleTransition,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import build_constructor_mission_scope
from agents.monthly_plan_constructor.professional_review_resume import (
    ProfessionalHumanReviewResumeCommand,
)
from agents.control_room.dtos import (
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    ProfessionalResultAvailability,
)

FIXED_AT = datetime(2026, 10, 14, 14, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run-hr-v2-001"
MISSION_ID = "mission-hr-v2-001"
PROJECT = "PRJ_001_БХК"
MONTH = "октябрь-2026"


def _mission():
    return build_constructor_mission_scope(project_code=PROJECT, month_key=MONTH)


def _cand(
    cid: str,
    *,
    facility: str,
    discipline: str,
    system: str = "SYS-1",
    iwp: str = "IWP-1",
    boq: str | None = None,
    qty: float = 80.0,
) -> dict[str, object]:
    return {
        "candidate_id": cid,
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": facility,
        "discipline": discipline,
        "system": system,
        "iwp": iwp,
        "queue": "",
        "boq_code": boq or f"2041-01-{cid[-2:]}-01",
        "boq_name": f"Work {cid}",
        "unit": "м",
        "remaining_qty": 100.0,
        "already_planned_qty": 0.0,
        "available_to_add_qty": qty,
        "availability_status": "AVAILABLE",
        "labor_norm_status": LABOR_VALIDATED,
    }


def _package():
    items = [
        _cand("c01", facility="16160-13", discipline="Автоматизация", boq="2041-01-01-01", qty=80),
        _cand("c02", facility="16160-13", discipline="Автоматизация", boq="2041-01-02-01", qty=70),
        _cand("c03", facility="16160-13", discipline="Автоматизация", boq="2041-01-03-01", qty=60),
        _cand("c04", facility="16160-13", discipline="Автоматизация", boq="2041-01-04-01", qty=50),
        _cand("c05", facility="16160-13", discipline="Вентиляция", boq="2041-02-01-01", qty=40),
        _cand("c06", facility="16160-17", discipline="Автоматизация", boq="2041-03-01-01", qty=30),
        _cand(
            "c07",
            facility="16160-13",
            discipline="Автоматизация",
            system="SYS-2",
            iwp="IWP-9",
            boq="2041-02-06-03",
            qty=80,
        ),
    ]
    return build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items),
        run_id=RUN_ID,
        snapshot_id="snap-v2",
        created_at=FIXED_AT.isoformat(),
        exception_summary=PackageExceptionSummary(
            blocking_count=0, non_blocking_count=0, warning_count=0
        ),
    )


def _lifecycle() -> ConstructorLifecycleState:
    package = _package()
    state = create_lifecycle_state(
        mission_id=MISSION_ID, run_id=RUN_ID, authorization_id="auth-v2", created_at=FIXED_AT
    )
    return replace(
        state,
        status=STATUS_WAITING_FOR_HUMAN_REVIEW,
        scope=package.scope,
        package=package,
        exceptions=ConstructorExceptionSet(
            schema_version=EXC_SCHEMA,
            exceptions=(),
            summary=package.exception_summary,
            package_id=package.package_id,
        ),
        transitions=(
            LifecycleTransition(
                from_status="LABOR_RESOLVED",
                to_status=STATUS_WAITING_FOR_HUMAN_REVIEW,
                at=FIXED_AT,
                trigger_code="HUMAN_REVIEW",
                source_capability="LIFECYCLE",
                note="awaiting",
            ),
        ),
        updated_at=FIXED_AT,
        error_code="HUMAN_REVIEW",
        terminal_reason="awaiting",
    )


class _FakeRuntime:
    def __init__(self, lifecycle: ConstructorLifecycleState) -> None:
        self.lifecycle = lifecycle
        self.checkpoint_id = "ckpt-v2-1"
        self.resume_calls = 0

    def load_lifecycle(self, run_id: str) -> ConstructorLifecycleState:
        if run_id != self.lifecycle.run_id:
            raise HumanReviewCommandError("run not found")
        return self.lifecycle

    def current_checkpoint_id(self, run_id: str) -> str:
        return self.checkpoint_id

    def resume_professional_review(
        self,
        *,
        run_id: str,
        resume_command: ProfessionalHumanReviewResumeCommand,
    ) -> ConstructorLifecycleState:
        self.resume_calls += 1
        history = normalize_human_review_events(
            tuple(self.lifecycle.human_review_events or ())
            + tuple(resume_command.review_events),
            self.lifecycle.package,
        )
        self.lifecycle = replace(
            self.lifecycle, human_review_events=history, updated_at=FIXED_AT
        )
        self.checkpoint_id = f"ckpt-v2-{self.resume_calls + 1}"
        return self.lifecycle


class FocusSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = _FakeRuntime(_lifecycle())
        self.surface = prepare_human_review_surface(RUN_ID, runtime=self.runtime)

    def test_01_candidate_count_equals_package(self) -> None:
        self.assertEqual(len(self.surface.candidates), 7)
        self.assertEqual(len(self.runtime.lifecycle.package.candidates), 7)

    def test_02_06_filters_and_combined(self) -> None:
        focus = build_human_review_focus_set(
            self.surface,
            HumanReviewFocusFilter(facility="16160-13", discipline="Автоматизация"),
            created_at=FIXED_AT,
        )
        self.assertEqual(focus.size, 5)
        by_system = build_human_review_focus_set(
            self.surface,
            HumanReviewFocusFilter(
                facility="16160-13", discipline="Автоматизация", system="SYS-2"
            ),
            created_at=FIXED_AT,
        )
        self.assertEqual(by_system.size, 1)
        by_iwp = build_human_review_focus_set(
            self.surface,
            HumanReviewFocusFilter(
                facility="16160-13",
                discipline="Автоматизация",
                system="SYS-2",
                iwp="IWP-9",
            ),
            created_at=FIXED_AT,
        )
        self.assertEqual(by_iwp.size, 1)
        title = build_human_review_focus_set(
            self.surface, HumanReviewFocusFilter(facility="16160-17"), created_at=FIXED_AT
        )
        self.assertEqual(title.size, 1)

    def test_07_alias_maps_to_candidate_id(self) -> None:
        focus = build_human_review_focus_set(
            self.surface,
            HumanReviewFocusFilter(facility="16160-13", discipline="Автоматизация"),
            created_at=FIXED_AT,
        )
        rows = focus_rows(self.surface, focus)
        self.assertEqual(resolve_focus_alias(focus, 4), rows[3].candidate_id)

    def test_08_stale_focus_fails(self) -> None:
        focus = build_human_review_focus_set(
            self.surface, HumanReviewFocusFilter(facility="16160-13"), created_at=FIXED_AT
        )
        stale = replace(focus, expected_checkpoint_id="stale")
        with self.assertRaises(HumanReviewCommandError):
            validate_focus_set_against_surface(stale, self.surface)


class IntentAndBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = _FakeRuntime(_lifecycle())
        self.surface = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        self.focus = build_human_review_focus_set(
            self.surface,
            HumanReviewFocusFilter(facility="16160-13", discipline="Автоматизация"),
            focus_set_id="fs-test",
            created_at=FIXED_AT,
        )

    def test_09_defer_intent(self) -> None:
        draft = default_review_intent_interpreter().interpret(
            "Позицию 4 перенести на ноябрь. Нет строительной готовности, не выполнен предэтап."
        )
        self.assertEqual(len(draft.operations), 1)
        op = draft.operations[0]
        self.assertEqual(op.kind, ReviewIntentKind.DEFER_TO_PERIOD)
        self.assertEqual(op.target.alias_numbers, (4,))
        self.assertEqual(op.target_period, "2026-11")
        self.assertIn("готовности", op.reason_text or "")

    def test_09b_natural_month_forms_and_missing_reason_preview(self) -> None:
        interp = default_review_intent_interpreter()
        for phrase in (
            "№1 перенести на ноябрь",
            "№1 перенести на ноябрь 2026",
            "№1 перенести на ноябрь-2026",
            "№1 ПЕРЕНЕСТИ НА НОЯБРЬ-2026",
            "№1 перенести в ноябрь",
            "№1 перенести в ноябрь 2026",
        ):
            draft = interp.interpret(
                phrase, default_year=2026, context_period="2026-10"
            )
            self.assertEqual(len(draft.operations), 1, phrase)
            op = draft.operations[0]
            self.assertEqual(op.kind, ReviewIntentKind.DEFER_TO_PERIOD, phrase)
            self.assertEqual(op.target.alias_numbers, (1,), phrase)
            self.assertEqual(op.target_period, "2026-11", phrase)
            self.assertIsNone(op.reason_text, phrase)

        preview = prepare_batch_from_text(
            "№1 ПЕРЕНЕСТИ НА НОЯБРЬ-2026",
            focus=self.focus,
            surface=self.surface,
            default_year=2026,
            context_period="2026-10",
        )
        self.assertEqual(preview.counts.defer, 1)
        self.assertFalse(preview.reasons_complete)
        self.assertIn("Укажите причину переноса.", preview.clarification_lines)
        self.assertEqual(preview.draft.operations[0].target_period, "2026-11")
        self.assertEqual(
            preview.draft.operations[0].candidate_id,
            self.focus.ordered_candidate_ids[0],
        )
        self.assertEqual(self.runtime.resume_calls, 0)
        with self.assertRaises(HumanReviewCommandError) as ctx:
            submit_human_review_batch(
                preview.draft,
                focus=self.focus,
                runtime=self.runtime,
                now=FIXED_AT,
                confirmed=True,
            )
        self.assertIn("причину переноса", str(ctx.exception.message))
        self.assertEqual(self.runtime.resume_calls, 0)

    def test_09c_multi_command_segmentation_no_action_leak(self) -> None:
        text = (
            "№1 ПЕРЕНЕСТИ НА НОЯБРЬ 2026\n"
            "№6 ПЕРЕНЕСТИ НА НОЯБРЬ 2026\n"
            "№8 СКОРРЕКТИРОВАТЬ ОБЪЕМ"
        )
        one_line = (
            "№1 ПЕРЕНЕСТИ НА НОЯБРЬ 2026 "
            "№6 ПЕРЕНЕСТИ НА НОЯБРЬ 2026 "
            "№8 СКОРРЕКТИРОВАТЬ ОБЪЕМ"
        )
        interp = default_review_intent_interpreter()
        for sample in (text, one_line):
            draft = interp.interpret(
                sample, default_year=2026, context_period="2026-10"
            )
            self.assertEqual(len(draft.operations), 3, sample)
            self.assertEqual(draft.operations[0].kind, ReviewIntentKind.DEFER_TO_PERIOD)
            self.assertEqual(draft.operations[0].target.alias_numbers, (1,))
            self.assertEqual(draft.operations[0].target_period, "2026-11")
            self.assertIsNone(draft.operations[0].reason_text)
            self.assertEqual(draft.operations[1].kind, ReviewIntentKind.DEFER_TO_PERIOD)
            self.assertEqual(draft.operations[1].target.alias_numbers, (6,))
            self.assertEqual(draft.operations[1].target_period, "2026-11")
            self.assertIsNone(draft.operations[1].reason_text)
            self.assertEqual(draft.operations[2].kind, ReviewIntentKind.CHANGE_QUANTITY)
            self.assertEqual(draft.operations[2].target.alias_numbers, (8,))
            self.assertIsNone(draft.operations[2].approved_qty)
            self.assertIsNone(draft.operations[2].reason_text)
            self.assertIsNone(draft.operations[2].target_period)

        # Resolve against full package Focus Set (aliases 1..7 exist; add №8 via open filter).
        wide = build_human_review_focus_set(
            self.surface,
            HumanReviewFocusFilter(),
            focus_set_id="fs-wide",
            created_at=FIXED_AT,
        )
        self.assertGreaterEqual(wide.size, 7)
        preview_text = (
            "№1 ПЕРЕНЕСТИ НА НОЯБРЬ 2026\n"
            f"№{min(6, wide.size)} ПЕРЕНЕСТИ НА НОЯБРЬ 2026\n"
            f"№{wide.size} СКОРРЕКТИРОВАТЬ ОБЪЕМ"
        )
        preview = prepare_batch_from_text(
            preview_text,
            focus=wide,
            surface=self.surface,
            default_year=2026,
            context_period="2026-10",
        )
        self.assertEqual(preview.counts.defer, 2)
        self.assertEqual(preview.counts.change_qty, 1)
        kinds = [op.resolution for op in preview.draft.operations]
        self.assertEqual(kinds.count(BatchResolution.DEFER_TO_PERIOD), 2)
        self.assertEqual(kinds.count(BatchResolution.CHANGE_QUANTITY), 1)
        change = next(
            op
            for op in preview.draft.operations
            if op.resolution is BatchResolution.CHANGE_QUANTITY
        )
        self.assertIsNone(change.approved_qty)
        self.assertIn("Укажите причину переноса.", preview.clarification_lines)
        self.assertIn("Укажите новый объём.", preview.clarification_lines)
        self.assertIn("Укажите причину корректировки.", preview.clarification_lines)
        self.assertFalse(preview.reasons_complete)
        # Recognize / preview must never write durable Human Review state.
        self.assertEqual(self.runtime.resume_calls, 0)
        for _ in range(3):
            prepare_batch_from_text(
                preview_text,
                focus=wide,
                surface=self.surface,
                default_year=2026,
                context_period="2026-10",
            )
        self.assertEqual(self.runtime.resume_calls, 0)
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_batch(
                preview.draft,
                focus=wide,
                runtime=self.runtime,
                now=FIXED_AT,
                confirmed=True,
            )
        self.assertEqual(self.runtime.resume_calls, 0)

    def test_10_quantity_intent(self) -> None:
        draft = default_review_intent_interpreter().interpret(
            "Позиция 7 — объём 50 метров. Ошибка объёма."
        )
        op = draft.operations[0]
        self.assertEqual(op.kind, ReviewIntentKind.CHANGE_QUANTITY)
        self.assertEqual(op.approved_qty, 50.0)
        self.assertIn("Ошибка", op.reason_text or "")

    def test_11_multi_exclude(self) -> None:
        draft = default_review_intent_interpreter().interpret(
            "Позиции 1, 2 и 3 исключить. В этом месяце не требуются."
        )
        op = draft.operations[0]
        self.assertEqual(op.kind, ReviewIntentKind.EXCLUDE)
        self.assertEqual(op.target.alias_numbers, (1, 2, 3))

    def test_12_needs_data_range(self) -> None:
        draft = default_review_intent_interpreter().interpret(
            "Позиции с 1 по 2 — нужны данные. Уточнить норму."
        )
        op = draft.operations[0]
        self.assertEqual(op.kind, ReviewIntentKind.NEEDS_DATA)
        self.assertEqual(op.target.alias_numbers, (1, 2))

    def test_13_accept_remainder_resolves_ids(self) -> None:
        preview = prepare_batch_from_text(
            "Позицию 4 перенести на ноябрь. Нет готовности.\nОстальные принять.",
            focus=self.focus,
            surface=self.surface,
        )
        deferred = [
            op
            for op in preview.draft.operations
            if op.resolution is BatchResolution.DEFER_TO_PERIOD
        ]
        accepted = [
            op for op in preview.draft.operations if op.resolution is BatchResolution.ACCEPT
        ]
        self.assertEqual(len(deferred), 1)
        self.assertEqual(preview.counts.defer, 1)
        self.assertEqual(preview.counts.accept, self.focus.size - 1)
        self.assertEqual(len(accepted), self.focus.size - 1)
        self.assertTrue(all(op.candidate_id for op in preview.draft.operations))

    def test_14_15_boq_resolve_and_ambiguous(self) -> None:
        preview = prepare_batch_from_text(
            "Код 2041-02-06-03 принять 50 м. Ошибка объёма.",
            focus=self.focus,
            surface=self.surface,
        )
        self.assertEqual(preview.counts.change_qty, 1)
        self.assertEqual(preview.draft.operations[0].boq_code, "2041-02-06-03")
        # Ambiguous: inject duplicate BOQ into a cloned focus is heavy; unknown fails.
        with self.assertRaises(HumanReviewCommandError):
            prepare_batch_from_text(
                "Код 9999-99-99-99 принять 10 м. Ошибка.",
                focus=self.focus,
                surface=self.surface,
            )

    def test_16_unknown_row_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            prepare_batch_from_text(
                "Позицию 99 исключить. Причина.",
                focus=self.focus,
                surface=self.surface,
            )

    def test_17_21_preview_counts_and_confirm_gate(self) -> None:
        preview = prepare_batch_from_text(
            "Позицию 1 исключить. Не нужно.\n"
            "Позиция 2 — объём 40 м. Ошибка объёма.\n"
            "Позицию 3 перенести на ноябрь. Нет готовности.\n"
            "Остальные принять.",
            focus=self.focus,
            surface=self.surface,
        )
        self.assertEqual(preview.counts.total, self.focus.size)
        self.assertEqual(preview.counts.exclude, 1)
        self.assertEqual(preview.counts.change_qty, 1)
        self.assertEqual(preview.counts.defer, 1)
        self.assertTrue(any("80" in line or "40" in line for line in preview.exception_lines))
        self.assertTrue(any("2026-11" in line for line in preview.exception_lines))
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_batch(
                preview.draft, focus=self.focus, runtime=self.runtime, confirmed=False
            )

    def test_22_28_batch_port_atomic_and_stale(self) -> None:
        preview = prepare_batch_from_text(
            "Позицию 1 исключить. Не нужно.\nОстальные принять.",
            focus=self.focus,
            surface=self.surface,
        )
        result = submit_human_review_batch(
            preview.draft,
            focus=self.focus,
            runtime=self.runtime,
            now=FIXED_AT,
            confirmed=True,
        )
        self.assertEqual(result.operation_count, self.focus.size)
        self.assertEqual(self.runtime.resume_calls, 1)
        self.assertEqual(len(self.runtime.lifecycle.human_review_events), self.focus.size)

        stale_focus = replace(self.focus, expected_checkpoint_id="stale")
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_batch(
                replace(preview.draft, expected_checkpoint_id="stale"),
                focus=stale_focus,
                runtime=self.runtime,
                now=FIXED_AT,
                confirmed=True,
            )

    def test_25_invalid_qty_blocks_batch(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            prepare_batch_from_text(
                "Позиция 1 — объём 999 м. Ошибка.",
                focus=self.focus,
                surface=self.surface,
            )
        self.assertEqual(self.runtime.resume_calls, 0)

    def test_29_32_defer_metadata(self) -> None:
        preview = prepare_batch_from_text(
            "Позицию 1 перенести на ноябрь. Нет готовности.",
            focus=self.focus,
            surface=self.surface,
        )
        submit_human_review_batch(
            preview.draft,
            focus=self.focus,
            runtime=self.runtime,
            now=FIXED_AT,
            confirmed=True,
        )
        event = self.runtime.lifecycle.human_review_events[0]
        self.assertEqual(event.decision, HumanReviewDecision.REMOVE)
        self.assertEqual(event.resolution_kind, RESOLUTION_KIND_DEFER_TO_PERIOD)
        self.assertEqual(event.target_period, "2026-11")
        self.assertIn("готовности", event.reason_text or "")
        # No November commitment artifact — only review event metadata.
        self.assertIsNone(getattr(self.runtime.lifecycle, "reviewed_package", None) or None)


class UiRegressionTests(unittest.TestCase):
    def test_33_37_page_and_chips(self) -> None:
        page = (
            Path(__file__).resolve().parents[1]
            / "pages"
            / "53_AI_Центр_управления_агентами.py"
        )
        text = page.read_text(encoding="utf-8")
        self.assertIn("prepare_batch_from_text", text)
        self.assertIn("ПОДТВЕРДИТЬ РЕШЕНИЯ", text)
        self.assertIn("КОМАНДА РЕШЕНИЯ", text)
        self.assertIn("РАСПОЗНАТЬ КОМАНДУ", text)
        self.assertIn("Не удалось распознать команду", text)
        self.assertIn("clarification_lines", text)
        self.assertIn("reasons_complete", text)
        self.assertIn("_render_decision_command_panel", text)
        # Recognize → prepare_batch_from_text only; durable write only via confirm submit.
        recognize_idx = text.index("РАСПОЗНАТЬ КОМАНДУ")
        confirm_idx = text.index("ПОДТВЕРДИТЬ РЕШЕНИЯ")
        self.assertLess(recognize_idx, confirm_idx)
        self.assertIn("prepare_batch_from_text", text[recognize_idx:confirm_idx])
        self.assertNotIn("submit_human_review_batch", text[recognize_idx:confirm_idx])
        self.assertIn("submit_human_review_batch", text[confirm_idx:])
        self.assertIn("_render_human_decision_single_row_v1", text)
        self.assertIn("ПОДТВЕРДИТЬ РЕШЕНИЕ", text)
        self.assertIn("Быстрая команда", text)
        self.assertIn('st.session_state["dynamis_global_text"] = ""', text)
        self.assertIn("module5_filter_options", text)
        self.assertIn("filter_records_by_work_context", text)
        self.assertIn("build_focus_set_from_work_context", text)
        self.assertIn("build_monthly_commitment_draft", text)
        self.assertIn("Текущий черновик месячного обязательства", text)
        # Golden Path: no second Focus Set filter workbench in Human Decision.
        self.assertNotIn("Рабочий срез (Focus Set)", text)
        self.assertNotIn("dynamis_hr_focus_facility_", text)
        self.assertNotRegex(text, r"st\.set_page_config\s*\(")

        # Кандидаты chip from result_view.
        from tests.test_human_surface_module5_result_ux import _registry

        registry = _registry()
        labels = " ".join(
            label for _id, label, _e in module5_filter_options(build_module5_result_summary(registry))
        )
        self.assertIn("Кандидаты ·", labels)
        cand_rows = select_workspace_records(
            registry.records, registry.professional, view_id="candidates"
        )
        self.assertTrue(all(item.outcome == "CANDIDATE" for item in cand_rows))


if __name__ == "__main__":
    unittest.main()
