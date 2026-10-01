"""LND-R1 labor_norm_decisions service tests — no live DB / no Constructor."""

from __future__ import annotations

import math
import os
import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.labor_norm_decisions import (
    APPROVED_BY_OPERATOR_LABEL_NOTE,
    DECISION_APPROVED_PROVISIONAL,
    DECISION_MANUAL_PROVISIONAL,
    DECISION_REJECTED,
    DECISION_RU,
    FORBIDDEN_DECISION_CODES,
    HINT_WARNING_RU,
    LaborNormDecisionDraft,
    MemoryLaborNormDecisionStore,
    SERVICE_ROLE_MISSING_MSG,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    SupabaseLaborNormDecisionStore,
    get_active_decision,
    list_decisions,
    normalize_decision_code,
    require_service_role_client,
    save_decision,
    validate_decision_draft,
)

SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "labor_norm_decisions_r1.sql"


def _draft(**overrides):
    payload = {
        "project_code": "PRJ_001_БХК",
        "facility_building": "16160-13",
        "construction_discipline": "Вентиляция",
        "boq_code": "2041-01-27-04",
        "unit_of_measure": "м2 / m2",
        "decision": DECISION_APPROVED_PROVISIONAL,
        "approved_by": "operator.test",
        "comment": "временная норма для планирования",
        "approved_norm": 1.325,
        "boq_name": "Покрытие",
        "suggested_norm": 1.325,
        "suggested_source": "HISTORICAL_P50_HINT",
        "sample_count": 2,
        "confidence": "LOW",
        "expected_unit": "м2 / m2",
    }
    payload.update(overrides)
    return LaborNormDecisionDraft(**payload)


class LaborNormDecisionValidationTests(unittest.TestCase):
    def test_approved_provisional_valid(self) -> None:
        err, normalized = validate_decision_draft(_draft())
        self.assertIsNone(err)
        assert normalized is not None
        self.assertEqual(normalized.decision, DECISION_APPROVED_PROVISIONAL)
        self.assertEqual(normalized.approved_norm, 1.325)
        self.assertNotEqual(normalized.decision, "VALIDATED")

    def test_manual_provisional_valid(self) -> None:
        err, normalized = validate_decision_draft(
            _draft(decision=DECISION_MANUAL_PROVISIONAL, approved_norm=2.5)
        )
        self.assertIsNone(err)
        assert normalized is not None
        self.assertEqual(normalized.decision, DECISION_MANUAL_PROVISIONAL)
        self.assertEqual(normalized.approved_norm, 2.5)

    def test_rejected_without_norm(self) -> None:
        err, normalized = validate_decision_draft(
            _draft(decision=DECISION_REJECTED, approved_norm=None)
        )
        self.assertIsNone(err)
        assert normalized is not None
        self.assertIsNone(normalized.approved_norm)

    def test_zero_norm_rejected(self) -> None:
        err, _ = validate_decision_draft(_draft(approved_norm=0))
        self.assertIsNotNone(err)

    def test_negative_norm_rejected(self) -> None:
        err, _ = validate_decision_draft(_draft(approved_norm=-1))
        self.assertIsNotNone(err)

    def test_nan_inf_rejected(self) -> None:
        err_nan, _ = validate_decision_draft(_draft(approved_norm=float("nan")))
        err_inf, _ = validate_decision_draft(_draft(approved_norm=float("inf")))
        self.assertIsNotNone(err_nan)
        self.assertIsNotNone(err_inf)
        self.assertTrue(math.isnan(float("nan")))

    def test_unit_mismatch_fail_closed(self) -> None:
        err, _ = validate_decision_draft(
            _draft(unit_of_measure="м3 / m3", expected_unit="м2 / m2")
        )
        self.assertIsNotNone(err)
        self.assertIn("единиц", (err or "").lower())

    def test_validated_code_forbidden(self) -> None:
        self.assertIn("VALIDATED", FORBIDDEN_DECISION_CODES)
        self.assertEqual(normalize_decision_code("VALIDATED"), "")
        err, _ = validate_decision_draft(_draft(decision="VALIDATED"))
        self.assertIsNotNone(err)

    def test_page_guard_unsupported_decision_code(self) -> None:
        self.assertEqual(normalize_decision_code("Официальная норма ГЭСН"), "")
        self.assertEqual(normalize_decision_code("APPROVED_VALIDATED"), "")
        for label in DECISION_RU.values():
            self.assertIn(normalize_decision_code(label), {
                DECISION_APPROVED_PROVISIONAL,
                DECISION_MANUAL_PROVISIONAL,
                DECISION_REJECTED,
            })

    def test_suggested_p50_never_becomes_validated(self) -> None:
        err, normalized = validate_decision_draft(
            _draft(suggested_norm=20.0, decision=DECISION_APPROVED_PROVISIONAL)
        )
        self.assertIsNone(err)
        assert normalized is not None
        self.assertEqual(normalized.suggested_source, "HISTORICAL_P50_HINT")
        self.assertEqual(normalized.decision, DECISION_APPROVED_PROVISIONAL)
        self.assertNotEqual(normalized.decision, "VALIDATED")
        self.assertIn("подсказк", HINT_WARNING_RU.lower())

    def test_approved_by_required(self) -> None:
        err, _ = validate_decision_draft(_draft(approved_by=""))
        self.assertIsNotNone(err)
        self.assertIn("approved_by", (err or "").lower())

    def test_approved_by_documented_as_operator_label(self) -> None:
        self.assertIn("операторской меткой", APPROVED_BY_OPERATOR_LABEL_NOTE)
        self.assertIn("Криптографическая идентификация", APPROVED_BY_OPERATOR_LABEL_NOTE)
        self.assertNotIn("verified_user", APPROVED_BY_OPERATOR_LABEL_NOTE.lower())
        self.assertNotIn("authenticated_user", APPROVED_BY_OPERATOR_LABEL_NOTE.lower())


class LaborNormDecisionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryLaborNormDecisionStore()

    def test_approved_saves(self) -> None:
        result = save_decision(_draft(), store=self.store)
        self.assertTrue(result["ok"], result.get("error"))
        active = get_active_decision(
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-04",
            store=self.store,
        )
        assert active is not None
        self.assertEqual(active.decision, DECISION_APPROVED_PROVISIONAL)
        self.assertEqual(active.decision_status, STATUS_ACTIVE)
        self.assertEqual(active.approved_norm, 1.325)

    def test_manual_saves(self) -> None:
        result = save_decision(
            _draft(decision=DECISION_MANUAL_PROVISIONAL, approved_norm=3.0),
            store=self.store,
        )
        self.assertTrue(result["ok"], result.get("error"))
        active = get_active_decision(
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-04",
            store=self.store,
        )
        assert active is not None
        self.assertEqual(active.decision, DECISION_MANUAL_PROVISIONAL)
        self.assertEqual(active.approved_norm, 3.0)

    def test_rejected_saves_without_norm(self) -> None:
        result = save_decision(
            _draft(decision=DECISION_REJECTED, approved_norm=None),
            store=self.store,
        )
        self.assertTrue(result["ok"], result.get("error"))
        active = get_active_decision(
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-04",
            store=self.store,
        )
        assert active is not None
        self.assertEqual(active.decision, DECISION_REJECTED)
        self.assertIsNone(active.approved_norm)

    def test_replace_preserves_history_one_active(self) -> None:
        first = save_decision(_draft(approved_norm=1.1, comment="first"), store=self.store)
        self.assertTrue(first["ok"], first.get("error"))
        first_id = first["data"]["decision_id"]
        second = save_decision(
            _draft(
                decision=DECISION_MANUAL_PROVISIONAL,
                approved_norm=2.2,
                comment="second replaces first",
            ),
            store=self.store,
        )
        self.assertTrue(second["ok"], second.get("error"))
        self.assertEqual(second["data"]["status"], "replaced")
        self.assertEqual(second["data"]["cancelled_decision_id"], first_id)

        history = list_decisions(
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-04",
            include_cancelled=True,
            store=self.store,
        )
        self.assertEqual(len(history), 2)
        statuses = {row.decision_id: row.decision_status for row in history}
        self.assertEqual(statuses[first_id], STATUS_CANCELLED)
        self.assertEqual(statuses[second["data"]["decision_id"]], STATUS_ACTIVE)
        active_rows = [row for row in history if row.decision_status == STATUS_ACTIVE]
        self.assertEqual(len(active_rows), 1)

    def test_grain_isolation(self) -> None:
        save_decision(_draft(facility_building="16160-13", approved_norm=1.1), store=self.store)
        save_decision(
            _draft(
                facility_building="16160-17",
                approved_norm=9.9,
                comment="other facility",
            ),
            store=self.store,
        )
        a = get_active_decision(
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-04",
            store=self.store,
        )
        b = get_active_decision(
            project_code="PRJ_001_БХК",
            facility_building="16160-17",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-04",
            store=self.store,
        )
        assert a is not None and b is not None
        self.assertEqual(a.approved_norm, 1.1)
        self.assertEqual(b.approved_norm, 9.9)

        save_decision(
            _draft(
                construction_discipline="Электрика",
                approved_norm=5.0,
                comment="other discipline",
                expected_unit="м2 / m2",
            ),
            store=self.store,
        )
        c = get_active_decision(
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Электрика",
            boq_code="2041-01-27-04",
            store=self.store,
        )
        assert c is not None
        self.assertEqual(c.approved_norm, 5.0)
        # original facility/discipline untouched
        a2 = get_active_decision(
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-04",
            store=self.store,
        )
        assert a2 is not None
        self.assertEqual(a2.approved_norm, 1.1)


class LaborNormDecisionSecurityTests(unittest.TestCase):
    def test_missing_secret_key_fail_closed_require_client(self) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"SUPABASE_SECRET_KEY", "SUPABASE_URL"}
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                require_service_role_client()
            self.assertIn("SUPABASE_SECRET_KEY", str(ctx.exception))
            self.assertIn("fail-closed", str(ctx.exception).lower())

    def test_missing_secret_key_apply_fail_closed(self) -> None:
        store = SupabaseLaborNormDecisionStore()
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"SUPABASE_SECRET_KEY", "SUPABASE_URL"}
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("services.labor_norm_decisions.supabase") as anon:
                result = store.apply(_draft())
                self.assertFalse(result["ok"])
                self.assertIn("SUPABASE_SECRET_KEY", result["error"] or "")
                anon.rpc.assert_not_called()
                anon.table.assert_not_called()

    def test_missing_secret_key_cancel_fail_closed(self) -> None:
        store = SupabaseLaborNormDecisionStore()
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"SUPABASE_SECRET_KEY", "SUPABASE_URL"}
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("services.labor_norm_decisions.supabase") as anon:
                result = store.cancel(
                    project_code="PRJ_001_БХК",
                    facility_building="16160-13",
                    construction_discipline="Вентиляция",
                    boq_code="2041-01-27-04",
                    cancelled_by="operator.test",
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], SERVICE_ROLE_MISSING_MSG)
                anon.rpc.assert_not_called()
                anon.table.assert_not_called()

    def test_missing_secret_key_read_fail_closed(self) -> None:
        store = SupabaseLaborNormDecisionStore()
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"SUPABASE_SECRET_KEY", "SUPABASE_URL"}
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("services.labor_norm_decisions.supabase") as anon:
                with self.assertRaises(RuntimeError) as ctx:
                    store.get_active(
                        project_code="PRJ_001_БХК",
                        facility_building="16160-13",
                        construction_discipline="Вентиляция",
                        boq_code="2041-01-27-04",
                    )
                self.assertIn("SUPABASE_SECRET_KEY", str(ctx.exception))
                anon.table.assert_not_called()

    def test_apply_uses_service_role_not_anon(self) -> None:
        store = SupabaseLaborNormDecisionStore()
        fake_client = MagicMock()
        fake_client.rpc.return_value.execute.return_value = MagicMock(
            data={"status": "inserted", "decision_id": "abc"}
        )
        with patch(
            "services.labor_norm_decisions.require_service_role_client",
            return_value=fake_client,
        ):
            with patch("services.labor_norm_decisions.supabase") as anon:
                result = store.apply(_draft())
                self.assertTrue(result["ok"], result.get("error"))
                fake_client.rpc.assert_called_once()
                self.assertEqual(fake_client.rpc.call_args[0][0], "apply_labor_norm_decision")
                anon.rpc.assert_not_called()
                anon.table.assert_not_called()

    def test_cancel_uses_service_role_not_anon(self) -> None:
        store = SupabaseLaborNormDecisionStore()
        fake_client = MagicMock()
        fake_client.rpc.return_value.execute.return_value = MagicMock(
            data={"status": "cancelled", "decision_id": "abc"}
        )
        with patch(
            "services.labor_norm_decisions.require_service_role_client",
            return_value=fake_client,
        ):
            with patch("services.labor_norm_decisions.supabase") as anon:
                result = store.cancel(
                    project_code="PRJ_001_БХК",
                    facility_building="16160-13",
                    construction_discipline="Вентиляция",
                    boq_code="2041-01-27-04",
                    cancelled_by="operator.test",
                )
                self.assertTrue(result["ok"], result.get("error"))
                fake_client.rpc.assert_called_once()
                self.assertEqual(fake_client.rpc.call_args[0][0], "cancel_labor_norm_decision")
                anon.rpc.assert_not_called()

    def test_sql_no_grants_to_anon_or_authenticated(self) -> None:
        sql = SQL_PATH.read_text(encoding="utf-8")
        # Collapse multi-line GRANT statements ending at ';'
        grant_stmts = re.findall(
            r"(?is)\bgrant\b.*?;",
            sql,
        )
        self.assertGreaterEqual(len(grant_stmts), 3)
        for stmt in grant_stmts:
            self.assertNotRegex(
                stmt,
                r"(?i)\b(anon|authenticated)\b",
                msg=f"unexpected grant to anon/authenticated: {stmt}",
            )
            self.assertRegex(stmt, r"(?i)\bto\s+service_role\b")
        self.assertRegex(
            sql,
            r"(?i)revoke\s+all\s+on\s+table\s+public\.labor_norm_decisions"
            r"[\s\S]*from\s+public,\s*anon,\s*authenticated",
        )

    def test_sql_security_definer_search_path_explicit(self) -> None:
        sql = SQL_PATH.read_text(encoding="utf-8")
        self.assertGreaterEqual(sql.lower().count("security definer"), 2)
        self.assertGreaterEqual(
            len(re.findall(r"(?im)^\s*set\s+search_path\s*=\s*public\s*$", sql)),
            2,
        )

    def test_no_validated_status_in_allowed_codes(self) -> None:
        from services.labor_norm_decisions import DECISION_CODES

        self.assertNotIn("VALIDATED", DECISION_CODES)
        err, _ = validate_decision_draft(_draft(decision="VALIDATED"))
        self.assertIsNotNone(err)


class LaborNormHintDegradationTests(unittest.TestCase):
    def test_hint_available_offers_all_decisions(self) -> None:
        from services.labor_norm_decisions import (
            decision_codes_for_hint_availability,
            decision_labels_for_hint_availability,
        )

        codes = decision_codes_for_hint_availability(True)
        self.assertEqual(
            codes,
            (
                DECISION_APPROVED_PROVISIONAL,
                DECISION_MANUAL_PROVISIONAL,
                DECISION_REJECTED,
            ),
        )
        labels = decision_labels_for_hint_availability(True)
        self.assertEqual(len(labels), 3)
        self.assertIn(DECISION_RU[DECISION_APPROVED_PROVISIONAL], labels)

    def test_hint_unavailable_blocks_approved_provisional(self) -> None:
        from services.labor_norm_decisions import (
            HINT_UNAVAILABLE_WARNING_RU,
            decision_codes_for_hint_availability,
            decision_labels_for_hint_availability,
        )

        codes = decision_codes_for_hint_availability(False)
        self.assertNotIn(DECISION_APPROVED_PROVISIONAL, codes)
        self.assertEqual(
            codes,
            (DECISION_MANUAL_PROVISIONAL, DECISION_REJECTED),
        )
        labels = decision_labels_for_hint_availability(False)
        self.assertNotIn(DECISION_RU[DECISION_APPROVED_PROVISIONAL], labels)
        self.assertIn(DECISION_RU[DECISION_MANUAL_PROVISIONAL], labels)
        self.assertIn(DECISION_RU[DECISION_REJECTED], labels)
        self.assertIn("временно недоступна", HINT_UNAVAILABLE_WARNING_RU)
        self.assertIn("принять вручную", HINT_UNAVAILABLE_WARNING_RU)

    def test_hint_failure_manual_provisional_still_validates(self) -> None:
        err, normalized = validate_decision_draft(
            _draft(
                decision=DECISION_MANUAL_PROVISIONAL,
                approved_norm=3.5,
                suggested_norm=None,
                suggested_source="",
                sample_count=None,
                confidence="",
                comment="ручная норма без исторической подсказки",
            )
        )
        self.assertIsNone(err)
        assert normalized is not None
        self.assertEqual(normalized.decision, DECISION_MANUAL_PROVISIONAL)
        self.assertEqual(normalized.approved_norm, 3.5)

    def test_hint_failure_rejected_still_validates(self) -> None:
        err, normalized = validate_decision_draft(
            _draft(
                decision=DECISION_REJECTED,
                approved_norm=None,
                suggested_norm=None,
                comment="отклонение без исторической подсказки",
            )
        )
        self.assertIsNone(err)
        assert normalized is not None
        self.assertEqual(normalized.decision, DECISION_REJECTED)

    def test_hint_ssl_failure_page_mode_remains_usable(self) -> None:
        """Simulate load_boq_norm_hints SSL failure → manual path still open."""
        from services.labor_norm_decisions import (
            decision_codes_for_hint_availability,
            load_boq_norm_hints,
        )

        with patch(
            "services.labor_norm_decisions.get_write_client",
            return_value=None,
        ), patch("services.labor_norm_decisions.supabase") as anon, patch(
            "services.labor_norm_decisions.time.sleep"
        ):
            anon.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = (
                OSError(
                    "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
                )
            )
            rows, err = load_boq_norm_hints(project_code="PRJ_001_БХК")
        self.assertEqual(rows, [])
        self.assertIsNotNone(err)
        self.assertIn("SSL", err or "")
        hints_available = not bool(err)
        self.assertFalse(hints_available)
        codes = decision_codes_for_hint_availability(hints_available)
        self.assertIn(DECISION_MANUAL_PROVISIONAL, codes)
        self.assertIn(DECISION_REJECTED, codes)
        self.assertNotIn(DECISION_APPROVED_PROVISIONAL, codes)

    def test_durable_service_unchanged_on_manual_save(self) -> None:
        store = MemoryLaborNormDecisionStore()
        result = save_decision(
            _draft(
                decision=DECISION_MANUAL_PROVISIONAL,
                approved_norm=4.2,
                suggested_norm=None,
                comment="manual without hint",
            ),
            store=store,
        )
        self.assertTrue(result["ok"], result.get("error"))
        active = get_active_decision(
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-04",
            store=store,
        )
        assert active is not None
        self.assertEqual(active.decision, DECISION_MANUAL_PROVISIONAL)
        self.assertEqual(active.approved_norm, 4.2)
        self.assertEqual(active.decision_status, STATUS_ACTIVE)


class Page13PerformanceHotfixTests(unittest.TestCase):
    def test_initial_render_plan_fetches_nothing(self) -> None:
        from services.labor_norm_decisions import page13_remote_plan

        plan = page13_remote_plan(
            load_hints_clicked=False,
            load_history_clicked=False,
            load_active_clicked=False,
        )
        self.assertFalse(plan["fetch_hints"])
        self.assertFalse(plan["fetch_history"])
        self.assertFalse(plan["fetch_active"])

    def test_hint_fetch_only_when_explicit(self) -> None:
        from services.labor_norm_decisions import page13_remote_plan

        plan = page13_remote_plan(
            load_hints_clicked=True,
            load_history_clicked=False,
            load_active_clicked=False,
        )
        self.assertTrue(plan["fetch_hints"])
        self.assertFalse(plan["fetch_history"])

    def test_history_fetch_only_when_explicit(self) -> None:
        from services.labor_norm_decisions import page13_remote_plan

        plan = page13_remote_plan(
            load_hints_clicked=False,
            load_history_clicked=True,
            load_active_clicked=False,
        )
        self.assertFalse(plan["fetch_hints"])
        self.assertTrue(plan["fetch_history"])

    def test_initial_page_source_has_no_auto_hint_or_history_call(self) -> None:
        page = Path(__file__).resolve().parents[1] / "pages"
        matches = list(page.glob("*трудовой_норме.py"))
        self.assertTrue(matches, "Page13 file missing")
        source = matches[0].read_text(encoding="utf-8")
        # Auto path must be gated by page13_remote_plan / button flags.
        self.assertIn("page13_remote_plan", source)
        self.assertIn("Загрузить историческую подсказку", source)
        self.assertIn("Показать историю решений", source)
        self.assertIn("HINT_NOT_LOADED_RU", source)
        # Must not call load_boq_norm_hints / list_decisions before plan check.
        hint_call = source.find("load_boq_norm_hints(")
        plan_hint = source.find('plan["fetch_hints"]')
        self.assertGreater(hint_call, 0)
        self.assertGreater(plan_hint, 0)
        self.assertLess(plan_hint, hint_call)
        hist_call = source.find("list_decisions(")
        hist_plan = source.find('history_plan["fetch_history"]')
        self.assertGreater(hist_call, 0)
        self.assertGreater(hist_plan, 0)
        self.assertLess(hist_plan, hist_call)

    def test_hint_not_loaded_blocks_approved_keeps_manual_rejected(self) -> None:
        from services.labor_norm_decisions import (
            HINT_NOT_LOADED_RU,
            decision_codes_for_hint_availability,
        )

        codes = decision_codes_for_hint_availability(False)
        self.assertEqual(codes, (DECISION_MANUAL_PROVISIONAL, DECISION_REJECTED))
        self.assertIn("не загружена", HINT_NOT_LOADED_RU.lower())

    def test_history_failure_does_not_block_save_validation(self) -> None:
        # History is optional; save validation independent.
        err, normalized = validate_decision_draft(
            _draft(decision=DECISION_REJECTED, approved_norm=None)
        )
        self.assertIsNone(err)
        assert normalized is not None
        self.assertEqual(normalized.decision, DECISION_REJECTED)

    def test_rejected_save_path_unchanged(self) -> None:
        store = MemoryLaborNormDecisionStore()
        result = save_decision(
            _draft(decision=DECISION_REJECTED, approved_norm=None, comment="reject ok"),
            store=store,
        )
        self.assertTrue(result["ok"], result.get("error"))

    def test_service_role_security_still_required_for_supabase_store(self) -> None:
        store = SupabaseLaborNormDecisionStore()
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"SUPABASE_SECRET_KEY", "SUPABASE_URL"}
        }
        with patch.dict(os.environ, env, clear=True):
            result = store.apply(_draft(decision=DECISION_MANUAL_PROVISIONAL, approved_norm=1.1))
        self.assertFalse(result["ok"])
        self.assertIn("SUPABASE_SECRET_KEY", result["error"] or "")


if __name__ == "__main__":
    unittest.main()
