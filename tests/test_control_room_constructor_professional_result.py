"""
Control Room professional Constructor result: read-only checkpoint adapter.

No product writes. Checkpoint fixtures are temporary and opened by the reader
in SQLite read-only mode.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver

from agents.control_room.constructor_professional_result_reader import (
    ConstructorProfessionalResultReader,
    map_constructor_row_decisions,
    transcribe_stored_quantity,
)
from agents.control_room.dtos import (
    ConstructorCandidateResultView,
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    ProfessionalResultAvailability,
)
from agents.control_room.presentation import (
    constructor_decision_summary_tiles,
    constructor_exclusion_line,
    constructor_final_confirm_allowed,
    constructor_funnel_warnings,
    constructor_hitl_review_decision,
    constructor_management_scale_lines,
    constructor_processing_scale_lines,
    constructor_quantity_display,
    constructor_row_outcome_label,
    constructor_workspace_views,
    human_confirm_decision_ru,
    human_review_decision_ru,
    human_review_decision_short_ru,
    professional_status_ru,
)
from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.monthly_plan_constructor.row_decision import observe_scope_row
from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    build_candidate_package,
)
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
)
from agents.monthly_plan_constructor.human_confirm_contracts import (
    HumanConfirmDecision,
    build_human_confirm_event,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    HumanReviewDecision,
    build_human_review_event,
)
from agents.monthly_plan_constructor.langgraph_runtime import CONSTRUCTOR_AGENT_CODE
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_PROFESSIONAL_WORK_COMPLETED,
    ConstructorLifecycleState,
    LifecycleTransition,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import build_constructor_mission_scope
from agents.monthly_plan_constructor.reviewed_candidate_package import (
    build_reviewed_candidate_package,
)
from agents.monthly_plan_constructor.secure_read_tools import (
    SCHEMA_VERSION,
    ConstructorReadProvenance,
    ConstructorRealityRead,
    ConstructorRealityRow,
)
from agents.observability.contracts import (
    InitiatorType,
    OperationalStatus,
    TriggerType,
    build_agent_run,
)
from agents.observability.store import InMemoryObservabilityStore

RUN_ID = "run-professional-1"
MISSION_ID = "mission-professional-1"
PROJECT = "PRJ_001_БХК"
MONTH = "октябрь-2026"
STAMP = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
QTY_A = 0.00999999999999801
QTY_B = 2.220446049250313e-15


def _scope():
    return build_constructor_mission_scope(
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=("16160-13",),
        discipline_scope=("ВЕНТИЛЯЦИЯ",),
    )


def _candidate(candidate_id: str, boq_code: str, available: float) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": "16160-13",
        "discipline": "ВЕНТИЛЯЦИЯ",
        "system": "",
        "iwp": "",
        "queue": "",
        "boq_code": boq_code,
        "boq_name": boq_code,
        "unit": "м2",
        "remaining_qty": 9.079999999999998,
        "already_planned_qty": 9.07,
        "available_to_add_qty": available,
        "availability_status": "AVAILABLE",
        "labor_norm_status": LABOR_UNRESOLVED,
        "recommendation": "HUMAN_REVIEW_REQUIRED",
    }


def _reality(scope, row_count: int = 80) -> ConstructorRealityRead:
    rows = tuple(
        ConstructorRealityRow(
            project_code=PROJECT,
            month_key=MONTH,
            facility="16160-13",
            discipline="ВЕНТИЛЯЦИЯ",
            system="",
            iwp="",
            queue="",
            boq_code=f"ROW-{index}",
            boq_name="",
            unit="",
        )
        for index in range(row_count)
    )
    provenance = ConstructorReadProvenance(
        read_id="read-1",
        read_at="2026-10-09T12:00:00Z",
        tool_name="load_scope",
        project_code=PROJECT,
        month_key=MONTH,
        authorization_id="auth-1",
        row_count=row_count,
        source_reference="monthly_scope_picker_view",
    )
    return ConstructorRealityRead(
        read_id="read-1",
        schema_version=SCHEMA_VERSION,
        read_at="2026-10-09T12:00:00Z",
        tool_name="load_scope",
        project_code=PROJECT,
        month_key=MONTH,
        scope=scope,
        row_count=row_count,
        rows=rows,
        provenance=provenance,
        warnings=(),
    )


def _completed_lifecycle() -> ConstructorLifecycleState:
    scope = _scope()
    package = build_candidate_package(
        scope,
        [
            _candidate("cand-a", "2041-01-22-02", QTY_A),
            _candidate("cand-b", "2041-01-27-02", QTY_B),
        ],
        mission_id=MISSION_ID,
        run_id=RUN_ID,
        scanned_count=64,
        excluded_completed_count=38,
        excluded_no_remainder_count=20,
        already_planned_count=3,
    )
    reviews = [
        build_human_review_event(
            review_event_id=f"rev-{item.candidate_id}",
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            package_id=package.package_id,
            candidate_id=item.candidate_id,
            decision=HumanReviewDecision.REMOVE,
            actor_id="human-owner",
            reviewed_at=STAMP,
        )
        for item in package.candidates
    ]
    reviewed = build_reviewed_candidate_package(
        package, reviews, (), created_at=STAMP
    )
    confirm = build_human_confirm_event(
        confirm_event_id="cfm-1",
        reviewed_package_id=reviewed.reviewed_package_id,
        source_candidate_package_id=package.package_id,
        run_id=RUN_ID,
        mission_id=MISSION_ID,
        decision=HumanConfirmDecision.CONFIRM,
        actor_id="human-owner",
        confirmed_at=STAMP,
    )
    base = create_lifecycle_state(
        mission_id=MISSION_ID, run_id=RUN_ID, created_at=STAMP
    )
    return replace(
        base,
        status=STATUS_PROFESSIONAL_WORK_COMPLETED,
        scope=scope,
        reality_read=_reality(scope),
        package=package,
        reviewed_package=reviewed,
        human_confirm_events=(confirm,),
        transitions=(
            LifecycleTransition(
                from_status="CREATED",
                to_status=STATUS_PROFESSIONAL_WORK_COMPLETED,
                at=STAMP,
            ),
        ),
    )


def _put_lifecycle(path: Path, lifecycle: ConstructorLifecycleState) -> None:
    connection = sqlite3.connect(path)
    try:
        saver = SqliteSaver(connection, serde=build_constructor_jsonplus_serializer())
        saver.setup()
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"lifecycle": lifecycle}
        checkpoint["channel_versions"] = {"lifecycle": "1"}
        saver.put(
            {"configurable": {"thread_id": lifecycle.run_id, "checkpoint_ns": ""}},
            checkpoint,
            {"source": "input", "step": 1, "writes": {}, "parents": {}},
            {"lifecycle": "1"},
        )
    finally:
        connection.close()


class QuantityTranscriptionTests(unittest.TestCase):
    def test_residuals_stay_distinct(self) -> None:
        left = transcribe_stored_quantity(QTY_A)
        right = transcribe_stored_quantity(QTY_B)
        self.assertNotEqual(left, right)
        self.assertNotEqual(left, "0")
        self.assertNotEqual(right, "0")
        self.assertEqual(left, format(QTY_A, ".16g"))
        self.assertEqual(right, format(QTY_B, ".16g"))


class ConstructorProfessionalResultReaderTests(unittest.TestCase):
    def test_missing_checkpoint_does_not_create_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            reader = ConstructorProfessionalResultReader(path)
            result = reader.read(run_id=RUN_ID, agent_code=CONSTRUCTOR_AGENT_CODE)
            self.assertEqual(result.availability, ProfessionalResultAvailability.UNAVAILABLE)
            self.assertFalse(path.exists())

    def test_open_is_readonly_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            _put_lifecycle(path, _completed_lifecycle())
            calls: list[tuple[object, ...]] = []
            real_connect = sqlite3.connect

            def _capture(*args, **kwargs):
                calls.append(args)
                return real_connect(*args, **kwargs)

            reader = ConstructorProfessionalResultReader(path)
            with patch(
                "agents.control_room.constructor_professional_result_reader.sqlite3.connect",
                _capture,
            ):
                result = reader.read(run_id=RUN_ID, agent_code=CONSTRUCTOR_AGENT_CODE)
            self.assertEqual(result.availability, ProfessionalResultAvailability.AVAILABLE)
            self.assertEqual(len(calls), 1)
            self.assertIn("mode=ro", str(calls[0][0]))

    def test_missing_run_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            _put_lifecycle(path, _completed_lifecycle())
            result = ConstructorProfessionalResultReader(path).read(
                run_id="run-other", agent_code=CONSTRUCTOR_AGENT_CODE
            )
            self.assertEqual(result.availability, ProfessionalResultAvailability.UNAVAILABLE)

    def test_non_lifecycle_is_inconsistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            lifecycle = _completed_lifecycle()
            broken = replace(lifecycle, scope="not-a-scope")
            _put_lifecycle(path, broken)
            result = ConstructorProfessionalResultReader(path).read(
                run_id=RUN_ID, agent_code=CONSTRUCTOR_AGENT_CODE
            )
            self.assertEqual(result.availability, ProfessionalResultAvailability.INCONSISTENT)

    def test_completed_round_trip_maps_scale_and_quantities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            _put_lifecycle(path, _completed_lifecycle())
            result = ConstructorProfessionalResultReader(path).read(
                run_id=RUN_ID, agent_code=CONSTRUCTOR_AGENT_CODE
            )
        self.assertEqual(result.availability, ProfessionalResultAvailability.AVAILABLE)
        self.assertEqual(result.project_id, PROJECT)
        self.assertEqual(result.month, MONTH)
        self.assertEqual(result.facility_id, "16160-13")
        self.assertEqual(result.discipline, "ВЕНТИЛЯЦИЯ")
        self.assertEqual(result.professional_status, STATUS_PROFESSIONAL_WORK_COMPLETED)
        self.assertEqual(result.included_count, 0)
        self.assertEqual(result.excluded_count, 2)
        self.assertEqual(result.unresolved_count, 0)
        self.assertEqual(result.confirm_decision, "CONFIRM")
        self.assertEqual(result.mission_scope_row_count, 80)
        self.assertEqual(result.scanned_count, 64)
        self.assertEqual(result.excluded_completed_count, 38)
        self.assertEqual(result.excluded_no_remainder_count, 20)
        self.assertEqual(result.already_planned_count, 3)
        self.assertEqual(result.package_candidate_count, 2)
        quantities = {item.boq_code: item.available_qty for item in result.candidates}
        self.assertEqual(quantities["2041-01-22-02"], format(QTY_A, ".16g"))
        self.assertEqual(quantities["2041-01-27-02"], format(QTY_B, ".16g"))
        self.assertTrue(all(item.human_review_decision == "REMOVE" for item in result.candidates))
        self.assertTrue(all(item.final_disposition == "EXCLUDED" for item in result.candidates))


class ConstructorProfessionalQueryPortTests(unittest.TestCase):
    def _store(self):
        store = InMemoryObservabilityStore()
        store.create_run(
            build_agent_run(
                run_id=RUN_ID,
                request_id="req-1",
                agent_code=CONSTRUCTOR_AGENT_CODE,
                agent_version="0.1",
                mission_id=MISSION_ID,
                project_code=PROJECT,
                month_key=MONTH,
                initiator_type=InitiatorType.HUMAN,
                initiator_id="operator",
                trigger_type=TriggerType.MANUAL,
                trigger_reason="test",
                operational_status=OperationalStatus.REQUESTED,
                requested_at=STAMP,
                updated_at=STAMP,
                thread_id=RUN_ID,
            )
        )
        return store

    def test_result_comes_only_through_the_port(self) -> None:
        class _Reader:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def read(self, *, run_id: str, agent_code: str) -> ConstructorProfessionalResultView:
                self.calls.append((run_id, agent_code))
                return ConstructorProfessionalResultView(
                    availability=ProfessionalResultAvailability.AVAILABLE,
                    run_id=run_id,
                    mission_id=MISSION_ID,
                    professional_status=STATUS_PROFESSIONAL_WORK_COMPLETED,
                    project_id=PROJECT,
                    month=MONTH,
                    facility_id="16160-13",
                    discipline="ВЕНТИЛЯЦИЯ",
                    source_candidate_package_id="pkg",
                    reviewed_package_id="rev",
                    included_count=0,
                    excluded_count=2,
                    unresolved_count=0,
                    confirm_event_id="cfm",
                    confirm_decision="CONFIRM",
                    confirm_actor_type="HUMAN",
                    confirm_actor_id="human",
                    path_statuses=(),
                    candidates=(),
                    package_candidate_count=2,
                )

        reader = _Reader()
        port = AgentControlRoomQueryPort(self._store(), professional_result_reader=reader)
        result = port.get_constructor_professional_result(RUN_ID)
        snapshot = port.get_run_snapshot(RUN_ID)
        self.assertEqual(reader.calls, [(RUN_ID, CONSTRUCTOR_AGENT_CODE)])
        self.assertEqual(result.package_candidate_count, 2)
        self.assertEqual(snapshot.run.run_id, RUN_ID)

    def test_missing_reader_stays_unavailable_and_snapshot_still_reads(self) -> None:
        port = AgentControlRoomQueryPort(self._store())
        result = port.get_constructor_professional_result(RUN_ID)
        snapshot = port.get_run_snapshot(RUN_ID)
        self.assertEqual(result.availability, ProfessionalResultAvailability.UNAVAILABLE)
        self.assertIsNone(result.included_count)
        self.assertIsNone(result.scanned_count)
        self.assertEqual(snapshot.run.run_id, RUN_ID)

    def test_reader_exception_is_inconsistent(self) -> None:
        class _Reader:
            def read(self, *, run_id: str, agent_code: str):
                raise RuntimeError("checkpoint unreadable")

        port = AgentControlRoomQueryPort(self._store(), professional_result_reader=_Reader())
        result = port.get_constructor_professional_result(RUN_ID)
        self.assertEqual(result.availability, ProfessionalResultAvailability.INCONSISTENT)
        self.assertIsNone(result.scanned_count)


class ConstructorProfessionalPresentationTests(unittest.TestCase):
    def test_russian_labels_and_partial_scale_do_not_invent_81(self) -> None:
        result = ConstructorProfessionalResultView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            professional_status=STATUS_PROFESSIONAL_WORK_COMPLETED,
            project_id=PROJECT,
            month=MONTH,
            facility_id="16160-13",
            discipline="ВЕНТИЛЯЦИЯ",
            source_candidate_package_id="pkg",
            reviewed_package_id="rev",
            included_count=0,
            excluded_count=2,
            unresolved_count=0,
            confirm_event_id="cfm",
            confirm_decision="CONFIRM",
            confirm_actor_type="HUMAN",
            confirm_actor_id="human",
            path_statuses=(STATUS_PROFESSIONAL_WORK_COMPLETED,),
            candidates=(
                ConstructorCandidateResultView(
                    candidate_id="cand-a",
                    boq_code="2041-01-22-02",
                    name="Позиция",
                    unit="м2",
                    remaining_qty="9.079999999999998",
                    already_planned_qty="9.07",
                    available_qty=format(QTY_A, ".16g"),
                    labor_status="UNRESOLVED",
                    recommendation="HUMAN_REVIEW_REQUIRED",
                    exception_codes=(),
                    human_review_decision="REMOVE",
                    final_disposition="EXCLUDED",
                    final_reason_code="HUMAN_REMOVE",
                ),
            ),
            mission_scope_row_count=80,
            scanned_count=64,
            excluded_completed_count=38,
            excluded_no_remainder_count=20,
            already_planned_count=3,
            package_candidate_count=2,
        )
        lines = "\n".join(constructor_processing_scale_lines(result))
        self.assertIn("В релевантном scope: 80", lines)
        self.assertIn("Просканировано при сборке кандидатов: 64", lines)
        self.assertIn("Исключено выполненное: 38", lines)
        self.assertIn("Исключено без остатка: 20", lines)
        self.assertIn("Учтено уже запланированное: 3", lines)
        self.assertIn("Кандидатов на рассмотрение: 2", lines)
        self.assertIn("0 включено / 2 исключено / 0 нерешённых", lines)
        self.assertIn("нет сохранённой причины исключения: 16", lines)
        self.assertIn("не закрывают скан: 1", lines)
        self.assertNotIn("81", lines)
        self.assertEqual(professional_status_ru(result.professional_status), "Работа завершена")
        self.assertEqual(human_review_decision_ru("REMOVE"), "Исключить из текущего кандидатного состава")
        self.assertEqual(human_confirm_decision_ru("CONFIRM"), "Подтверждено человеком")
        note = constructor_exclusion_line(result.candidates[0])
        self.assertEqual(note, "Исключено из текущего кандидатного состава решением человека.")
        joined = lines + " " + str(note)
        self.assertNotIn("месячный план утверждён", joined.casefold())
        self.assertNotIn("admission", joined.casefold())
        self.assertNotIn("executability", joined.casefold())

    def test_management_scale_hides_unexplained_gaps(self) -> None:
        result = ConstructorProfessionalResultView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            professional_status=STATUS_PROFESSIONAL_WORK_COMPLETED,
            project_id=PROJECT,
            month=MONTH,
            facility_id="16160-13",
            discipline="ВЕНТИЛЯЦИЯ",
            source_candidate_package_id="pkg",
            reviewed_package_id="rev",
            included_count=0,
            excluded_count=2,
            unresolved_count=0,
            confirm_event_id="cfm",
            confirm_decision="CONFIRM",
            confirm_actor_type="HUMAN",
            confirm_actor_id="human",
            path_statuses=(),
            candidates=(),
            mission_scope_row_count=80,
            scanned_count=64,
            excluded_completed_count=38,
            excluded_no_remainder_count=20,
            already_planned_count=3,
            package_candidate_count=2,
        )
        primary = "\n".join(constructor_management_scale_lines(result))
        forensic = "\n".join(constructor_processing_scale_lines(result))
        self.assertIn("В scope: 80", primary)
        self.assertIn("Просканировано: 64", primary)
        self.assertIn("Кандидатов Constructor: 2", primary)
        self.assertNotIn("16", primary)
        self.assertNotIn("81", primary)
        self.assertIn("нет сохранённой причины исключения: 16", forensic)
        warnings = "\n".join(constructor_funnel_warnings(result))
        self.assertIn("16 строк: детальная причина перехода в сохранённых данных не подтверждена", warnings)
        self.assertIn("1 проверенная строка: классификация не зафиксирована", warnings)
        view_labels = " ".join(label for _key, label in constructor_workspace_views(result))
        self.assertNotIn("Все 80", view_labels)

    def test_quantity_display_rounds_without_changing_stored_text(self) -> None:
        self.assertEqual(constructor_quantity_display("9.079999999999998", "м2"), "9,08 м²")
        self.assertEqual(constructor_quantity_display("9.07", "м2"), "9,07 м²")
        self.assertEqual(constructor_quantity_display("0.00999999999999801", "м2"), "0,01 м²")
        self.assertEqual(constructor_quantity_display("1.150000000000002", "м3"), "1,15 м³")
        self.assertEqual(constructor_quantity_display("1.15", "м3"), "1,15 м³")
        self.assertEqual(
            constructor_quantity_display("2.220446049250313e-15", "м3"),
            "≈ 0 м³",
        )
        self.assertEqual(human_review_decision_short_ru("REMOVE"), "Исключить")
        self.assertEqual(constructor_quantity_display("9.079999999999998", "м2 / m2"), "9,08 м²")
        self.assertEqual(constructor_quantity_display("2.220446049250313e-15", "м3 / m3"), "≈ 0 м³")
        self.assertEqual(constructor_hitl_review_decision("OK"), "ADD")
        self.assertEqual(constructor_hitl_review_decision("NOT_OK"), "REMOVE")
        self.assertEqual(constructor_hitl_review_decision("NEED_DATA"), "REQUIRES_CLARIFICATION")
        self.assertFalse(
            constructor_final_confirm_allowed(
                "PROFESSIONAL_WORK_COMPLETED",
                candidates_decided=2,
                candidate_count=2,
                write_path_available=False,
            )
        )
        self.assertTrue(
            constructor_final_confirm_allowed(
                "WAITING_FOR_HUMAN_REVIEW",
                candidates_decided=2,
                candidate_count=2,
                write_path_available=True,
            )
        )

    def test_exclusion_line_only_for_remove_and_excluded(self) -> None:
        kept = ConstructorCandidateResultView(
            candidate_id="cand-a",
            boq_code="BOQ",
            name="",
            unit="",
            remaining_qty="1",
            already_planned_qty="0",
            available_qty="1",
            labor_status="",
            recommendation="",
            exception_codes=(),
            human_review_decision="ADD",
            final_disposition="INCLUDED",
            final_reason_code="",
        )
        self.assertIsNone(constructor_exclusion_line(kept))


class _Run:
    def __init__(self) -> None:
        self.agent_code = CONSTRUCTOR_AGENT_CODE


class _Store:
    def get_run(self, run_id: str) -> _Run:
        return _Run()


class DecisionRegistryQueryTest(unittest.TestCase):
    def test_port_exposes_eighty_records_filters_and_keeps_unknown_quantity(self) -> None:
        professional = ConstructorProfessionalResultView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            run_id="run-80",
            mission_id="mission-80",
            professional_status="WAITING_FOR_HUMAN_REVIEW",
            project_id="PRJ_001_БХК",
            month="октябрь-2026",
            facility_id="16160-13",
            discipline="ВЕНТИЛЯЦИЯ",
            source_candidate_package_id="pkg",
            reviewed_package_id="",
            included_count=None,
            excluded_count=None,
            unresolved_count=None,
            confirm_event_id="",
            confirm_decision="",
            confirm_actor_type="",
            confirm_actor_id="",
            path_statuses=("WAITING_FOR_HUMAN_REVIEW",),
            candidates=(
                ConstructorCandidateResultView(
                    candidate_id="c-1",
                    boq_code="BOQ-C1",
                    name="Кандидат 1",
                    unit="м2",
                    remaining_qty="1",
                    already_planned_qty="0",
                    available_qty="1",
                    labor_status="UNRESOLVED",
                    recommendation="HUMAN_REVIEW_REQUIRED",
                    exception_codes=(),
                    human_review_decision="",
                    final_disposition="",
                    final_reason_code="",
                ),
                ConstructorCandidateResultView(
                    candidate_id="c-2",
                    boq_code="BOQ-C2",
                    name="Кандидат 2",
                    unit="м2",
                    remaining_qty="1",
                    already_planned_qty="0",
                    available_qty="1",
                    labor_status="UNRESOLVED",
                    recommendation="HUMAN_REVIEW_REQUIRED",
                    exception_codes=(),
                    human_review_decision="",
                    final_disposition="",
                    final_reason_code="",
                ),
            ),
            package_candidate_count=2,
        )
        stored = (
            observe_scope_row(
                source_order=0,
                project_code="PRJ",
                facility="F",
                discipline="D",
                month_key="октябрь-2026",
                system=None,
                iwp="",
                boq_code="BOQ-GAP",
                boq_name="Без количества",
                unit="м",
                remaining_qty=None,
                already_planned_qty=None,
                available_qty=None,
                outcome="EXCLUDED_INVALID",
                reason_code="EXCLUDED_INVALID",
                reason_text="Нет исходных количеств.",
                requires_human=False,
                candidate_created=False,
            ),
            observe_scope_row(
                source_order=1,
                project_code="PRJ",
                facility="F",
                discipline="D",
                month_key="октябрь-2026",
                system="AHU",
                iwp="",
                boq_code="BOQ-ZERO",
                boq_name="Ноль",
                unit="м",
                remaining_qty=0.0,
                already_planned_qty=0.0,
                available_qty=0.0,
                outcome="EXCLUDED_COMPLETED",
                reason_code="EXCLUDED_COMPLETED",
                reason_text="Выполнено.",
                requires_human=False,
                candidate_created=False,
            ),
        )
        mapped = map_constructor_row_decisions(
            type("Life", (), {"row_decisions": stored, "reality_read": type("Reality", (), {"row_count": 2})()})()
        )
        self.assertIsNone(mapped[0].remaining_qty)
        self.assertEqual(mapped[1].remaining_qty, "0")
        records = _eighty(mapped[0])
        reader = type(
            "Reader",
            (),
            {
                "read": lambda self, *, run_id, agent_code: professional,
                "read_row_decisions": lambda self, *, run_id, agent_code: records,
            },
        )()
        port = AgentControlRoomQueryPort(_Store(), professional_result_reader=reader)
        full = port.get_constructor_decision_registry("run-80")
        self.assertEqual(full.total_count, 80)
        self.assertEqual(sum(count for _name, count in full.outcome_counts), 80)
        self.assertEqual(full.attention_count, 2)
        completed = port.get_constructor_decision_registry("run-80", outcome="EXCLUDED_COMPLETED")
        self.assertEqual(len(completed.records), 38)
        self.assertEqual(completed.total_count, 80)
        found = port.get_constructor_decision_registry("run-80", text="решет")
        self.assertEqual(len(found.records), 1)
        self.assertEqual(found.records[0].boq_code, "BOQ-C1")
        selected = port.get_constructor_decision_registry(
            "run-80",
            selected_identity=records[0].source_identity,
        )
        self.assertIsNotNone(selected.selected)
        self.assertIsNone(selected.selected.remaining_qty)
        attention = port.get_constructor_decision_registry("run-80", attention_only=True)
        self.assertEqual(len(attention.records), 2)
        self.assertTrue(all(item.outcome == "CANDIDATE" for item in attention.records))

    def test_inconsistent_quantities_outcome_propagates_in_read_model(self) -> None:
        stored = observe_scope_row(
            source_order=0,
            project_code="PRJ",
            facility="16160-13",
            discipline="ОВ",
            month_key="октябрь-2026",
            system="SYS-1",
            iwp="",
            boq_code="BOQ-INCONSISTENT",
            boq_name="Несогласованные объёмы",
            unit="м2",
            remaining_qty=10.0,
            already_planned_qty=15.0,
            available_qty=0.0,
            outcome="EXCLUDED_INCONSISTENT_QUANTITIES",
            reason_code="EXCLUDED_INCONSISTENT_QUANTITIES",
            reason_text=(
                "already_planned превышает физический остаток; "
                "строка исключена из Candidate Package без изменения исходных величин."
            ),
            requires_human=True,
            candidate_created=False,
        )
        mapped = map_constructor_row_decisions(
            type(
                "Life",
                (),
                {
                    "row_decisions": (stored,),
                    "reality_read": type("Reality", (), {"row_count": 1})(),
                },
            )()
        )
        self.assertEqual(len(mapped), 1)
        record = mapped[0]
        self.assertEqual(record.outcome, "EXCLUDED_INCONSISTENT_QUANTITIES")
        self.assertEqual(record.reason_code, "EXCLUDED_INCONSISTENT_QUANTITIES")
        self.assertFalse(record.candidate_created)
        self.assertNotEqual(record.outcome, "UNKNOWN")
        self.assertEqual(record.remaining_qty, "10")
        self.assertEqual(record.already_planned_qty, "15")
        self.assertEqual(record.available_qty, "0")
        label = constructor_row_outcome_label(record.outcome)
        self.assertIn("already_planned превышает физический остаток", label)
        self.assertNotEqual(label, "EXCLUDED_INCONSISTENT_QUANTITIES")
        registry = ConstructorDecisionRegistryView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            professional=ConstructorProfessionalResultView(
                availability=ProfessionalResultAvailability.AVAILABLE,
                run_id="run-inconsistent",
                mission_id="mission-inconsistent",
                professional_status="PACKAGE_BUILT",
                project_id="PRJ",
                month="октябрь-2026",
                facility_id="",
                discipline="",
                source_candidate_package_id="pkg-1",
                reviewed_package_id="",
                included_count=None,
                excluded_count=None,
                unresolved_count=None,
                confirm_event_id="",
                confirm_decision="",
                confirm_actor_type="",
                confirm_actor_id="",
                path_statuses=(),
                candidates=(),
                package_candidate_count=0,
            ),
            total_count=1,
            outcome_counts=(("EXCLUDED_INCONSISTENT_QUANTITIES", 1),),
            known_systems=("SYS-1",),
            attention_count=0,
            records=mapped,
        )
        tiles = dict(constructor_decision_summary_tiles(registry))
        self.assertEqual(tiles.get("НЕСОГЛАСОВАННЫЕ ОБЪЁМЫ"), "1")


def _eighty(unknown: ConstructorRowDecisionView) -> tuple[ConstructorRowDecisionView, ...]:
    from dataclasses import replace

    rows = [unknown]
    plan = (
        ("CANDIDATE", 2),
        ("EXCLUDED_COMPLETED", 38),
        ("EXCLUDED_NO_REMAINDER", 20),
        ("EXCLUDED_ALREADY_PLANNED", 3),
        ("EXCLUDED_INVALID", 15),
        ("EXCLUDED_OVERRUN", 1),
    )
    order = 1
    for outcome, count in plan:
        for index in range(count):
            boq = "BOQ-C1" if outcome == "CANDIDATE" and index == 0 else (
                "BOQ-C2" if outcome == "CANDIDATE" else f"BOQ-{order:03d}"
            )
            name = "Решетка" if boq == "BOQ-C1" else f"Работа {order}"
            rows.append(
                replace(
                    unknown,
                    source_identity=f"{order}|{boq}",
                    source_order=order,
                    boq_code=boq,
                    name=name,
                    system="AHU" if outcome == "EXCLUDED_COMPLETED" else None,
                    remaining_qty="0" if outcome != "EXCLUDED_INVALID" else None,
                    already_planned_qty="0" if outcome != "EXCLUDED_INVALID" else None,
                    available_qty="0" if outcome != "EXCLUDED_INVALID" else None,
                    outcome=outcome,
                    reason_code=outcome,
                    reason_text="Сохранённое основание",
                    requires_human=None if outcome == "CANDIDATE" else False,
                    candidate_created=outcome == "CANDIDATE",
                    candidate_id="c-1" if boq == "BOQ-C1" else ("c-2" if boq == "BOQ-C2" else ""),
                )
            )
            order += 1
    return tuple(rows)


if __name__ == "__main__":
    unittest.main()
