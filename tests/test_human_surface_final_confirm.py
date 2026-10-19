"""Package-wide Final Human Confirm and immutable Approved Monthly Package."""

from __future__ import annotations

import inspect
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from agents.human_surface.final_confirm_command import (
    CODE_NOT_READY,
    CODE_READBACK_MISMATCH,
    CODE_STALE_APPROVAL_PREVIEW,
    STATUS_CONFIRM_ALREADY,
    STATUS_CONFIRM_APPROVED,
    FinalConfirmError,
    find_current_approved_package,
    prepare_final_monthly_approval_preview,
    review_content_hash,
    submit_final_monthly_confirm,
)
from agents.human_surface.human_review_command import HumanReviewCommandError
from agents.human_surface.monthly_commitment_draft import (
    STATUS_ACCEPTED,
    STATUS_CHANGED,
)
from agents.monthly_plan_constructor.approved_monthly_package import (
    ApprovedMonthlyLine,
    ApprovedMonthlyPackage,
    ApprovedMonthlySummary,
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
    build_human_review_event,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_WAITING_FOR_HUMAN_REVIEW,
    ConstructorLifecycleState,
    LifecycleTransition,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import build_constructor_mission_scope
from agents.monthly_plan_constructor.row_decision import ConstructorRowDecisionRecord
from agents.monthly_plan_constructor.shadow_approved_monthly_package_store import (
    CODE_APPROVED_STORE_CONFLICT,
    ApprovedMonthlyPackageStore,
    ApprovedMonthlyPackageStoreError,
    open_approved_monthly_package_store,
)

FIXED_AT = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 14, 13, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run-final-confirm-001"
MISSION_ID = "mission-final-confirm-001"
PROJECT = "PRJ_001_БХК"
MONTH = "октябрь-2026"
FACILITY = "16160-13"
DISCIPLINE = "Вентиляция"


def _candidate(
    candidate_id: str,
    *,
    available: float = 80.0,
    planned: float = 20.0,
    facility: str = FACILITY,
    discipline: str = DISCIPLINE,
    system: str = "SYS-1",
    iwp: str = "IWP-1",
    boq_code: str | None = None,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": facility,
        "discipline": discipline,
        "system": system,
        "iwp": iwp,
        "queue": "",
        "boq_code": boq_code or f"BOQ-{candidate_id}",
        "boq_name": f"Work {candidate_id}",
        "unit": "м",
        "remaining_qty": 100.0,
        "already_planned_qty": planned,
        "available_to_add_qty": available,
        "availability_status": "AVAILABLE",
        "labor_norm_status": LABOR_VALIDATED,
    }


def _lifecycle(
    rows: list[dict[str, object]],
    *,
    run_id: str = RUN_ID,
    queue_scope: str | None = None,
) -> ConstructorLifecycleState:
    scope = build_constructor_mission_scope(
        project_code=PROJECT,
        month_key=MONTH,
        queue_scope=queue_scope,
    )
    package = build_candidate_package(
        scope,
        rows,
        mission_id=MISSION_ID,
        scanned_count=max(len(rows), 1),
        excluded_completed_count=1,
        run_id=run_id,
        snapshot_id="snap-final-1",
        created_at=FIXED_AT.isoformat(),
        exception_summary=PackageExceptionSummary(
            blocking_count=0,
            non_blocking_count=0,
            warning_count=0,
        ),
    )
    state = create_lifecycle_state(
        mission_id=MISSION_ID,
        run_id=run_id,
        authorization_id="auth-final-1",
        created_at=FIXED_AT,
    )
    exc_set = ConstructorExceptionSet(
        schema_version=EXC_SCHEMA,
        exceptions=(),
        summary=package.exception_summary,
        package_id=package.package_id,
    )
    excluded = ConstructorRowDecisionRecord(
        source_order=0,
        source_identity="row-excluded",
        boq_code="BOQ-EXCLUDED",
        boq_name="Already done",
        unit="м",
        system="SYS-X",
        project_code=PROJECT,
        facility=FACILITY,
        discipline=DISCIPLINE,
        month_key=MONTH,
        iwp="IWP-X",
        remaining_qty=0.0,
        already_planned_qty=0.0,
        available_qty=0.0,
        outcome="EXCLUDED_COMPLETED",
        reason_code="COMPLETED",
        reason_text="deterministic exclusion",
        requires_human=False,
        candidate_created=False,
        candidate_id=None,
    )
    return replace(
        state,
        status=STATUS_WAITING_FOR_HUMAN_REVIEW,
        scope=package.scope,
        package=package,
        exceptions=exc_set,
        row_decisions=(excluded,),
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
        terminal_reason="awaiting professional Human Review",
    )


def _event(state: ConstructorLifecycleState, candidate_id: str, **overrides: object):
    package = state.package
    assert package is not None
    payload = {
        "review_event_id": f"evt-{candidate_id}",
        "run_id": state.run_id,
        "mission_id": state.mission_id,
        "package_id": package.package_id,
        "candidate_id": candidate_id,
        "decision": HumanReviewDecision.ADD,
        "actor_id": "human-surface-operator",
        "reviewed_at": FIXED_AT,
        "constructor_proposed_qty": 80.0,
        "human_approved_qty": 80.0,
        "reason_text": None,
        "resolution_kind": None,
        "target_period": None,
    }
    payload.update(overrides)
    return build_human_review_event(**payload)


class _FakeRuntime:
    def __init__(self, lifecycle: ConstructorLifecycleState) -> None:
        self.lifecycle = lifecycle
        self.checkpoint_id = "ckpt-1"

    def load_lifecycle(self, run_id: str) -> ConstructorLifecycleState:
        if run_id != self.lifecycle.run_id:
            raise HumanReviewCommandError("run not found")
        return self.lifecycle

    def current_checkpoint_id(self, run_id: str) -> str:
        return self.checkpoint_id


class _MismatchStore(ApprovedMonthlyPackageStore):
    def get_by_id(self, approved_package_id: str):
        package = super().get_by_id(approved_package_id)
        if package is None:
            return None
        return replace(package, content_hash="mismatch")


class FinalConfirmTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.store_path = Path(self._tmp.name) / "approved_monthly_packages.sqlite"
        self.store = open_approved_monthly_package_store(self.store_path)

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def _runtime(self, state: ConstructorLifecycleState) -> _FakeRuntime:
        return _FakeRuntime(state)

    def _bind(self, state: ConstructorLifecycleState, *events: object) -> _FakeRuntime:
        bound = replace(state, human_review_events=tuple(events))
        return self._runtime(bound)

    def _preview(self, runtime: _FakeRuntime):
        return prepare_final_monthly_approval_preview(runtime.lifecycle.run_id, runtime=runtime)

    def _confirm(self, runtime: _FakeRuntime, preview=None, store=None):
        current = preview or self._preview(runtime)
        return submit_final_monthly_confirm(
            current,
            runtime=runtime,
            store=store or self.store,
            now=LATER,
        )

    def _row_count(self) -> int:
        connection = sqlite3.connect(self.store_path)
        try:
            return int(
                connection.execute("SELECT COUNT(*) FROM approved_monthly_packages").fetchone()[0]
            )
        finally:
            connection.close()

    def test_readiness_blocks_not_reviewed_and_needs_data(self) -> None:
        rows = [_candidate("a"), _candidate("b")]
        state = _lifecycle(rows)
        runtime = self._bind(state, _event(state, "a"))
        blocked = self._preview(runtime)
        self.assertFalse(blocked.readiness.ready)
        self.assertEqual(blocked.readiness.not_reviewed_count, 1)
        with self.assertRaises(FinalConfirmError) as pending:
            self._confirm(runtime, blocked)
        self.assertEqual(pending.exception.code, CODE_NOT_READY)
        self.assertIn("1", pending.exception.message)
        self.assertEqual(self._row_count(), 0)

        needs = self._bind(
            state,
            _event(state, "a"),
            _event(
                state,
                "b",
                decision=HumanReviewDecision.REQUIRES_CLARIFICATION,
                human_approved_qty=None,
                constructor_proposed_qty=80.0,
                reason_text="нет остатка",
            ),
        )
        needs_preview = self._preview(needs)
        self.assertEqual(needs_preview.readiness.needs_data_count, 1)
        self.assertFalse(needs_preview.readiness.ready)
        with self.assertRaises(FinalConfirmError) as data_error:
            self._confirm(needs, needs_preview)
        self.assertIn("1", data_error.exception.message)

    def test_readiness_accepts_resolved_mix_and_ignores_excluded_rows(self) -> None:
        rows = [
            _candidate("accept"),
            _candidate("change", available=80.0),
            _candidate("exclude"),
            _candidate("defer"),
        ]
        state = _lifecycle(rows)
        runtime = self._bind(
            state,
            _event(state, "accept"),
            _event(
                state,
                "change",
                human_approved_qty=50.0,
                reason_text="только 50",
            ),
            _event(
                state,
                "exclude",
                decision=HumanReviewDecision.REMOVE,
                human_approved_qty=0.0,
                reason_text="не в этом месяце",
            ),
            _event(
                state,
                "defer",
                decision=HumanReviewDecision.REMOVE,
                human_approved_qty=0.0,
                reason_text="перенос",
                resolution_kind=RESOLUTION_KIND_DEFER_TO_PERIOD,
                target_period="2026-11",
            ),
        )
        preview = self._preview(runtime)
        self.assertTrue(preview.readiness.ready)
        self.assertEqual(preview.readiness.not_reviewed_count, 0)
        self.assertEqual(preview.readiness.needs_data_count, 0)
        self.assertEqual(preview.readiness.accepted_count, 1)
        self.assertEqual(preview.readiness.changed_qty_count, 1)
        self.assertEqual(preview.readiness.excluded_count, 1)
        self.assertEqual(preview.readiness.deferred_count, 1)
        self.assertEqual(len(runtime.lifecycle.row_decisions), 1)
        self.assertEqual(runtime.lifecycle.row_decisions[0].outcome, "EXCLUDED_COMPLETED")
        self.assertEqual(preview.readiness.candidate_count, 4)

        only = _lifecycle([_candidate("solo")])
        accepted = self._bind(only, _event(only, "solo"))
        ready = self._preview(accepted)
        self.assertTrue(ready.readiness.ready)

    def test_preview_is_package_wide_and_ignores_ui_slice(self) -> None:
        signature = inspect.signature(prepare_final_monthly_approval_preview)
        self.assertEqual(list(signature.parameters), ["run_id", "runtime"])
        rows = [
            _candidate("left", facility="16160-13", system="SYS-A", iwp="IWP-A"),
            _candidate("right", facility="26160-13", discipline="Автоматизация", system="SYS-B", iwp="IWP-B"),
        ]
        state = _lifecycle(rows)
        runtime = self._bind(state, _event(state, "left"), _event(state, "right"))
        first = self._preview(runtime)
        second = self._preview(runtime)
        self.assertEqual(first.preview_content_hash, second.preview_content_hash)
        self.assertEqual(first.review_content_hash, second.review_content_hash)
        self.assertEqual(
            tuple(item.candidate_id for item in first.professional_lines),
            ("left", "right"),
        )
        self.assertIsNone(first.queue)
        self.assertIn("16160-13", {item.facility for item in first.professional_lines})
        self.assertIn("26160-13", {item.facility for item in first.professional_lines})

    def test_professional_lines_keep_identity_and_do_not_mutate_source(self) -> None:
        source_rows = [
            _candidate("base", available=80.0, planned=20.0, boq_code="BOQ-SAME", system="SYS-A", iwp="IWP-A"),
            _candidate(
                "other",
                available=10.0,
                planned=1.0,
                boq_code="BOQ-SAME",
                facility="16160-17",
                system="SYS-B",
                iwp="IWP-B",
            ),
            _candidate("changed", available=80.0, planned=20.0),
            _candidate("drop-ex"),
            _candidate("drop-def"),
            _candidate("dust", available=1e-13, planned=20.0),
        ]
        snapshot = [dict(item) for item in source_rows]
        state = _lifecycle(source_rows)
        runtime = self._bind(
            state,
            _event(state, "base", constructor_proposed_qty=80.0, human_approved_qty=80.0),
            _event(state, "other", constructor_proposed_qty=10.0, human_approved_qty=10.0),
            _event(
                state,
                "changed",
                constructor_proposed_qty=80.0,
                human_approved_qty=50.0,
                reason_text="снижение",
            ),
            _event(
                state,
                "drop-ex",
                decision=HumanReviewDecision.REMOVE,
                human_approved_qty=0.0,
                reason_text="исключить",
            ),
            _event(
                state,
                "drop-def",
                decision=HumanReviewDecision.REMOVE,
                human_approved_qty=0.0,
                reason_text="позже",
                resolution_kind=RESOLUTION_KIND_DEFER_TO_PERIOD,
                target_period="2026-11",
            ),
            _event(state, "dust", constructor_proposed_qty=1e-13, human_approved_qty=1e-13),
        )
        before_qty = {
            item.candidate_id: item.available_to_add_qty
            for item in runtime.lifecycle.package.candidates
        }
        preview = self._preview(runtime)
        after_qty = {
            item.candidate_id: item.available_to_add_qty
            for item in runtime.lifecycle.package.candidates
        }
        self.assertEqual(before_qty, after_qty)
        self.assertEqual(source_rows, snapshot)
        by_id = {item.candidate_id: item for item in preview.professional_lines}
        self.assertEqual(set(by_id), {"base", "other", "changed", "dust"})
        self.assertEqual(by_id["base"].baseline_qty, "20")
        self.assertEqual(by_id["base"].constructor_delta_qty, "80")
        self.assertEqual(by_id["base"].final_qty, "100")
        self.assertEqual(by_id["base"].source_status, STATUS_ACCEPTED)
        self.assertEqual(by_id["changed"].constructor_delta_qty, "50")
        self.assertEqual(by_id["changed"].final_qty, "70")
        self.assertEqual(by_id["changed"].source_status, STATUS_CHANGED)
        self.assertEqual(by_id["base"].boq_code, by_id["other"].boq_code)
        self.assertNotEqual(by_id["base"].system, by_id["other"].system)
        self.assertNotEqual(by_id["base"].iwp, by_id["other"].iwp)
        self.assertEqual(by_id["dust"].constructor_delta_qty, "0")
        self.assertEqual(by_id["dust"].final_qty, "20")

    def test_review_hash_ignores_event_identity(self) -> None:
        rows = [_candidate("a"), _candidate("b")]
        state = _lifecycle(rows)
        first = self._bind(
            state,
            _event(state, "a", review_event_id="evt-1", reviewed_at=FIXED_AT),
            _event(state, "b", review_event_id="evt-2", reviewed_at=FIXED_AT),
        )
        second = self._bind(
            state,
            _event(state, "b", review_event_id="evt-9", reviewed_at=LATER),
            _event(state, "a", review_event_id="evt-8", reviewed_at=LATER),
        )
        self.assertEqual(review_content_hash(first.lifecycle), review_content_hash(second.lifecycle))
        self.assertEqual(self._preview(first).preview_content_hash, self._preview(second).preview_content_hash)

    def _expect_stale(self, runtime: _FakeRuntime, preview, label: str) -> None:
        with self.assertRaises(FinalConfirmError) as caught:
            self._confirm(runtime, preview)
        self.assertEqual(caught.exception.code, CODE_STALE_APPROVAL_PREVIEW, label)
        self.assertIn("предварительного просмотра", caught.exception.message)

    def test_stale_preview_writes_nothing(self) -> None:
        rows = [_candidate("a")]
        state = _lifecycle(rows)
        accepted = _event(state, "a", reason_text="держать")
        runtime = self._bind(state, accepted)
        preview = self._preview(runtime)
        runtime.lifecycle = replace(
            runtime.lifecycle,
            human_review_events=(
                accepted,
                _event(
                    state,
                    "a",
                    review_event_id="evt-review",
                    decision=HumanReviewDecision.REMOVE,
                    human_approved_qty=0.0,
                    reason_text="убрать",
                    reviewed_at=LATER,
                ),
            ),
        )
        self._expect_stale(runtime, preview, "review")

        runtime.lifecycle = replace(
            runtime.lifecycle,
            human_review_events=(
                accepted,
                _event(
                    state,
                    "a",
                    review_event_id="evt-qty",
                    human_approved_qty=40.0,
                    reason_text="держать",
                    reviewed_at=LATER,
                ),
            ),
        )
        self._expect_stale(runtime, preview, "qty")

        runtime.lifecycle = replace(
            runtime.lifecycle,
            human_review_events=(
                accepted,
                _event(
                    state,
                    "a",
                    review_event_id="evt-reason",
                    reason_text="другая причина",
                    reviewed_at=LATER,
                ),
            ),
        )
        self._expect_stale(runtime, preview, "reason")

        excluded = _event(
            state,
            "a",
            decision=HumanReviewDecision.REMOVE,
            human_approved_qty=0.0,
            reason_text="вне месяца",
        )
        runtime.lifecycle = replace(runtime.lifecycle, human_review_events=(excluded,))
        excluded_preview = self._preview(runtime)
        runtime.lifecycle = replace(
            runtime.lifecycle,
            human_review_events=(
                excluded,
                _event(
                    state,
                    "a",
                    review_event_id="evt-kind",
                    decision=HumanReviewDecision.REMOVE,
                    human_approved_qty=0.0,
                    reason_text="вне месяца",
                    resolution_kind=RESOLUTION_KIND_DEFER_TO_PERIOD,
                    target_period="2026-11",
                    reviewed_at=LATER,
                ),
            ),
        )
        self._expect_stale(runtime, excluded_preview, "kind")

        deferred = _event(
            state,
            "a",
            review_event_id="evt-defer",
            decision=HumanReviewDecision.REMOVE,
            human_approved_qty=0.0,
            reason_text="перенос",
            resolution_kind=RESOLUTION_KIND_DEFER_TO_PERIOD,
            target_period="2026-11",
        )
        runtime.lifecycle = replace(runtime.lifecycle, human_review_events=(deferred,))
        deferred_preview = self._preview(runtime)
        runtime.lifecycle = replace(
            runtime.lifecycle,
            human_review_events=(
                deferred,
                _event(
                    state,
                    "a",
                    review_event_id="evt-period",
                    decision=HumanReviewDecision.REMOVE,
                    human_approved_qty=0.0,
                    reason_text="перенос",
                    resolution_kind=RESOLUTION_KIND_DEFER_TO_PERIOD,
                    target_period="2026-12",
                    reviewed_at=LATER,
                ),
            ),
        )
        self._expect_stale(runtime, deferred_preview, "period")

        runtime.lifecycle = replace(runtime.lifecycle, human_review_events=(accepted,))
        runtime.checkpoint_id = "ckpt-moved"
        self._expect_stale(runtime, preview, "checkpoint")
        self.assertEqual(self._row_count(), 0)

    def test_idempotent_confirm_and_immutable_history(self) -> None:
        rows = [_candidate("a")]
        state = _lifecycle(rows)
        runtime = self._bind(state, _event(state, "a", reason_text="ок"))
        preview = self._preview(runtime)
        first = self._confirm(runtime, preview)
        second = self._confirm(runtime, preview)
        self.assertEqual(first.status, STATUS_CONFIRM_APPROVED)
        self.assertEqual(second.status, STATUS_CONFIRM_ALREADY)
        self.assertEqual(first.package.approved_package_id, second.package.approved_package_id)
        self.assertEqual(first.package.content_hash, second.package.content_hash)
        self.assertEqual(self._row_count(), 1)
        historical = self.store.get_by_id(first.package.approved_package_id)
        assert historical is not None
        historical_lines = historical.professional_lines
        revised = replace(
            runtime.lifecycle,
            human_review_events=runtime.lifecycle.human_review_events
            + (
                _event(
                    state,
                    "a",
                    review_event_id="evt-later",
                    human_approved_qty=30.0,
                    reason_text="позже меньше",
                    reviewed_at=LATER,
                ),
            ),
        )
        runtime.lifecycle = revised
        runtime.checkpoint_id = "ckpt-2"
        again = self._confirm(runtime)
        self.assertEqual(again.status, STATUS_CONFIRM_APPROVED)
        self.assertNotEqual(again.package.approved_package_id, historical.approved_package_id)
        kept = self.store.get_by_id(historical.approved_package_id)
        assert kept is not None
        self.assertEqual(kept.professional_lines, historical_lines)
        self.assertEqual(kept.content_hash, historical.content_hash)
        self.assertEqual(self._row_count(), 2)
        self.assertEqual(again.package.professional_lines[0].final_qty, "50")

    def test_readback_mismatch_and_conflict_fail_closed(self) -> None:
        rows = [_candidate("a")]
        state = _lifecycle(rows)
        runtime = self._bind(state, _event(state, "a"))
        preview = self._preview(runtime)
        mismatch = _MismatchStore(db_path=self.store.db_path, connection=self.store._connection)
        with self.assertRaises(FinalConfirmError) as readback:
            self._confirm(runtime, preview, store=mismatch)
        self.assertEqual(readback.exception.code, CODE_READBACK_MISMATCH)

        class _Conflict:
            def put_if_absent(self, package: ApprovedMonthlyPackage):
                raise ApprovedMonthlyPackageStoreError(CODE_APPROVED_STORE_CONFLICT, "conflict")

            def get_by_id(self, approved_package_id: str):
                raise AssertionError("readback must not run after conflict")

            def close(self) -> None:
                return None

        with self.assertRaises(FinalConfirmError) as conflict:
            submit_final_monthly_confirm(
                preview,
                runtime=runtime,
                store=_Conflict(),
                now=LATER,
            )
        self.assertEqual(conflict.exception.code, CODE_APPROVED_STORE_CONFLICT)

    def test_same_id_different_payload_conflicts_in_store(self) -> None:
        line = ApprovedMonthlyLine(
            project_code=PROJECT,
            month_key=MONTH,
            facility=FACILITY,
            discipline=DISCIPLINE,
            system="SYS-1",
            iwp="IWP-1",
            boq_code="BOQ",
            name="Work",
            unit="м",
            baseline_qty="0",
            constructor_delta_qty="1",
            final_qty="1",
            source_status=STATUS_ACCEPTED,
            candidate_id="a",
        )
        summary = ApprovedMonthlySummary(1, 0, 1, 0, 1, 0, 0, 0, 0)
        first = ApprovedMonthlyPackage(
            schema_version="1.0",
            approved_package_id="amp-same",
            project_code=PROJECT,
            month_key=MONTH,
            queue=None,
            source_run_id=RUN_ID,
            source_candidate_package_id="pkg",
            source_review_content_hash="h1",
            source_preview_content_hash="p1",
            source_checkpoint_id="c1",
            approved_at=FIXED_AT,
            approved_by="human-surface-operator",
            status="APPROVED",
            professional_lines=(line,),
            summary_counts=summary,
            content_hash="hash-1",
            provenance="HUMAN_SURFACE_FINAL_CONFIRM",
        )
        self.store.put_if_absent(first)
        other = replace(
            first,
            source_review_content_hash="h2",
            content_hash="hash-2",
            professional_lines=(replace(line, final_qty="9"),),
        )
        with self.assertRaises(ApprovedMonthlyPackageStoreError) as conflict:
            self.store.put_if_absent(other)
        self.assertEqual(conflict.exception.code, CODE_APPROVED_STORE_CONFLICT)
        stored = self.store.get_by_id("amp-same")
        assert stored is not None
        self.assertEqual(stored.content_hash, "hash-1")
        self.assertEqual(stored.professional_lines[0].final_qty, "1")

    def test_lookup_does_not_create_a_missing_store(self) -> None:
        rows = [_candidate("a")]
        state = _lifecycle(rows)
        runtime = self._bind(state, _event(state, "a"))
        missing = Path(self._tmp.name) / "missing" / "approved_monthly_packages.sqlite"

        def _path():
            return missing

        from agents.human_surface import final_confirm_command as module

        original = module._production_store_path
        module._production_store_path = _path
        try:
            found = find_current_approved_package(runtime.lifecycle.run_id, runtime=runtime)
        finally:
            module._production_store_path = original
        self.assertIsNone(found)
        self.assertFalse(missing.exists())


class FinalConfirmPageTests(unittest.TestCase):
    def _preview(self, *, ready: bool, pending: int = 0, needs: int = 0):
        from agents.human_surface.final_confirm_command import (
            FinalApprovalReadiness,
            FinalMonthlyApprovalPreview,
        )

        return FinalMonthlyApprovalPreview(
            project_code=PROJECT,
            month_key=MONTH,
            queue="1",
            source_run_id="run-page",
            source_mission_id=MISSION_ID,
            source_candidate_package_id="pkg-page",
            expected_checkpoint_id="ckpt",
            review_content_hash="review",
            readiness=FinalApprovalReadiness(
                candidate_count=4,
                accepted_count=1,
                changed_qty_count=1,
                excluded_count=1,
                deferred_count=1,
                needs_data_count=needs,
                not_reviewed_count=pending,
                ready=ready,
            ),
            professional_lines=(),
            summary=ApprovedMonthlySummary(0, 0, 0, 1, 1, 1, 1, pending, needs),
            preview_content_hash="preview",
        )

    def test_page_button_follows_readiness_and_keeps_handoff_disabled(self) -> None:
        from tests.test_control_room_page_guards import PAGE_PATH, _load_page_module

        page, st = _load_page_module()
        result = SimpleNamespace(run_id="run-page")
        registry = SimpleNamespace()
        page.prepare_final_monthly_approval_preview = lambda run_id: self._preview(
            ready=False,
            pending=2,
            needs=1,
        )
        page._render_human_outcome(result, registry)
        text = " ".join(str(item) for args in st.write_calls for item in args)
        self.assertIn("остались позиции, требующие решения человека: 3", text)
        self.assertIn("Рассмотрено: 5", text)
        self.assertIn("Осталось решить: 2", text)
        self.assertIn("Требуют данных: 1", text)
        self.assertIn("Перенесено: 1", text)
        self.assertIn("Исключено: 1", text)
        confirm = [item for item in st.button_calls if "ПОДТВЕРДИТЬ" in item["label"]]
        self.assertEqual(confirm[-1]["label"], "ПОДТВЕРДИТЬ МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО")
        self.assertTrue(confirm[-1]["disabled"])

        page, st = _load_page_module()
        submitted = {"called": False}

        def _submit(preview, **kwargs):
            submitted["called"] = True
            raise FinalConfirmError(CODE_STALE_APPROVAL_PREVIEW, "stale")

        page.prepare_final_monthly_approval_preview = lambda run_id: self._preview(ready=True)
        page.find_current_approved_package = lambda run_id: None
        page.submit_final_monthly_confirm = _submit
        page._render_human_outcome(result, registry)
        enabled = [item for item in st.button_calls if item["label"] == "ПОДТВЕРДИТЬ МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО"]
        self.assertTrue(enabled)
        self.assertFalse(enabled[-1]["disabled"])
        self.assertFalse(submitted["called"])
        self.assertNotIn(
            "МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО УТВЕРЖДЕНО",
            " ".join(str(item) for args in st.write_calls for item in args),
        )

        page, st = _load_page_module()
        package = SimpleNamespace(
            approved_package_id="amp-page",
            approved_at=FIXED_AT,
            approved_by="human-surface-operator",
            source_candidate_package_id="pkg-page",
            source_run_id="run-page",
        )
        shown = self._preview(ready=True)
        submitted = {}

        def _ok(preview, **kwargs):
            submitted["preview"] = preview
            return SimpleNamespace(status=STATUS_CONFIRM_APPROVED, package=package)

        def _button(label: str, *args, **kwargs):
            st.button_calls.append(
                {"label": str(label), "disabled": bool(kwargs.get("disabled", False))}
            )
            return str(label) == "ПОДТВЕРДИТЬ МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО"

        st.button = _button
        page.prepare_final_monthly_approval_preview = lambda run_id: self._preview(ready=True)
        page.find_current_approved_package = lambda run_id: None
        page.submit_final_monthly_confirm = _ok
        page._render_human_outcome(result, registry)
        self.assertNotIn(
            "МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО УТВЕРЖДЕНО",
            " ".join(str(item) for args in st.write_calls for item in args),
        )
        self.assertEqual(submitted, {})
        st.session_state[page._FINAL_PREVIEW_TOKEN] = shown
        page.prepare_final_monthly_approval_preview = lambda run_id: self._preview(ready=True)
        page._render_human_outcome(result, registry)
        self.assertIs(submitted["preview"], shown)
        approved_text = " ".join(str(item) for args in st.write_calls for item in args)
        self.assertIn("МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО УТВЕРЖДЕНО", approved_text)
        self.assertIn("amp-page", approved_text)
        self.assertIn("pkg-page", approved_text)
        self.assertIn("run-page", approved_text)

        page.find_current_approved_package = lambda run_id: package
        page._render_next_step("run-page")
        handoff = [
            item
            for item in st.button_calls
            if item["label"] == "ПЕРЕДАТЬ ИНЖЕНЕРУ ПРОИЗВОДСТВЕННОЙ ГОТОВНОСТИ И ДОПУСКА"
        ]
        self.assertEqual(len(handoff), 1)
        self.assertTrue(handoff[0]["disabled"])
        next_text = " ".join(str(item) for args in st.write_calls for item in args)
        self.assertIn("Контур передачи будет подключён следующим шагом", next_text)

        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("sqlite3", source)
        self.assertNotIn("approved_monthly_packages", source)
        self.assertNotIn("st.navigation", source)
        self.assertNotIn("NAV_SECTIONS", source)
        self.assertIn("ПОДТВЕРДИТЬ РЕЗУЛЬТАТ", source)
        command = Path(__file__).resolve().parents[1] / "agents" / "human_surface" / "final_confirm_command.py"
        self.assertNotIn("force_include", command.read_text(encoding="utf-8"))
