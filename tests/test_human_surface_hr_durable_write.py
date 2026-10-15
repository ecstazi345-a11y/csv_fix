"""Human Review durable write / read-after-write incident guards."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from agents.human_surface.human_review_batch import (
    prepare_batch_from_text,
    submit_human_review_batch,
)
from agents.human_surface.human_review_command import (
    HumanReviewCommandError,
    prepare_human_review_surface,
)
from agents.human_surface.human_review_focus import (
    HumanReviewFocusFilter,
    build_human_review_focus_set,
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

FIXED_AT = datetime(2026, 10, 14, 18, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run-hr-durable-001"
MISSION_ID = "mission-hr-durable-001"
PROJECT = "PRJ_001_БХК"
MONTH = "октябрь-2026"
PAGE = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "53_AI_Центр_управления_агентами.py"
)


def _mission():
    return build_constructor_mission_scope(project_code=PROJECT, month_key=MONTH)


def _cand(cid: str, *, facility: str, discipline: str, qty: float = 80.0) -> dict[str, object]:
    return {
        "candidate_id": cid,
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": facility,
        "discipline": discipline,
        "system": "SYS-1",
        "iwp": "IWP-1",
        "queue": "",
        "boq_code": f"2041-01-{cid[-2:]}-01",
        "boq_name": f"Work {cid}",
        "unit": "м",
        "remaining_qty": 100.0,
        "already_planned_qty": 0.0,
        "available_to_add_qty": qty,
        "availability_status": "AVAILABLE",
        "labor_norm_status": LABOR_VALIDATED,
    }


def _lifecycle() -> ConstructorLifecycleState:
    items = [
        _cand("c01", facility="16160-13", discipline="Автоматизация", qty=80),
        _cand("c02", facility="16160-13", discipline="Автоматизация", qty=70),
        _cand("c03", facility="16160-13", discipline="Автоматизация", qty=60),
    ]
    package = build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items),
        run_id=RUN_ID,
        snapshot_id="snap-durable",
        created_at=FIXED_AT.isoformat(),
        exception_summary=PackageExceptionSummary(
            blocking_count=0, non_blocking_count=0, warning_count=0
        ),
    )
    base = create_lifecycle_state(
        mission_id=MISSION_ID,
        run_id=RUN_ID,
        authorization_id="auth-durable",
        created_at=FIXED_AT,
    )
    return replace(
        base,
        status=STATUS_WAITING_FOR_HUMAN_REVIEW,
        scope=package.scope,
        package=package,
        exceptions=ConstructorExceptionSet(
            schema_version=EXC_SCHEMA,
            exceptions=(),
            summary=package.exception_summary,
            package_id=package.package_id,
        ),
        human_review_events=(),
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


class _PersistingRuntime:
    def __init__(self, lifecycle: ConstructorLifecycleState) -> None:
        self.lifecycle = lifecycle
        self.checkpoint_id = "ckpt-durable-1"
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
        self.checkpoint_id = f"ckpt-durable-{self.resume_calls + 1}"
        return self.lifecycle


class _NonPersistingRuntime(_PersistingRuntime):
    """Resume returns success-shaped state but does not persist events."""

    def resume_professional_review(
        self,
        *,
        run_id: str,
        resume_command: ProfessionalHumanReviewResumeCommand,
    ) -> ConstructorLifecycleState:
        self.resume_calls += 1
        # Swallow events — simulates write port no-op / wrong store.
        return self.lifecycle


class DurableWritePortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = _PersistingRuntime(_lifecycle())
        self.surface = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        self.focus = build_human_review_focus_set(
            self.surface,
            HumanReviewFocusFilter(facility="16160-13", discipline="Автоматизация"),
            created_at=FIXED_AT,
        )

    def test_confirm_calls_write_port_once_and_persists(self) -> None:
        preview = prepare_batch_from_text(
            "Позицию 1 перенести на ноябрь. Нет готовности.\n"
            "Позицию 2 перенести на ноябрь. Нет готовности.\n"
            "Остальные принять.",
            focus=self.focus,
            surface=self.surface,
            default_year=2026,
            context_period="2026-10",
        )
        self.assertEqual(self.runtime.resume_calls, 0)
        result = submit_human_review_batch(
            preview.draft,
            focus=self.focus,
            runtime=self.runtime,
            now=FIXED_AT,
            confirmed=True,
        )
        self.assertEqual(self.runtime.resume_calls, 1)
        self.assertEqual(result.operation_count, 3)
        self.assertEqual(len(result.event_ids), 3)
        self.assertEqual(len(self.runtime.lifecycle.human_review_events), 3)

    def test_reload_surface_shows_same_durable_decisions(self) -> None:
        preview = prepare_batch_from_text(
            "Позицию 1 перенести на ноябрь. Нет готовности.\nОстальные принять.",
            focus=self.focus,
            surface=self.surface,
            default_year=2026,
            context_period="2026-10",
        )
        submit_human_review_batch(
            preview.draft,
            focus=self.focus,
            runtime=self.runtime,
            now=FIXED_AT,
            confirmed=True,
        )
        again = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        self.assertEqual(again.reviewed_count, 3)
        self.assertEqual(again.accepted_count, 2)
        self.assertEqual(again.deferred_count, 1)
        self.assertEqual(again.not_reviewed_count, 0)
        labels = {c.candidate_id: c.current_decision_label for c in again.candidates}
        self.assertEqual(labels["c01"], "ПЕРЕНЕСЕНО")
        self.assertEqual(labels["c02"], "ПРИНЯТО")
        self.assertEqual(labels["c03"], "ПРИНЯТО")

    def test_write_failure_does_not_report_success(self) -> None:
        runtime = _NonPersistingRuntime(_lifecycle())
        surface = prepare_human_review_surface(RUN_ID, runtime=runtime)
        focus = build_human_review_focus_set(
            surface,
            HumanReviewFocusFilter(facility="16160-13", discipline="Автоматизация"),
            created_at=FIXED_AT,
        )
        preview = prepare_batch_from_text(
            "Остальные принять.",
            focus=focus,
            surface=surface,
            default_year=2026,
        )
        with self.assertRaises(HumanReviewCommandError) as ctx:
            submit_human_review_batch(
                preview.draft,
                focus=focus,
                runtime=runtime,
                now=FIXED_AT,
                confirmed=True,
            )
        self.assertIn("missing committed events", ctx.exception.message)
        self.assertEqual(runtime.resume_calls, 1)
        self.assertEqual(len(runtime.lifecycle.human_review_events), 0)
        surface_after = prepare_human_review_surface(RUN_ID, runtime=runtime)
        self.assertEqual(surface_after.reviewed_count, 0)
        self.assertEqual(surface_after.not_reviewed_count, 3)

    def test_preview_recognize_writes_zero(self) -> None:
        for _ in range(2):
            prepare_batch_from_text(
                "Позицию 1 перенести на ноябрь. Нет готовности.\nОстальные принять.",
                focus=self.focus,
                surface=self.surface,
                default_year=2026,
                context_period="2026-10",
            )
        self.assertEqual(self.runtime.resume_calls, 0)
        self.assertEqual(len(self.runtime.lifecycle.human_review_events), 0)


class PageReadAfterWriteGuards(unittest.TestCase):
    def test_confirm_requires_durable_readback_before_success(self) -> None:
        text = PAGE.read_text(encoding="utf-8")
        confirm_idx = text.index("ПОДТВЕРДИТЬ РЕШЕНИЯ")
        chunk = text[confirm_idx : confirm_idx + 2200]
        self.assertIn("submit_human_review_batch", chunk)
        self.assertIn("prepare_human_review_surface", chunk)
        self.assertIn("readback", chunk.lower() + chunk)
        # Success only after durable verification; failure keeps error path.
        success_idx = chunk.index("Пакет решений записан в durable Human Review.")
        readback_idx = chunk.index("prepare_human_review_surface")
        self.assertLess(readback_idx, success_idx)
        self.assertIn("НЕ РАССМОТРЕНО", chunk)
        self.assertIn("Preview is not committed truth", chunk)
        # Preview recognize must not write.
        recognize_idx = text.index("РАСПОЗНАТЬ КОМАНДУ")
        between = text[recognize_idx:confirm_idx]
        self.assertIn("prepare_batch_from_text", between)
        self.assertNotIn("submit_human_review_batch", between)
        # No session_state authoritative committed counters.
        self.assertNotIn("dynamis_hr_committed_counts", text)
        self.assertNotIn('session_state["reviewed_count"]', text)


if __name__ == "__main__":
    unittest.main()
