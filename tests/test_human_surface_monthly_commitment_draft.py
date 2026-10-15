"""Cumulative Monthly Commitment Draft — reviewed Work Contexts only."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from agents.human_surface.human_review_batch import (
    BatchResolution,
    prepare_batch_from_text,
    submit_human_review_batch,
)
from agents.human_surface.human_review_command import (
    HumanReviewCandidateContext,
    HumanReviewCommandError,
    HumanReviewSurfaceSnapshot,
    prepare_human_review_surface,
)
from agents.human_surface.human_review_focus import (
    build_focus_set_from_work_context,
)
from agents.human_surface.mission_draft import WorkingContext
from agents.human_surface.monthly_commitment_draft import (
    NON_CANDIDATE_CLARIFICATION_RU,
    STATUS_ACCEPTED,
    STATUS_BASELINE,
    build_monthly_commitment_draft,
    build_work_context_review_summary,
    composition_table_dicts,
    reviewed_context_identities,
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

FIXED_AT = datetime(2026, 10, 14, 16, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run-draft-001"
MISSION_ID = "mission-draft-001"
PROJECT = "PRJ_001_БХК"
MONTH = "октябрь-2026"
PAGE = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "53_AI_Центр_управления_агентами.py"
)


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
    already: float = 0.0,
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
        "already_planned_qty": already,
        "available_to_add_qty": qty,
        "availability_status": "AVAILABLE",
        "labor_norm_status": LABOR_VALIDATED,
    }


def _package():
    items = [
        _cand("c01", facility="16160-13", discipline="Автоматизация", boq="2041-01-01-01", qty=10, already=5),
        _cand("c02", facility="16160-13", discipline="Автоматизация", boq="2041-01-02-01", qty=20),
        _cand("c03", facility="16160-13", discipline="Автоматизация", boq="2041-01-03-01", qty=30),
        _cand("c04", facility="16160-13", discipline="Автоматизация", boq="2041-01-04-01", qty=40),
        _cand("c05", facility="16160-13", discipline="Автоматизация", boq="2041-01-05-01", qty=50),
        _cand("c06", facility="16160-13", discipline="Автоматизация", boq="2041-01-06-01", qty=60),
        _cand("c07", facility="16160-13", discipline="Автоматизация", boq="2041-01-07-01", qty=70),
        _cand("c08", facility="16160-13", discipline="Автоматизация", boq="2041-01-08-01", qty=80),
        _cand("c09", facility="16160-13", discipline="Вентиляция", boq="2041-02-01-01", qty=15, already=3),
        _cand("c10", facility="16160-17", discipline="Автоматизация", boq="2041-01-01-01", qty=25),
        _cand("c11", facility="16160-13", discipline="АКЗ трубопроводов", boq="2300-01-01-01", qty=12, already=8),
        _cand("c12", facility="16160-13", discipline="Изоляция трубопроводов", boq="2041-02-07-14", qty=9, already=4),
    ]
    return build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items),
        run_id=RUN_ID,
        snapshot_id="snap-draft",
        created_at=FIXED_AT.isoformat(),
        exception_summary=PackageExceptionSummary(
            blocking_count=0, non_blocking_count=0, warning_count=0
        ),
    )


def _lifecycle() -> ConstructorLifecycleState:
    package = _package()
    state = create_lifecycle_state(
        mission_id=MISSION_ID, run_id=RUN_ID, authorization_id="auth-draft", created_at=FIXED_AT
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
        self.checkpoint_id = "ckpt-draft-1"
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
        self.checkpoint_id = f"ckpt-draft-{self.resume_calls + 1}"
        return self.lifecycle


def _defer_event(candidate_id: str, reason: str, *, package_id: str) -> object:
    return build_human_review_event(
        review_event_id=f"ev-{candidate_id}",
        run_id=RUN_ID,
        mission_id=MISSION_ID,
        package_id=package_id,
        candidate_id=candidate_id,
        decision=HumanReviewDecision.REMOVE,
        actor_id="human_surface",
        reviewed_at=FIXED_AT,
        constructor_proposed_qty=10.0,
        human_approved_qty=0.0,
        reason_text=reason,
        resolution_kind=RESOLUTION_KIND_DEFER_TO_PERIOD,
        target_period="2026-11",
    )


def _disciplines_in_draft(draft) -> set[str]:
    found: set[str] = set()
    for row in draft.composition_rows:
        found.add(row.discipline)
    for row in draft.deferred_rows:
        found.add(row.discipline)
    for row in draft.excluded_rows:
        found.add(row.discipline)
    return found


def _facilities_in_draft(draft) -> set[str]:
    found: set[str] = set()
    for bucket in (
        draft.composition_rows,
        draft.deferred_rows,
        draft.excluded_rows,
        draft.needs_data_rows,
    ):
        for row in bucket:
            found.add(row.facility)
    return found


class MonthlyCommitmentDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = _FakeRuntime(_lifecycle())
        package = self.runtime.lifecycle.package
        assert package is not None
        seeded = normalize_human_review_events(
            (
                _defer_event("c01", "НЕ ГОТОВ ФРОНТ", package_id=package.package_id),
                _defer_event("c06", "НЕТ КОМПЛЕКТАЦИИ", package_id=package.package_id),
            ),
            package,
        )
        self.runtime.lifecycle = replace(
            self.runtime.lifecycle, human_review_events=seeded
        )
        self.surface = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        self.context = WorkingContext(
            titles=("16160-13",),
            discipline="Автоматизация",
        )
        self.focus = build_focus_set_from_work_context(
            self.surface, self.context, created_at=FIXED_AT
        )

    def test_01_remainder_accepts_only_unresolved_in_context(self) -> None:
        self.assertEqual(self.focus.size, 8)
        summary = build_work_context_review_summary(self.surface, self.focus)
        self.assertEqual(summary.deferred, 2)
        self.assertEqual(summary.not_reviewed, 6)

        preview = prepare_batch_from_text(
            "ОСТАЛЬНЫЕ ПРИНЯТЬ",
            focus=self.focus,
            surface=self.surface,
        )
        self.assertEqual(preview.counts.accept, 6)
        self.assertEqual(preview.counts.defer, 0)
        self.assertEqual(preview.prior_deferred_in_focus, 2)
        self.assertEqual(preview.prior_unresolved_in_focus, 6)
        accepted_ids = {
            op.candidate_id
            for op in preview.draft.operations
            if op.resolution is BatchResolution.ACCEPT
        }
        self.assertEqual(len(accepted_ids), 6)
        self.assertNotIn("c01", accepted_ids)
        self.assertNotIn("c06", accepted_ids)
        self.assertEqual(self.runtime.resume_calls, 0)

    def test_02_remainder_does_not_leak_outside_context(self) -> None:
        preview = prepare_batch_from_text(
            "остальные принять",
            focus=self.focus,
            surface=self.surface,
        )
        for op in preview.draft.operations:
            self.assertIn(op.candidate_id, self.focus.ordered_candidate_ids)
        vent = build_focus_set_from_work_context(
            self.surface,
            WorkingContext(titles=("16160-13",), discipline="Вентиляция"),
            created_at=FIXED_AT,
        )
        self.assertEqual(vent.size, 1)
        self.assertNotIn("c09", self.focus.ordered_candidate_ids)

    def test_03_confirm_remainder_builds_reviewed_context_draft_only(self) -> None:
        preview = prepare_batch_from_text(
            "остальные принять",
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
        again = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        draft = build_monthly_commitment_draft(again)
        self.assertEqual(
            reviewed_context_identities(again),
            frozenset({("16160-13", "Автоматизация")}),
        )
        self.assertEqual(draft.counts.deferred, 2)
        self.assertEqual(draft.counts.added_constructor, 6)
        # c01 deferred with already_planned — excluded from month composition (MINUS DEFER).
        self.assertEqual(draft.counts.baseline, 0)
        # Unrelated package contexts are outside draft scope.
        self.assertEqual(draft.counts.unresolved, 0)
        self.assertEqual(_disciplines_in_draft(draft), {"Автоматизация"})
        self.assertEqual(_facilities_in_draft(draft), {"16160-13"})
        self.assertNotIn("Вентиляция", _disciplines_in_draft(draft))
        self.assertNotIn("АКЗ трубопроводов", _disciplines_in_draft(draft))
        self.assertNotIn("Изоляция трубопроводов", _disciplines_in_draft(draft))
        composition_ids = {row.candidate_id for row in draft.composition_rows}
        self.assertNotIn("c01", composition_ids)  # deferred, not baseline composition
        self.assertNotIn("c06", composition_ids)
        self.assertNotIn("c09", composition_ids)
        self.assertNotIn("c10", composition_ids)
        self.assertNotIn("c11", composition_ids)
        self.assertNotIn("c12", composition_ids)
        for cid in ("c02", "c03", "c04", "c05", "c07", "c08"):
            self.assertIn(cid, composition_ids)

    def test_04_selecting_unreviewed_context_does_not_add_baseline(self) -> None:
        preview = prepare_batch_from_text(
            "остальные принять",
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
        rebuilt = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        # Merely building focus for Ventilation must not enlarge draft.
        build_focus_set_from_work_context(
            rebuilt,
            WorkingContext(titles=("16160-13",), discipline="Вентиляция"),
            created_at=FIXED_AT,
        )
        draft = build_monthly_commitment_draft(rebuilt)
        self.assertNotIn("Вентиляция", _disciplines_in_draft(draft))
        self.assertNotIn("c09", {row.candidate_id for row in draft.composition_rows})
        self.assertEqual(draft.counts.baseline, 0)

    def test_05_cumulative_union_across_reviewed_contexts(self) -> None:
        preview = prepare_batch_from_text(
            "остальные принять",
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
        rebuilt = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        draft_a = build_monthly_commitment_draft(rebuilt)
        self.assertEqual(_facilities_in_draft(draft_a), {"16160-13"})

        title17 = build_focus_set_from_work_context(
            rebuilt,
            WorkingContext(titles=("16160-17",), discipline="Автоматизация"),
            created_at=FIXED_AT,
        )
        submit_human_review_batch(
            prepare_batch_from_text(
                "остальные принять",
                focus=title17,
                surface=rebuilt,
            ).draft,
            focus=title17,
            runtime=self.runtime,
            now=FIXED_AT,
            confirmed=True,
        )
        mid = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        draft_mid = build_monthly_commitment_draft(mid)
        self.assertEqual(_facilities_in_draft(draft_mid), {"16160-13", "16160-17"})
        self.assertEqual(draft_mid.counts.added_constructor, 7)
        self.assertIn("c10", {row.candidate_id for row in draft_mid.composition_rows})

        vent_focus = build_focus_set_from_work_context(
            mid,
            WorkingContext(titles=("16160-13",), discipline="Вентиляция"),
            created_at=FIXED_AT,
        )
        submit_human_review_batch(
            prepare_batch_from_text(
                "остальные принять",
                focus=vent_focus,
                surface=mid,
            ).draft,
            focus=vent_focus,
            runtime=self.runtime,
            now=FIXED_AT,
            confirmed=True,
        )
        final = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        draft_b = build_monthly_commitment_draft(final)
        self.assertEqual(draft_b.counts.added_constructor, 8)
        self.assertEqual(draft_b.counts.deferred, 2)
        # Ventilation baseline (c09 already_planned) enters only after its review.
        self.assertEqual(draft_b.counts.baseline, 1)
        self.assertIn("Вентиляция", _disciplines_in_draft(draft_b))
        accepted = {
            row.candidate_id
            for row in draft_b.composition_rows
            if row.source_status == STATUS_ACCEPTED
        }
        self.assertIn("c09", accepted)
        for cid in ("c02", "c03", "c04", "c05", "c07", "c08", "c10"):
            self.assertIn(cid, accepted)
        # Same BOQ across physical titles stays separate once both reviewed.
        same_boq = [
            row
            for row in draft_b.composition_rows
            if row.boq_code == "2041-01-01-01"
        ]
        self.assertTrue(any(row.candidate_id == "c10" for row in same_boq))
        self.assertTrue(
            any(row.facility == "16160-17" and row.source_status == STATUS_ACCEPTED for row in same_boq)
        )
        # Prior automation survives; AKZ / Insulation still unreviewed → absent.
        self.assertNotIn("АКЗ трубопроводов", _disciplines_in_draft(draft_b))
        self.assertNotIn("Изоляция трубопроводов", _disciplines_in_draft(draft_b))
        again = build_monthly_commitment_draft(
            prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        )
        self.assertEqual(again.counts.added_constructor, draft_b.counts.added_constructor)
        self.assertEqual(len(composition_table_dicts(again)), len(composition_table_dicts(draft_b)))

    def test_06_empty_before_any_review_ignores_package_wide_baseline(self) -> None:
        clean = _FakeRuntime(_lifecycle())
        surface = prepare_human_review_surface(RUN_ID, runtime=clean)
        draft = build_monthly_commitment_draft(surface)
        self.assertEqual(reviewed_context_identities(surface), frozenset())
        self.assertEqual(draft.counts.baseline, 0)
        self.assertEqual(draft.composition_rows, ())
        self.assertEqual(draft.counts.unresolved, 0)

    def test_07_non_candidate_reference_fail_closed(self) -> None:
        with self.assertRaises(HumanReviewCommandError) as ctx:
            prepare_batch_from_text(
                "№99 исключить. Причина.",
                focus=self.focus,
                surface=self.surface,
            )
        self.assertEqual(ctx.exception.message, NON_CANDIDATE_CLARIFICATION_RU)
        self.assertEqual(self.runtime.resume_calls, 0)

    def test_08_page_guards_and_no_production_writes(self) -> None:
        text = PAGE.read_text(encoding="utf-8")
        self.assertIn("build_monthly_commitment_draft", text)
        self.assertIn("Текущий черновик месячного обязательства", text)
        self.assertIn("Итоговых позиций", text)
        self.assertIn("NON_CANDIDATE_CLARIFICATION_RU", text)
        self.assertNotIn(
            'if surface is not None and focus is not None and view_id == "candidates"',
            text,
        )
        self.assertIn("if surface is not None and focus is not None:", text)
        self.assertNotIn("monthly_plan_lines_v2", text)
        draft_src = (
            Path(__file__).resolve().parents[1]
            / "agents"
            / "human_surface"
            / "monthly_commitment_draft.py"
        ).read_text(encoding="utf-8")
        self.assertIn("reviewed_context_identities", draft_src)
        self.assertIn("durably reviewed", draft_src)
        self.assertNotIn("st.session_state", draft_src)
        self.assertIn("Streamlit session_state is not used", draft_src)
        self.assertIn("Базовый объём", draft_src)
        self.assertIn("Добавлено Constructor", draft_src)
        self.assertIn("Итоговый объём", draft_src)
        self.assertIn("_normalize_residue", draft_src)


class ProfessionalCompositionViewTests(unittest.TestCase):
    """Projection-only merge of baseline + Constructor delta for one physical identity."""

    def _surface(self, *candidates: HumanReviewCandidateContext) -> HumanReviewSurfaceSnapshot:
        reviewed = sum(
            1
            for item in candidates
            if str(item.current_decision_label or "").strip()
            and str(item.current_decision_label) != "НЕ РАССМОТРЕНО"
        )
        return HumanReviewSurfaceSnapshot(
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            package_id="pkg-professional-view",
            professional_status=STATUS_WAITING_FOR_HUMAN_REVIEW,
            expected_checkpoint_id="ckpt",
            interrupt_id="int",
            candidates=candidates,
            reviewed_count=reviewed,
            accepted_count=sum(
                1 for item in candidates if item.current_decision_label == STATUS_ACCEPTED
            ),
            changed_qty_count=0,
            excluded_count=sum(
                1 for item in candidates if item.current_decision_label == "ИСКЛЮЧЕНО"
            ),
            deferred_count=sum(
                1 for item in candidates if item.current_decision_label == "ПЕРЕНЕСЕНО"
            ),
            needs_data_count=0,
            not_reviewed_count=sum(
                1
                for item in candidates
                if not str(item.current_decision_label or "").strip()
                or item.current_decision_label == "НЕ РАССМОТРЕНО"
            ),
        )

    def _cand(
        self,
        cid: str,
        *,
        facility: str,
        discipline: str,
        boq: str,
        baseline: float,
        proposed: float,
        label: str,
        system: str = "SYS-1",
        iwp: str = "IWP-1",
        unit: str = "м",
        name: str | None = None,
    ) -> HumanReviewCandidateContext:
        return HumanReviewCandidateContext(
            candidate_id=cid,
            facility=facility,
            discipline=discipline,
            system=system,
            iwp=iwp,
            boq_code=boq,
            name=name or f"Work {cid}",
            unit=unit,
            remaining_qty=baseline + proposed,
            already_planned_qty=baseline,
            constructor_proposed_qty=proposed,
            current_decision_label=label,
            warning_lines=(),
            human_approved_qty=proposed if label == STATUS_ACCEPTED else None,
        )

    def test_01_baseline_plus_accept_one_row_final_584(self) -> None:
        surface = self._surface(
            self._cand(
                "c-akz",
                facility="16160-17",
                discipline="Автоматизация",
                boq="1500-04-01-01",
                baseline=450.0,
                proposed=134.0,
                label=STATUS_ACCEPTED,
                unit="шт",
            )
        )
        draft = build_monthly_commitment_draft(surface)
        self.assertEqual(len(draft.composition_rows), 1)
        self.assertEqual(draft.counts.final_positions, 1)
        self.assertEqual(draft.counts.baseline, 1)
        self.assertEqual(draft.counts.added_constructor, 1)
        row = draft.composition_rows[0]
        self.assertEqual(row.boq_code, "1500-04-01-01")
        self.assertEqual(row.baseline_qty, 450.0)
        self.assertEqual(row.constructor_delta_qty, 134.0)
        self.assertEqual(row.final_qty, 584.0)
        self.assertEqual(row.source_status, STATUS_ACCEPTED)
        table = composition_table_dicts(draft)[0]
        self.assertEqual(table["Базовый объём"], "450")
        self.assertEqual(table["Добавлено Constructor"], "134")
        self.assertEqual(table["Итоговый объём"], "584")

    def test_02_baseline_907_plus_001_final_908(self) -> None:
        surface = self._surface(
            self._cand(
                "c-vent-22",
                facility="16160-13",
                discipline="Вентиляция",
                boq="2041-01-22-02",
                baseline=9.07,
                proposed=0.01,
                label=STATUS_ACCEPTED,
                unit="м2",
            )
        )
        draft = build_monthly_commitment_draft(surface)
        self.assertEqual(len(draft.composition_rows), 1)
        row = draft.composition_rows[0]
        self.assertEqual(row.baseline_qty, 9.07)
        self.assertEqual(row.constructor_delta_qty, 0.01)
        self.assertAlmostEqual(row.final_qty, 9.08, places=12)
        self.assertEqual(composition_table_dicts(draft)[0]["Итоговый объём"], "9.08")

    def test_03_float_residue_normalized_to_zero_delta(self) -> None:
        surface = self._surface(
            self._cand(
                "c-vent-27",
                facility="16160-13",
                discipline="Вентиляция",
                boq="2041-01-27-02",
                baseline=1.15,
                proposed=2.22045e-15,
                label=STATUS_ACCEPTED,
                unit="м3",
            )
        )
        draft = build_monthly_commitment_draft(surface)
        self.assertEqual(len(draft.composition_rows), 1)
        row = draft.composition_rows[0]
        self.assertEqual(row.baseline_qty, 1.15)
        self.assertEqual(row.constructor_delta_qty, 0.0)
        self.assertEqual(row.final_qty, 1.15)
        table = composition_table_dicts(draft)[0]
        self.assertEqual(table["Добавлено Constructor"], "0")
        self.assertEqual(table["Итоговый объём"], "1.15")

    def test_04_same_boq_different_title_never_merged(self) -> None:
        surface = self._surface(
            self._cand(
                "c-a",
                facility="16160-13",
                discipline="Автоматизация",
                boq="2041-01-01-01",
                baseline=0.0,
                proposed=10.0,
                label=STATUS_ACCEPTED,
            ),
            self._cand(
                "c-b",
                facility="16160-17",
                discipline="Автоматизация",
                boq="2041-01-01-01",
                baseline=0.0,
                proposed=25.0,
                label=STATUS_ACCEPTED,
            ),
        )
        draft = build_monthly_commitment_draft(surface)
        self.assertEqual(len(draft.composition_rows), 2)
        by_facility = {row.facility: row for row in draft.composition_rows}
        self.assertEqual(by_facility["16160-13"].final_qty, 10.0)
        self.assertEqual(by_facility["16160-17"].final_qty, 25.0)

    def test_05_same_boq_different_system_or_package_never_merged(self) -> None:
        surface = self._surface(
            self._cand(
                "c-sys-a",
                facility="16160-13",
                discipline="Вентиляция",
                boq="2041-01-22-02",
                baseline=1.0,
                proposed=0.5,
                label=STATUS_ACCEPTED,
                system="SYS-A",
                iwp="IWP-A",
            ),
            self._cand(
                "c-sys-b",
                facility="16160-13",
                discipline="Вентиляция",
                boq="2041-01-22-02",
                baseline=2.0,
                proposed=0.25,
                label=STATUS_ACCEPTED,
                system="SYS-B",
                iwp="IWP-B",
            ),
        )
        draft = build_monthly_commitment_draft(surface)
        self.assertEqual(len(draft.composition_rows), 2)
        systems = {row.system for row in draft.composition_rows}
        self.assertEqual(systems, {"SYS-A", "SYS-B"})
        self.assertTrue(all(row.identity_warning == "" for row in draft.composition_rows))

    def test_06_defer_and_exclude_out_of_final_composition(self) -> None:
        surface = self._surface(
            self._cand(
                "c-ok",
                facility="16160-13",
                discipline="Автоматизация",
                boq="2041-01-02-01",
                baseline=5.0,
                proposed=1.0,
                label=STATUS_ACCEPTED,
            ),
            self._cand(
                "c-def",
                facility="16160-13",
                discipline="Автоматизация",
                boq="2041-01-03-01",
                baseline=5.0,
                proposed=2.0,
                label="ПЕРЕНЕСЕНО",
            ),
            self._cand(
                "c-ex",
                facility="16160-13",
                discipline="Автоматизация",
                boq="2041-01-04-01",
                baseline=5.0,
                proposed=3.0,
                label="ИСКЛЮЧЕНО",
            ),
        )
        draft = build_monthly_commitment_draft(surface)
        self.assertEqual([row.candidate_id for row in draft.composition_rows], ["c-ok"])
        self.assertEqual(draft.counts.final_positions, 1)
        self.assertEqual(draft.counts.deferred, 1)
        self.assertEqual(draft.counts.excluded, 1)
        self.assertEqual(len(draft.deferred_rows), 1)
        self.assertEqual(len(draft.excluded_rows), 1)

    def test_07_reload_reconstructs_identical_view(self) -> None:
        surface = self._surface(
            self._cand(
                "c1",
                facility="16160-13",
                discipline="Вентиляция",
                boq="2041-01-27-02",
                baseline=1.15,
                proposed=2.22045e-15,
                label=STATUS_ACCEPTED,
                unit="м3",
            ),
            self._cand(
                "c2",
                facility="16160-13",
                discipline="Вентиляция",
                boq="2041-01-22-02",
                baseline=9.07,
                proposed=0.01,
                label=STATUS_ACCEPTED,
                unit="м2",
            ),
            self._cand(
                "c3",
                facility="16160-17",
                discipline="Автоматизация",
                boq="1500-04-01-01",
                baseline=450.0,
                proposed=134.0,
                label=STATUS_ACCEPTED,
            ),
        )
        first = build_monthly_commitment_draft(surface)
        second = build_monthly_commitment_draft(surface)
        self.assertEqual(first.composition_rows, second.composition_rows)
        self.assertEqual(first.counts, second.counts)
        self.assertEqual(composition_table_dicts(first), composition_table_dicts(second))
        self.assertEqual(first.counts.final_positions, 3)
        by_boq = {row.boq_code: row for row in first.composition_rows}
        self.assertEqual(by_boq["2041-01-27-02"].final_qty, 1.15)
        self.assertEqual(by_boq["2041-01-27-02"].constructor_delta_qty, 0.0)
        self.assertAlmostEqual(by_boq["2041-01-22-02"].final_qty, 9.08, places=12)
        self.assertEqual(by_boq["1500-04-01-01"].final_qty, 584.0)


if __name__ == "__main__":
    unittest.main()
