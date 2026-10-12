"""Row-level Constructor decision records. Synthetic data only. No product writes."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

from agents.monthly_plan_constructor.candidate_package import build_candidate_package
from agents.monthly_plan_constructor.domain import (
    REASON_ALREADY_PLANNED,
    REASON_COMPLETED,
    REASON_INVALID,
    REASON_NO_REMAINDER,
    build_constructor_proposal,
    classify_scope_rows,
)
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_PACKAGE_BUILT,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.real_data_assembler import RealDataShadowAdapter
from agents.monthly_plan_constructor.row_decision import (
    OUTCOME_CANDIDATE,
    OUTCOME_UNCLASSIFIED,
    REASON_UNKNOWN,
    known_quantity,
    observe_scope_row,
)
from agents.monthly_plan_constructor.shadow_checkpoint_store import (
    bootstrap_constructor_shadow_checkpoint_store,
)
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver
from tests.test_monthly_plan_constructor_lifecycle import (
    FIXED_AT,
    _advance,
    _candidate_dict,
)
from tests.test_monthly_plan_constructor_real_data_assembler import (
    _capture,
    _mission,
    _scope_row as _assembler_scope_row,
)

PROJECT = "PRJ_001_БХК"
MONTH = "август-2026"
HISTORICAL_RUN_ID = "run-119f4976-8d57-464d-b4d1-629a4128302d"
HISTORICAL_CHECKPOINTS = (
    Path(__file__).resolve().parents[1]
    / ".runtime"
    / "shadow"
    / "constructor"
    / "checkpoints.sqlite"
)


def _scope_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "project_code": PROJECT,
        "facility_building": "Здание А",
        "construction_discipline": "ОВ",
        "facility": "Здание А",
        "discipline": "ОВ",
        "system": "SYS-1",
        "iwp": "IWP-1",
        "boq_code": "BOQ-001",
        "boq_name": "Работа 1",
        "unit": "м3",
        "total_project_qty": 100.0,
        "total_qty": 100.0,
        "executed_qty_all_time": 0.0,
        "executed_qty": 0.0,
        "unit_price": 10.0,
        "total_project_value": 1000.0,
        "total_value": 1000.0,
        "planning_remaining_qty": 100.0,
        "manual_executed_before_system": 0.0,
        "manual_verified_remaining_qty": float("nan"),
    }
    base.update(overrides)
    return base


def _plan_line(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "plan_line_id": "pl-1",
        "client_line_uid": "cuid-1",
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": "Здание А",
        "discipline": "ОВ",
        "system": "SYS-1",
        "iwp": "IWP-1",
        "boq_code": "BOQ-PLANNED",
        "planned_qty": 100.0,
        "crew": "Бригада-1",
        "status": "NOT_SENT",
    }
    base.update(overrides)
    return base


def _proposal(rows: list[dict[str, object]], plans: list[dict[str, object]] | None = None):
    return build_constructor_proposal(
        pd.DataFrame(rows),
        pd.DataFrame(),
        pd.DataFrame(plans or []),
        PROJECT,
        MONTH,
    )


def _by_boq(proposal: dict) -> dict:
    return {record.boq_code: record for record in proposal["row_decisions"]}


class RowDecisionRecordsTest(unittest.TestCase):
    def test_known_quantity_keeps_zero_and_unknown(self) -> None:
        self.assertIsNone(known_quantity(None))
        self.assertIsNone(known_quantity(float("nan")))
        self.assertIsNone(known_quantity(""))
        self.assertEqual(known_quantity(0), 0.0)
        self.assertEqual(known_quantity(0.0), 0.0)

    def test_one_input_row_one_record(self) -> None:
        proposal = _proposal([_scope_row()])
        self.assertTrue(proposal["ok"])
        records = proposal["row_decisions"]
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.boq_code, "BOQ-001")
        self.assertEqual(record.outcome, OUTCOME_CANDIDATE)
        self.assertEqual(record.reason_code, OUTCOME_CANDIDATE)
        self.assertIsNone(record.requires_human)
        self.assertTrue(record.candidate_created)
        self.assertEqual(record.system, "SYS-1")
        self.assertEqual(len(proposal["candidates"]), 1)

    def test_n_rows_n_records_and_package_stays_candidates_only(self) -> None:
        rows = [
            _scope_row(boq_code="BOQ-CAND", boq_name="Кандидат"),
            _scope_row(
                boq_code="BOQ-DONE",
                boq_name="Выполнено",
                total_project_qty=10.0,
                total_qty=10.0,
                executed_qty_all_time=10.0,
                executed_qty=10.0,
                planning_remaining_qty=0.0,
                total_project_value=100.0,
                total_value=100.0,
            ),
            _scope_row(
                boq_code="BOQ-NONE",
                boq_name="Нет остатка",
                total_project_qty=0.0,
                total_qty=0.0,
                executed_qty_all_time=0.0,
                executed_qty=0.0,
                planning_remaining_qty=0.0,
                total_project_value=0.0,
                total_value=0.0,
                unit_price=10.0,
            ),
            _scope_row(
                boq_code="BOQ-PLANNED",
                boq_name="Уже в плане",
                system="",
            ),
            _scope_row(
                boq_code="BOQ-GAP",
                boq_name="Без расчёта",
                system=None,
                unit_price=0.0,
                total_project_value=0.0,
                total_value=0.0,
                total_project_qty=0.0,
                total_qty=0.0,
                executed_qty_all_time=0.0,
                executed_qty=0.0,
                planning_remaining_qty=float("nan"),
            ),
        ]
        proposal = _proposal(rows, [_plan_line()])
        self.assertTrue(proposal["ok"])
        records = proposal["row_decisions"]
        self.assertEqual(len(records), 5)
        self.assertEqual([record.source_order for record in records], [0, 1, 2, 3, 4])
        found = _by_boq(proposal)

        candidate = found["BOQ-CAND"]
        self.assertEqual(candidate.outcome, OUTCOME_CANDIDATE)
        self.assertTrue(candidate.candidate_created)
        self.assertIsNone(candidate.requires_human)
        self.assertEqual(candidate.boq_name, "Кандидат")
        self.assertEqual(candidate.unit, "м3")
        self.assertEqual(candidate.system, "SYS-1")
        self.assertGreater(candidate.remaining_qty, 0)

        completed = found["BOQ-DONE"]
        self.assertEqual(completed.outcome, REASON_COMPLETED)
        self.assertEqual(completed.reason_code, REASON_COMPLETED)
        self.assertFalse(completed.candidate_created)
        self.assertFalse(completed.requires_human)
        self.assertEqual(completed.remaining_qty, 0.0)

        no_remainder = found["BOQ-NONE"]
        self.assertEqual(no_remainder.outcome, REASON_NO_REMAINDER)
        self.assertFalse(no_remainder.candidate_created)
        self.assertEqual(no_remainder.remaining_qty, 0.0)

        planned = found["BOQ-PLANNED"]
        self.assertEqual(planned.outcome, REASON_ALREADY_PLANNED)
        self.assertFalse(planned.candidate_created)
        self.assertEqual(planned.already_planned_qty, 100.0)
        self.assertEqual(planned.available_qty, 0.0)
        self.assertIsNone(planned.system)

        unknown_qty = found["BOQ-GAP"]
        self.assertEqual(unknown_qty.outcome, REASON_INVALID)
        self.assertFalse(unknown_qty.candidate_created)
        self.assertIsNone(unknown_qty.remaining_qty)
        self.assertIsNone(unknown_qty.already_planned_qty)
        self.assertIsNone(unknown_qty.available_qty)
        self.assertIsNone(unknown_qty.system)

        candidate_boqs = {item["boq_code"] for item in proposal["candidates"]}
        self.assertEqual(candidate_boqs, {"BOQ-CAND"})
        self.assertEqual(proposal["counts"]["candidates"], 1)
        self.assertNotEqual(len(records), len(proposal["candidates"]))

    def test_unclassified_row_is_preserved(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "_source_order": 0,
                    "project_code": PROJECT,
                    "facility": "Здание А",
                    "discipline": "ОВ",
                    "boq_code": "BOQ-SKIP",
                    "boq_name": "Без формального исхода",
                    "unit": "м",
                    "system": "SYS-1",
                    "iwp": "IWP-1",
                    "status": "Доступно",
                    "remaining_qty": 1.0,
                    "available_to_add_qty": 5.0,
                    "already_planned_qty": 0.0,
                    "effective_required_qty": 1.0,
                    "executed_total_qty": 0.0,
                    "overrun_qty": 0.0,
                    "total_qty": 1.0,
                    "not_required_qty": 0.0,
                }
            ]
        )
        decisions: list = []
        candidates, exclusions, _issues, counts = classify_scope_rows(
            frame,
            project_code=PROJECT,
            stored_month_key=MONTH,
            month_key_canonical="2026-08",
            row_decisions=decisions,
        )
        self.assertEqual(candidates, [])
        self.assertEqual(exclusions, [])
        self.assertEqual(counts["scanned"], 1)
        self.assertEqual(counts["candidates"], 0)
        self.assertEqual(len(decisions), 1)
        record = decisions[0]
        self.assertEqual(record.outcome, OUTCOME_UNCLASSIFIED)
        self.assertEqual(record.reason_code, REASON_UNKNOWN)
        self.assertIn("не присвоил формальный исход", record.reason_text)
        self.assertFalse(record.candidate_created)
        self.assertIsNone(record.requires_human)
        self.assertEqual(record.remaining_qty, 1.0)
        self.assertEqual(record.available_qty, 5.0)

    def test_lifecycle_advance_stores_records_without_changing_package(self) -> None:
        record = observe_scope_row(
            source_order=0,
            project_code=PROJECT,
            facility="Здание А",
            discipline="ОВ",
            month_key=MONTH,
            system="SYS-1",
            iwp="IWP-1",
            boq_code="BOQ-001",
            boq_name="Работа 1",
            unit="м3",
            remaining_qty=10.0,
            already_planned_qty=0.0,
            available_qty=10.0,
            outcome=OUTCOME_CANDIDATE,
            reason_code=OUTCOME_CANDIDATE,
            reason_text="Строка дошла до candidate level.",
            requires_human=None,
            candidate_created=True,
        )

        class _Assembler:
            def __call__(self, reality_read, scope):
                return CandidateAssemblyResult(
                    candidates=(_candidate_dict(),),
                    scanned_count=1,
                    row_decisions=(record,),
                )

        state = create_lifecycle_state(
            mission_id="mission-row-decision",
            created_at=FIXED_AT,
        )
        self.assertEqual(state.row_decisions, ())
        state = _advance(state)
        state = _advance(state)
        state = _advance(state, assembler=_Assembler())
        self.assertEqual(state.status, STATUS_PACKAGE_BUILT)
        self.assertEqual(state.row_decisions, (record,))
        self.assertEqual(state.package.candidate_count, 1)
        self.assertEqual(len(state.package.candidates), 1)

    def test_real_assembler_keeps_one_record_per_scope_row(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        rows = [
            _assembler_scope_row(boq_code="BOQ-001", boq_name="Кандидат"),
            _assembler_scope_row(
                boq_code="BOQ-EMPTY",
                boq_name="Пустая",
                system=None,
                unit_price=0.0,
                total_project_value=0.0,
                total_project_qty=0.0,
                executed_qty_all_time=0.0,
                planning_remaining_qty=None,
            ),
        ]
        reality = _capture(adapter, mission, scope_rows=rows, plan_rows=[])
        result = adapter(reality, mission)
        self.assertEqual(len(reality.rows), 2)
        self.assertEqual(len(result.row_decisions), 2)
        self.assertEqual(len(result.candidates), 1)
        created = [item for item in result.row_decisions if item.candidate_created]
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].candidate_id, result.candidates[0]["candidate_id"])
        self.assertEqual(created[0].outcome, OUTCOME_CANDIDATE)
        gap = next(item for item in result.row_decisions if item.boq_code == "BOQ-EMPTY")
        self.assertIsNone(gap.remaining_qty)
        self.assertIsNone(gap.already_planned_qty)
        self.assertIsNone(gap.available_qty)
        self.assertFalse(gap.candidate_created)
        package = build_candidate_package(
            mission,
            result.candidates,
            mission_id="mission-row-decision",
            scanned_count=result.scanned_count,
            excluded_completed_count=result.excluded_completed_count,
            excluded_no_remainder_count=result.excluded_no_remainder_count,
            already_planned_count=result.already_planned_count,
        )
        self.assertEqual(package.candidate_count, 1)
        self.assertEqual(len(package.candidates), 1)
        self.assertNotEqual(len(result.row_decisions), package.candidate_count)

    def test_serializer_and_checkpoint_roundtrip(self) -> None:
        record = observe_scope_row(
            source_order=0,
            project_code=PROJECT,
            facility="Здание А",
            discipline="ОВ",
            month_key=MONTH,
            system=None,
            iwp="",
            boq_code="BOQ-GAP",
            boq_name="Без количества",
            unit="м",
            remaining_qty=None,
            already_planned_qty=None,
            available_qty=None,
            outcome=OUTCOME_UNCLASSIFIED,
            reason_code=REASON_UNKNOWN,
            reason_text="Текущий pipeline не присвоил формальный исход этой строке.",
            requires_human=None,
            candidate_created=False,
        )
        zero = observe_scope_row(
            source_order=1,
            project_code=PROJECT,
            facility="Здание А",
            discipline="ОВ",
            month_key=MONTH,
            system="SYS-1",
            iwp="IWP-1",
            boq_code="BOQ-ZERO",
            boq_name="Ноль",
            unit="м",
            remaining_qty=0.0,
            already_planned_qty=0.0,
            available_qty=0.0,
            outcome=REASON_COMPLETED,
            reason_code=REASON_COMPLETED,
            reason_text="Позиция полностью выполнена (executed >= total).",
            requires_human=False,
            candidate_created=False,
        )
        state = replace(
            create_lifecycle_state(
                mission_id="mission-row-decision",
                run_id="run-row-decision",
            ),
            row_decisions=(record, zero),
        )
        serde = build_constructor_jsonplus_serializer()
        restored = serde.loads_typed(serde.dumps_typed(state))
        self.assertIsInstance(restored, ConstructorLifecycleState)
        self.assertEqual(len(restored.row_decisions), 2)
        self.assertIsNone(restored.row_decisions[0].remaining_qty)
        self.assertIsNone(restored.row_decisions[0].already_planned_qty)
        self.assertIsNone(restored.row_decisions[0].available_qty)
        self.assertIsNone(restored.row_decisions[0].requires_human)
        self.assertEqual(restored.row_decisions[1].remaining_qty, 0.0)
        self.assertFalse(restored.row_decisions[1].requires_human)
        self.assertEqual(restored.row_decisions[0].outcome, OUTCOME_UNCLASSIFIED)

        with tempfile.TemporaryDirectory() as tmp:
            store = bootstrap_constructor_shadow_checkpoint_store(
                repository_root=tmp,
            )
            try:
                checkpoint = empty_checkpoint()
                checkpoint["channel_values"] = {"lifecycle": state}
                config = {
                    "configurable": {
                        "thread_id": "run-row-decision",
                        "checkpoint_ns": "",
                    }
                }
                store.checkpointer.put(
                    config,
                    checkpoint,
                    {"source": "input", "step": 0},
                    {},
                )
                loaded = store.checkpointer.get_tuple(config)
                self.assertIsNotNone(loaded)
                durable = loaded.checkpoint["channel_values"]["lifecycle"]
                self.assertEqual(len(durable.row_decisions), 2)
                self.assertIsNone(durable.row_decisions[0].remaining_qty)
                self.assertEqual(durable.row_decisions[1].remaining_qty, 0.0)
                self.assertEqual(durable.row_decisions[0].reason_code, REASON_UNKNOWN)
            finally:
                store.close()

    def test_historical_checkpoint_still_loads_without_records(self) -> None:
        if not HISTORICAL_CHECKPOINTS.is_file():
            self.skipTest("historical shadow checkpoint is not on this machine")
        uri = HISTORICAL_CHECKPOINTS.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
        try:
            checkpointer = SqliteSaver(
                connection,
                serde=build_constructor_jsonplus_serializer(),
            )
            loaded = checkpointer.get_tuple(
                {
                    "configurable": {
                        "thread_id": HISTORICAL_RUN_ID,
                        "checkpoint_ns": "",
                    }
                }
            )
        finally:
            connection.close()
        self.assertIsNotNone(loaded)
        lifecycle = loaded.checkpoint["channel_values"]["lifecycle"]
        self.assertIsInstance(lifecycle, ConstructorLifecycleState)
        self.assertEqual(lifecycle.row_decisions, ())
        self.assertEqual(len(lifecycle.package.candidates), 2)


if __name__ == "__main__":
    unittest.main()
