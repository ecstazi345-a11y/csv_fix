"""PSAA-02 — append-only Shift Audit History proofs."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from agents.production_shift_auditor.contracts import (
    LaborUnit,
    OperationLaborClaim,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.history_contracts import (
    CODE_HISTORY_CONFLICT,
    CODE_HISTORY_PROJECT_DENIED,
    CODE_HISTORY_WRITE_FAILED,
    STATUS_CREATED,
    STATUS_IDEMPOTENT_REPLAY,
    ShiftAuditHistoryError,
    build_history_record,
)
from agents.production_shift_auditor.history_store import (
    InMemoryShiftAuditHistoryStore,
    open_existing_sqlite_history_store,
    open_sqlite_history_store,
)
from agents.production_shift_auditor.s01_mathematical_integrity import evaluate_s01
from agents.production_shift_auditor.tools import (
    load_shift_audit_history,
    persist_shift_audit_history,
)
from security.agent_execution_context import (
    PSAA_ALLOWED_TOOLS,
    TOOL_PERSIST_SHIFT_AUDIT_HISTORY,
    issue_read_only_agent_context,
)
from security.trusted_read_executor import ToolPermissionError, validate_context_for_tool


class ProfessionalScenarioTests(unittest.TestCase):
    def test_two_sequential_audits_append_only(self) -> None:
        store = InMemoryShiftAuditHistoryStore()
        ctx = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="FIXTURE_INSULATION_DEMO",
        )

        base = build_insulation_pipeline_fixture()
        art1 = evaluate_s01(base, audit_id="audit_hist_v1")
        r1 = persist_shift_audit_history(
            ctx, audit_input=base, artifact=art1, store=store
        )
        self.assertEqual(r1.status, STATUS_CREATED)
        self.assertEqual(art1.s01_metrics.claimed_total_man_minutes, 1425.0)

        # Mutate claimed labor for one operation → new professional audit identity
        ops = list(base.operations)
        changed = replace(ops[0], claimed_labor_quantity=90.0)  # was 30
        ops[0] = changed
        mutated = replace(base, operations=tuple(ops))
        art2 = evaluate_s01(mutated, audit_id="audit_hist_v2")
        self.assertEqual(art2.s01_metrics.claimed_total_man_minutes, 1485.0)
        r2 = persist_shift_audit_history(
            ctx, audit_input=mutated, artifact=art2, store=store
        )
        self.assertEqual(r2.status, STATUS_CREATED)

        rows, meta = load_shift_audit_history(
            ctx,
            store=store,
            work_date=base.work_date,
            crew_id=base.crew_id,
            shift_type=base.shift_type,
        )
        self.assertEqual(meta["row_count"], 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].audit_id, "audit_hist_v1")
        self.assertEqual(rows[1].audit_id, "audit_hist_v2")

        # First result unchanged
        first = store.get_by_audit_id("audit_hist_v1", project_code=base.project_code)
        assert first is not None
        self.assertEqual(first.artifact_snapshot["s01_metrics"]["claimed_total_man_minutes"], 1425.0)
        self.assertEqual(first.math_integrity_status, "COHERENT")
        self.assertNotEqual(first.record_content_hash, rows[1].record_content_hash)

    def test_technical_retry_idempotent(self) -> None:
        store = InMemoryShiftAuditHistoryStore()
        ctx = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="FIXTURE_INSULATION_DEMO",
        )
        base = build_insulation_pipeline_fixture()
        art = evaluate_s01(base, audit_id="audit_idem_1")
        first = persist_shift_audit_history(
            ctx, audit_input=base, artifact=art, store=store
        )
        second = persist_shift_audit_history(
            ctx, audit_input=base, artifact=art, store=store
        )
        self.assertEqual(first.status, STATUS_CREATED)
        self.assertEqual(second.status, STATUS_IDEMPOTENT_REPLAY)
        rows = store.list_for_shift(
            project_code=base.project_code,
            work_date=base.work_date,
            crew_id=base.crew_id,
            shift_type=base.shift_type,
        )
        self.assertEqual(len(rows), 1)

    def test_same_audit_id_different_content_conflicts(self) -> None:
        store = InMemoryShiftAuditHistoryStore()
        ctx = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="FIXTURE_INSULATION_DEMO",
        )
        base = build_insulation_pipeline_fixture()
        art = evaluate_s01(base, audit_id="audit_conflict")
        persist_shift_audit_history(ctx, audit_input=base, artifact=art, store=store)

        ops = list(base.operations)
        ops[0] = replace(ops[0], claimed_labor_quantity=999.0)
        mutated = replace(base, operations=tuple(ops))
        art2 = evaluate_s01(mutated, audit_id="audit_conflict")
        with self.assertRaises(ShiftAuditHistoryError) as err:
            persist_shift_audit_history(
                ctx, audit_input=mutated, artifact=art2, store=store
            )
        self.assertEqual(err.exception.code, CODE_HISTORY_CONFLICT)

    def test_write_failure_fail_closed(self) -> None:
        store = InMemoryShiftAuditHistoryStore(fail_next_write=True)
        ctx = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="FIXTURE_INSULATION_DEMO",
        )
        base = build_insulation_pipeline_fixture()
        art = evaluate_s01(base, audit_id="audit_fail")
        with self.assertRaises(ShiftAuditHistoryError) as err:
            persist_shift_audit_history(
                ctx, audit_input=base, artifact=art, store=store
            )
        self.assertEqual(err.exception.code, CODE_HISTORY_WRITE_FAILED)
        self.assertEqual(
            store.list_for_shift(
                project_code=base.project_code,
                work_date=base.work_date,
                crew_id=base.crew_id,
                shift_type=base.shift_type,
            ),
            (),
        )

    def test_cross_project_access_denied(self) -> None:
        store = InMemoryShiftAuditHistoryStore()
        ctx_a = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="FIXTURE_INSULATION_DEMO",
        )
        base = build_insulation_pipeline_fixture()
        art = evaluate_s01(base, audit_id="audit_proj")
        persist_shift_audit_history(ctx_a, audit_input=base, artifact=art, store=store)

        ctx_b = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="OTHER_PROJECT",
        )
        with self.assertRaises(ShiftAuditHistoryError) as err:
            load_shift_audit_history(ctx_b, store=store, audit_id="audit_proj")
        self.assertEqual(err.exception.code, CODE_HISTORY_PROJECT_DENIED)

        # Persist with mismatched project also denied
        foreign = replace(base, project_code="OTHER_PROJECT")
        art_f = evaluate_s01(foreign, audit_id="audit_proj_foreign")
        with self.assertRaises(ShiftAuditHistoryError) as err2:
            persist_shift_audit_history(
                ctx_a, audit_input=foreign, artifact=art_f, store=store
            )
        self.assertEqual(err2.exception.code, CODE_HISTORY_PROJECT_DENIED)


class SqliteDurabilityTests(unittest.TestCase):
    def test_reopen_sqlite_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "psaa_history.sqlite"
            store = open_sqlite_history_store(path)
            try:
                ctx = issue_read_only_agent_context(
                    agent_code="PRODUCTION_SHIFT_AUDITOR",
                    project_code="FIXTURE_INSULATION_DEMO",
                )
                base = build_insulation_pipeline_fixture()
                art1 = evaluate_s01(base, audit_id="audit_sqlite_1")
                persist_shift_audit_history(
                    ctx, audit_input=base, artifact=art1, store=store
                )
                ops = list(base.operations)
                ops[4] = replace(ops[4], claimed_labor_quantity=210.0)
                mutated = replace(base, operations=tuple(ops))
                art2 = evaluate_s01(mutated, audit_id="audit_sqlite_2")
                persist_shift_audit_history(
                    ctx, audit_input=mutated, artifact=art2, store=store
                )
            finally:
                store.close()

            reopened = open_existing_sqlite_history_store(path)
            assert reopened is not None
            try:
                rows = reopened.list_for_shift(
                    project_code="FIXTURE_INSULATION_DEMO",
                    work_date="2026-01-01",
                    crew_id="FIXTURE_CREW_3",
                    shift_type="DAY",
                )
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0].audit_id, "audit_sqlite_1")
                self.assertEqual(
                    rows[0].artifact_snapshot["s01_metrics"]["claimed_total_man_minutes"],
                    1425.0,
                )
                self.assertEqual(rows[1].audit_id, "audit_sqlite_2")
            finally:
                reopened.close()


class SecurityRegistryTests(unittest.TestCase):
    def test_psaa_tools_include_history(self) -> None:
        ctx = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="PRJ_001_БХК",
        )
        self.assertEqual(ctx.allowed_tools, PSAA_ALLOWED_TOOLS)
        self.assertIs(ctx.write_allowed, False)
        validate_context_for_tool(ctx, TOOL_PERSIST_SHIFT_AUDIT_HISTORY)
        with self.assertRaises(ToolPermissionError):
            validate_context_for_tool(ctx, "load_constructor_scope")

    def test_manifest_lists_persist_tool(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (
                root
                / "agents"
                / "production_shift_auditor"
                / "specification"
                / "security_manifest.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("persist_shift_audit_history", manifest["allowed_tools"])
        self.assertEqual(manifest["write_access"], False)
        self.assertEqual(manifest["product_write_access"], False)
        self.assertIn(
            "persist_shift_audit_history",
            manifest["allowed_artifact_persist_tools"],
        )


class SourceNeutralityTests(unittest.TestCase):
    def test_history_record_has_no_airtable_schema_dependency(self) -> None:
        base = build_insulation_pipeline_fixture()
        art = evaluate_s01(base, audit_id="audit_neutral")
        rec = build_history_record(base, art)
        blob = json.dumps(rec.to_dict(), ensure_ascii=False)
        self.assertIn("FIXTURE", rec.source_kind)
        self.assertNotIn("daily_progress_active", rec.source_kind.lower())
        # Opaque ids only — fixture has none
        self.assertEqual(rec.source_record_ids, ())
        self.assertIn("input_snapshot", blob)
        self.assertIn("artifact_snapshot", blob)


class HumanReadableDualAuditDemo(unittest.TestCase):
    def test_print_friendly_dual_audit(self) -> None:
        store = InMemoryShiftAuditHistoryStore()
        ctx = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="FIXTURE_INSULATION_DEMO",
        )
        base = build_insulation_pipeline_fixture()
        a1 = evaluate_s01(base, audit_id="demo_audit_A")
        persist_shift_audit_history(ctx, audit_input=base, artifact=a1, store=store)

        ops = list(base.operations)
        ops.append(
            OperationLaborClaim("Доп. контроль качества", 20, LaborUnit.MAN_MINUTE)
        )
        mutated = replace(base, operations=tuple(ops))
        a2 = evaluate_s01(mutated, audit_id="demo_audit_B")
        persist_shift_audit_history(
            ctx, audit_input=mutated, artifact=a2, store=store
        )
        rows = store.list_for_shift(
            project_code=base.project_code,
            work_date=base.work_date,
            crew_id=base.crew_id,
            shift_type=base.shift_type,
        )
        self.assertEqual(len(rows), 2)
        # Stable demo assertions
        self.assertEqual(rows[0].artifact_snapshot["s01_metrics"]["claimed_total_man_minutes"], 1425.0)
        self.assertEqual(rows[1].artifact_snapshot["s01_metrics"]["claimed_total_man_minutes"], 1445.0)


if __name__ == "__main__":
    unittest.main()
