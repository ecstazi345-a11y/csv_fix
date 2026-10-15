"""Monthly workspace mode — existing Project+Month+Queue run serves Work Context slices."""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

from agents.control_room.dtos import (
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    ProfessionalResultAvailability,
)
from agents.human_surface.human_review_command import (
    HumanReviewCandidateContext,
    HumanReviewSurfaceSnapshot,
)
from agents.human_surface.mission_command import (
    MissionLaunchResult,
    launch_monthly_plan_mission,
    reset_launch_memory_for_tests,
)
from agents.human_surface.mission_draft import (
    CONSTRUCTOR_AGENT_CODE,
    EXISTING_MONTHLY_ANALYSIS_RU,
    EXISTING_MONTHLY_WORK_ACTION_RU,
    WORK_CONTEXT_OUT_OF_SCOPE_RU,
    WORK_CONTEXT_SLICE_RU,
    WorkingContext,
)
from agents.human_surface.mission_recovery import (
    DurableRunEvidence,
    RecoveredMission,
    find_usable_professional_run,
)
from agents.human_surface.monthly_commitment_draft import reviewed_context_identities
from agents.human_surface.result_view import filter_records_by_work_context
from agents.human_surface.work_context import ScopeFact, WorkContextCatalog
from tests.test_control_room_page_guards import _StreamlitStub

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = REPO_ROOT / "pages" / "53_AI_Центр_управления_агентами.py"
APP_PY = REPO_ROOT / "app.py"
WHEN = datetime(2026, 10, 13, 11, 33, tzinfo=timezone.utc)
OCT_RUN = "run-a0c70277-486b-439d-a6be-7599411ffc37"
OCT_PACKAGE = "3ef26b0e-1f5c-41ef-a06e-e39758749273"


def _catalog() -> WorkContextCatalog:
    return WorkContextCatalog(
        source="test",
        error="",
        months=("октябрь 2026", "ноябрь 2026"),
        facts=(
            ScopeFact(
                project_label="БХК",
                project_code="PRJ_001_БХК",
                queue="1",
                facility="16160-13",
                title="16160-13",
                discipline="Автоматизация",
                systems=("АСУТП",),
                packages=(),
            ),
            ScopeFact(
                project_label="БХК",
                project_code="PRJ_001_БХК",
                queue="1",
                facility="16160-13",
                title="16160-13",
                discipline="Вентиляция",
                systems=("ОВ",),
                packages=(),
            ),
            ScopeFact(
                project_label="БХК",
                project_code="PRJ_001_БХК",
                queue="1",
                facility="16160-17",
                title="16160-17",
                discipline="АКЗ трубопроводов",
                systems=("АКЗ",),
                packages=(),
            ),
        ),
    )


def _context(**overrides: object) -> WorkingContext:
    payload = dict(
        project="БХК",
        planning_month="октябрь 2026",
        queue="1",
        titles=("16160-13",),
        discipline="Автоматизация",
        systems=(),
        packages=None,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        intent="Сформировать кандидатный состав.",
        contour_code="MONTHLY_PRODUCTION_COMMITMENT",
    )
    payload.update(overrides)
    return WorkingContext(**payload)


def _evidence(**overrides: object) -> DurableRunEvidence:
    payload = dict(
        run_id=OCT_RUN,
        mission_id="mission-hs-64b62cbcb56220fb604625d3",
        initiator_id="human-surface",
        agent_code=CONSTRUCTOR_AGENT_CODE,
        project_code="PRJ_001_БХК",
        month_key="октябрь-2026",
        operational_status="RUNNING",
        requested_at=WHEN,
        scope_summary={"facility": ["16160-13", "16160-17"]},
        trigger_reason="Сформировать",
        lifecycle_status="WAITING_FOR_HUMAN_REVIEW",
        has_candidate_package=True,
    )
    payload.update(overrides)
    return DurableRunEvidence(**payload)


def _mission(**overrides: object) -> RecoveredMission:
    payload = dict(
        run_id=OCT_RUN,
        mission_id="mission-hs-64b62cbcb56220fb604625d3",
        project_label="БХК",
        planning_month="октябрь 2026",
        queue="1",
        titles=("16160-13", "16160-17"),
        discipline=None,
        systems=(),
        packages=None,
        intent="Сформировать",
        operational_status="RUNNING",
        lifecycle_status="WAITING_FOR_HUMAN_REVIEW",
        requested_at=WHEN,
    )
    payload.update(overrides)
    return RecoveredMission(**payload)


def _row(
    *,
    facility: str,
    discipline: str,
    outcome: str = "CANDIDATE",
    cid: str = "c1",
    order: int = 1,
) -> ConstructorRowDecisionView:
    return ConstructorRowDecisionView(
        source_identity=f"{order}|{cid}",
        source_order=order,
        boq_code=f"BOQ-{cid}",
        name=f"Work {cid}",
        unit="м",
        system="SYS",
        remaining_qty="10",
        already_planned_qty="0",
        available_qty="10",
        outcome=outcome,
        reason_code=outcome,
        reason_text="stored",
        requires_human=None,
        candidate_created=outcome == "CANDIDATE",
        candidate_id=cid,
        facility=facility,
        discipline=discipline,
        iwp="IWP-1",
    )


def _registry(records: tuple[ConstructorRowDecisionView, ...]) -> ConstructorDecisionRegistryView:
    professional = ConstructorProfessionalResultView(
        availability=ProfessionalResultAvailability.AVAILABLE,
        run_id=OCT_RUN,
        mission_id="mission-hs-64b62cbcb56220fb604625d3",
        professional_status="WAITING_FOR_HUMAN_REVIEW",
        project_id="PRJ_001_БХК",
        month="октябрь-2026",
        facility_id="",
        discipline="",
        source_candidate_package_id=OCT_PACKAGE,
        reviewed_package_id="",
        included_count=None,
        excluded_count=None,
        unresolved_count=None,
        confirm_event_id="",
        confirm_decision="",
        confirm_actor_type="",
        confirm_actor_id="",
        path_statuses=("WAITING_FOR_HUMAN_REVIEW",),
        candidates=(),
        package_candidate_count=len(records),
    )
    return ConstructorDecisionRegistryView(
        availability=ProfessionalResultAvailability.AVAILABLE,
        professional=professional,
        total_count=len(records),
        outcome_counts=(),
        known_systems=(),
        attention_count=0,
        records=records,
    )


def _load_page_module() -> tuple[ModuleType, _StreamlitStub]:
    module_name = "page53_monthly_workspace_mode_test"
    for key in list(sys.modules):
        if key == module_name or key == "streamlit":
            del sys.modules[key]
    st = _StreamlitStub()
    sys.modules["streamlit"] = st
    spec = importlib.util.spec_from_file_location(module_name, PAGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    with patch(
        "agents.human_surface.work_context.load_work_context_catalog",
        return_value=_catalog(),
    ):
        # Page resolves _build_query_port at call time; force safe port None via factory fail.
        with patch.dict("os.environ", {"AGENT_OBSERVABILITY_DB_PATH": ""}, clear=False):
            spec.loader.exec_module(module)
    st.session_state.clear()
    for name in (
        "info_calls",
        "warning_calls",
        "error_calls",
        "write_calls",
        "button_calls",
        "markdown_calls",
        "caption_calls",
    ):
        getattr(st, name).clear()
    return module, st


class FindUsableMonthQueueTests(unittest.TestCase):
    def test_october_usable_found_for_project_month_queue(self) -> None:
        with patch(
            "agents.human_surface.mission_recovery.list_durable_run_evidence",
            return_value=(_evidence(),),
        ):
            found = find_usable_professional_run(
                object(),
                project_code="PRJ_001_БХК",
                month_key="октябрь-2026",
                queue="1",
            )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.run_id, OCT_RUN)

    def test_november_has_no_usable_when_only_october_exists(self) -> None:
        with patch(
            "agents.human_surface.mission_recovery.list_durable_run_evidence",
            return_value=(_evidence(),),
        ):
            found = find_usable_professional_run(
                object(),
                project_code="PRJ_001_БХК",
                month_key="ноябрь-2026",
                queue="1",
            )
        self.assertIsNone(found)


class WorkContextSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = (
            _row(facility="16160-13", discipline="Автоматизация", cid="auto", order=1),
            _row(facility="16160-13", discipline="Вентиляция", cid="vent", order=2),
            _row(facility="16160-17", discipline="АКЗ трубопроводов", cid="akz", order=3),
        )

    def test_automation_slice(self) -> None:
        scoped = filter_records_by_work_context(
            self.records,
            _context(titles=("16160-13",), discipline="Автоматизация"),
        )
        self.assertEqual([r.candidate_id for r in scoped], ["auto"])

    def test_ventilation_slice_same_package(self) -> None:
        scoped = filter_records_by_work_context(
            self.records,
            _context(titles=("16160-13",), discipline="Вентиляция"),
        )
        self.assertEqual([r.candidate_id for r in scoped], ["vent"])

    def test_other_title_discipline_slice(self) -> None:
        scoped = filter_records_by_work_context(
            self.records,
            _context(titles=("16160-17",), discipline="АКЗ трубопроводов"),
        )
        self.assertEqual([r.candidate_id for r in scoped], ["akz"])

    def test_out_of_scope_context_empty_slice(self) -> None:
        scoped = filter_records_by_work_context(
            self.records,
            _context(titles=("88888-00",), discipline="Несуществующая"),
        )
        self.assertEqual(scoped, ())


class LaunchReuseNoNewRunTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_launch_memory_for_tests()

    def test_discipline_and_title_change_reuses_same_run_no_starter(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            raise AssertionError("must not start when monthly usable exists")

        with patch(
            "agents.human_surface.mission_recovery.find_usable_professional_run",
            return_value=_mission(),
        ):
            first = launch_monthly_plan_mission(
                _context(discipline="Автоматизация"),
                _catalog(),
                starter=starter,
                query_port=object(),
            )
            second = launch_monthly_plan_mission(
                _context(discipline="Вентиляция"),
                _catalog(),
                starter=starter,
                query_port=object(),
            )
            third = launch_monthly_plan_mission(
                _context(titles=("16160-17",), discipline="АКЗ трубопроводов"),
                _catalog(),
                starter=starter,
                query_port=object(),
            )
        self.assertEqual(calls, [])
        self.assertTrue(first.reused_existing and second.reused_existing and third.reused_existing)
        self.assertEqual({first.run_id, second.run_id, third.run_id}, {OCT_RUN})

    def test_november_without_usable_calls_starter(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            return MissionLaunchResult(
                run_id="run-nov-new",
                mission_id="mission-nov",
                status="ACCEPTED",
                started_at=WHEN.isoformat(),
                reused_existing=False,
            )

        with patch(
            "agents.human_surface.mission_recovery.find_usable_professional_run",
            return_value=None,
        ):
            result = launch_monthly_plan_mission(
                _context(planning_month="ноябрь 2026"),
                _catalog(),
                starter=starter,
                query_port=object(),
            )
        self.assertEqual(len(calls), 1)
        self.assertFalse(result.reused_existing)
        self.assertEqual(result.run_id, "run-nov-new")


class PageMonthlyWorkspaceModeTests(unittest.TestCase):
    def test_page_ux_guards(self) -> None:
        text = PAGE_PATH.read_text(encoding="utf-8")
        self.assertIn("_ensure_existing_monthly_workspace", text)
        self.assertIn("_bind_usable_run_ids", text)
        self.assertIn("_monthly_workspace_key", text)
        self.assertIn("_render_existing_monthly_workspace_panel", text)
        self.assertIn("_work_context_out_of_package_scope", text)
        self.assertIn("EXISTING_MONTHLY_ANALYSIS_RU", text)
        self.assertIn("Месячный анализ сформирован", text)
        usable_start = text.index(
            "usable = _find_usable_professional_for_context(catalog, context, port)"
        )
        # First usable-hit inside _render_mission_draft returns before ЗАПУСТИТЬ.
        draft_fn = text.index("def _render_mission_draft")
        draft_usable = text.index(
            "usable = _find_usable_professional_for_context(catalog, context, port)",
            draft_fn,
        )
        recognized = text.index('st.markdown("## Задача распознана")', draft_usable)
        usable_block = text[draft_usable:recognized]
        self.assertIn("_render_existing_monthly_workspace_panel", usable_block)
        self.assertIn("return", usable_block)
        self.assertNotIn('st.button("ЗАПУСТИТЬ"', usable_block)
        self.assertTrue(EXISTING_MONTHLY_ANALYSIS_RU)
        self.assertTrue(EXISTING_MONTHLY_WORK_ACTION_RU)
        self.assertTrue(WORK_CONTEXT_OUT_OF_SCOPE_RU)
        self.assertTrue(WORK_CONTEXT_SLICE_RU)
        _ = usable_start

    def test_navigation_unchanged(self) -> None:
        page = PAGE_PATH.read_text(encoding="utf-8")
        app = APP_PY.read_text(encoding="utf-8")
        self.assertNotIn("st.navigation", page)
        self.assertNotIn("NAV_SECTIONS", page)
        self.assertIsNone(re.search(r"st\.set_page_config\s*\(", page))
        self.assertIn("53_AI_Центр_управления_агентами.py", app)

    def test_bind_preserves_work_context_and_monthly_key(self) -> None:
        module, st = _load_page_module()
        auto = _context(discipline="Автоматизация")
        vent = _context(discipline="Вентиляция")
        st.session_state["dynamis_working_context"] = auto
        module._bind_usable_run_ids(_mission(), auto)
        key_auto = module._monthly_workspace_key(auto)
        self.assertEqual(st.session_state["dynamis_active_run_id"], OCT_RUN)
        self.assertEqual(st.session_state["dynamis_launched_mission_identity"], key_auto)
        st.session_state["dynamis_working_context"] = vent
        module._bind_usable_run_ids(_mission(), vent)
        self.assertEqual(module._monthly_workspace_key(vent), key_auto)
        self.assertEqual(st.session_state["dynamis_active_run_id"], OCT_RUN)
        self.assertIs(st.session_state["dynamis_working_context"], vent)
        self.assertEqual(vent.discipline, "Вентиляция")

    def test_ensure_binds_october_clears_november_recovers_october(self) -> None:
        module, st = _load_page_module()
        catalog = _catalog()
        port = object()
        st.session_state["dynamis_working_context"] = _context()
        with patch.object(module, "_find_usable_professional_for_context", return_value=_mission()):
            module._ensure_existing_monthly_workspace(catalog, port)
        self.assertEqual(st.session_state["dynamis_active_run_id"], OCT_RUN)

        st.session_state["dynamis_working_context"] = _context(planning_month="ноябрь 2026")
        with patch.object(module, "_find_usable_professional_for_context", return_value=None), patch(
            "agents.human_surface.mission_recovery.find_usable_professional_run",
            return_value=None,
        ):
            module._ensure_existing_monthly_workspace(catalog, port)
        self.assertNotIn("dynamis_active_run_id", st.session_state)

        st.session_state["dynamis_working_context"] = _context()
        with patch.object(module, "_find_usable_professional_for_context", return_value=_mission()):
            module._ensure_existing_monthly_workspace(catalog, port)
        self.assertEqual(st.session_state["dynamis_active_run_id"], OCT_RUN)

    def test_mission_draft_usable_shows_workspace_not_disabled_launch(self) -> None:
        module, st = _load_page_module()
        catalog = _catalog()
        st.session_state["dynamis_working_context"] = _context()
        with patch.object(module, "_safe_query_port", return_value=object()), patch.object(
            module,
            "_find_usable_professional_for_context",
            return_value=_mission(),
        ):
            module._render_mission_draft(catalog)
        labels = [call["label"] for call in st.button_calls]
        self.assertNotIn("ЗАПУСТИТЬ", labels)
        self.assertTrue(any("Месячный анализ сформирован" in m for m in st.markdown_calls))
        self.assertIn(EXISTING_MONTHLY_ANALYSIS_RU, st.info_calls)
        self.assertEqual(st.session_state["dynamis_active_run_id"], OCT_RUN)

    def test_mission_draft_november_shows_enabled_launch(self) -> None:
        module, st = _load_page_module()
        catalog = _catalog()
        st.session_state["dynamis_working_context"] = _context(planning_month="ноябрь 2026")
        with patch.object(module, "_safe_query_port", return_value=object()), patch.object(
            module,
            "_find_usable_professional_for_context",
            return_value=None,
        ):
            module._render_mission_draft(catalog)
        launch_calls = [c for c in st.button_calls if c["label"] == "ЗАПУСТИТЬ"]
        self.assertEqual(len(launch_calls), 1)
        self.assertFalse(launch_calls[0].get("disabled", False))

    def test_out_of_scope_detection(self) -> None:
        module, _st = _load_page_module()
        registry = _registry(
            (
                _row(facility="16160-13", discipline="Автоматизация", cid="auto"),
                _row(facility="16160-13", discipline="Вентиляция", cid="vent"),
            )
        )
        self.assertFalse(
            module._work_context_out_of_package_scope(
                registry,
                _context(titles=("16160-13",), discipline="Автоматизация"),
            )
        )
        self.assertTrue(
            module._work_context_out_of_package_scope(
                registry,
                _context(titles=("88888-00",), discipline="Несуществующая"),
            )
        )

    def test_f5_style_restore_binds_usable_without_overwriting_slice(self) -> None:
        module, st = _load_page_module()
        catalog = _catalog()
        slice_ctx = _context(discipline="Вентиляция")
        st.session_state["dynamis_working_context"] = slice_ctx
        st.session_state["dynamis_recovery_resolved"] = False
        with patch.object(module, "_find_usable_professional_for_context", return_value=_mission()):
            module._restore_durable_mission_if_needed(object(), catalog)
        self.assertEqual(st.session_state["dynamis_active_run_id"], OCT_RUN)
        self.assertIs(st.session_state["dynamis_working_context"], slice_ctx)
        self.assertEqual(slice_ctx.discipline, "Вентиляция")


class CumulativeDraftSurvivesContextChangeTests(unittest.TestCase):
    def test_reviewed_identities_survive_current_context_change(self) -> None:
        def _cand(
            cid: str,
            facility: str,
            discipline: str,
            *,
            label: str,
        ) -> HumanReviewCandidateContext:
            return HumanReviewCandidateContext(
                candidate_id=cid,
                facility=facility,
                discipline=discipline,
                system="SYS",
                iwp="IWP",
                boq_code=f"BOQ-{cid}",
                name=cid,
                unit="м",
                remaining_qty=10.0,
                already_planned_qty=0.0,
                constructor_proposed_qty=10.0,
                current_decision_label=label,
                warning_lines=(),
            )

        surface = HumanReviewSurfaceSnapshot(
            run_id=OCT_RUN,
            mission_id="mission",
            package_id=OCT_PACKAGE,
            professional_status="WAITING_FOR_HUMAN_REVIEW",
            expected_checkpoint_id="cp",
            interrupt_id="int",
            candidates=(
                _cand("a1", "16160-13", "Автоматизация", label="ПРИНЯТО"),
                _cand("v1", "16160-13", "Вентиляция", label="ПРИНЯТО"),
                _cand("u1", "16160-17", "АКЗ трубопроводов", label="НЕ РАССМОТРЕНО"),
            ),
            reviewed_count=2,
            accepted_count=2,
            changed_qty_count=0,
            excluded_count=0,
            deferred_count=0,
            needs_data_count=0,
            not_reviewed_count=1,
        )
        identities = reviewed_context_identities(surface)
        self.assertEqual(
            identities,
            frozenset(
                {
                    ("16160-13", "Автоматизация"),
                    ("16160-13", "Вентиляция"),
                }
            ),
        )
        # Current Work Context change does not shrink reviewed identities.
        _ = _context(titles=("16160-17",), discipline="АКЗ трубопроводов")
        self.assertEqual(len(identities), 2)


if __name__ == "__main__":
    unittest.main()
