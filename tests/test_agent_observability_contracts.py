"""
Increment 10.1A — agent-neutral observability contract tests.

No Streamlit, LangGraph, Supabase, SQL, Docker, LLM, or product writes.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import subprocess
import sys
import unittest
from dataclasses import is_dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agents.observability.contracts import (
    AGENT_RUN_SCHEMA_VERSION,
    CONSTRUCTOR_STAGE_CATALOG,
    EVENT_FAMILY_BY_TYPE,
    EVENT_TYPES,
    MAX_DETAIL_KEYS,
    MAX_LIST_LENGTH,
    MAX_NESTING_DEPTH,
    MAX_SERIALIZED_BYTES,
    MAX_STRING_LENGTH,
    OBSERVABILITY_EVENT_SCHEMA_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    RUN_REQUEST_SCHEMA_VERSION,
    AgentRun,
    EventFamily,
    EventStatus,
    EventType,
    InitiatorType,
    ObservabilityContractError,
    ObservabilityEvent,
    OperationalStatus,
    RunRequest,
    StageDefinition,
    StageDisplayState,
    TriggerType,
    build_agent_run,
    build_observability_event,
    build_run_request,
    compute_run_request_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_PATH = REPO_ROOT / "agents" / "observability" / "contracts.py"
PACKAGE_INIT_PATH = REPO_ROOT / "agents" / "observability" / "__init__.py"
FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 8, 31, 13, 0, 0, tzinfo=timezone.utc)
OFFSET_AT = datetime(2026, 8, 31, 15, 0, 0, tzinfo=timezone(timedelta(hours=3)))
NAIVE_AT = datetime(2026, 8, 31, 12, 0, 0)

_FORBIDDEN_IMPORTS = frozenset(
    {
        "streamlit",
        "langgraph",
        "supabase",
        "pandas",
        "agents.monthly_plan_constructor",
    }
)


def _human_request_kwargs(**overrides: Any) -> dict[str, Any]:
    payload = {
        "request_id": "req-human-001",
        "requested_at": FIXED_AT,
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "initiator_type": InitiatorType.HUMAN,
        "initiator_id": "operator-local",
        "trigger_type": TriggerType.MANUAL,
        "trigger_reason": "manual-start",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "requested_mission_id": "mission-001",
        "idempotency_key": "idem-human-001",
        "scope_request": {"facility": "A"},
        "metadata": {"ui": "control-room"},
    }
    payload.update(overrides)
    return payload


def _orch_request_kwargs(**overrides: Any) -> dict[str, Any]:
    payload = _human_request_kwargs(
        request_id="req-orch-001",
        initiator_type=InitiatorType.ORCHESTRATOR,
        initiator_id="monthly-plan-orchestrator",
        trigger_type=TriggerType.ORCHESTRATION,
        trigger_reason="orchestration-start",
        idempotency_key="idem-orch-001",
        orchestration_run_id="orch-run-001",
    )
    payload.update(overrides)
    return payload


def _agent_run_kwargs(**overrides: Any) -> dict[str, Any]:
    payload = {
        "run_id": "run-001",
        "request_id": "req-human-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "agent_version": "0.1",
        "mission_id": "mission-001",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "initiator_type": InitiatorType.HUMAN,
        "initiator_id": "operator-local",
        "trigger_type": TriggerType.MANUAL,
        "trigger_reason": "manual-start",
        "operational_status": OperationalStatus.RUNNING,
        "requested_at": FIXED_AT,
        "updated_at": FIXED_AT,
        "thread_id": "run-001",
        "scope_summary": {"facility": "A"},
        "safe_summary": {"phase": "running"},
        "safe_counts": {"candidates": 12},
    }
    payload.update(overrides)
    return payload


def _event_kwargs(**overrides: Any) -> dict[str, Any]:
    payload = {
        "event_id": "evt-001",
        "run_id": "run-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "occurred_at": FIXED_AT,
        "event_type": EventType.RUN_STARTED,
        "status": EventStatus.OK,
        "title": "Run started",
        "detail": {"node": "start"},
    }
    payload.update(overrides)
    return payload


class ObservabilityContractTests(unittest.TestCase):
    def test_01_run_request_valid_human(self) -> None:
        req = build_run_request(**_human_request_kwargs())
        self.assertTrue(is_dataclass(req))
        self.assertEqual(req.schema_version, RUN_REQUEST_SCHEMA_VERSION)
        self.assertEqual(req.initiator_type, InitiatorType.HUMAN)
        self.assertIsNone(req.orchestration_run_id)
        self.assertEqual(len(req.canonical_request_digest), 64)

    def test_02_run_request_valid_orchestrator(self) -> None:
        req = build_run_request(**_orch_request_kwargs())
        self.assertEqual(req.initiator_type, InitiatorType.ORCHESTRATOR)
        self.assertEqual(req.orchestration_run_id, "orch-run-001")

    def test_03_orchestrator_without_orchestration_run_id_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError) as ctx:
            build_run_request(**_orch_request_kwargs(orchestration_run_id=None))
        self.assertEqual(ctx.exception.code, "OBSERVABILITY_CONTRACT_BLOCKER")

    def test_04_whitespace_required_identity_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_run_request(**_human_request_kwargs(request_id="   "))
        with self.assertRaises(ObservabilityContractError):
            build_run_request(**_human_request_kwargs(project_code="\t"))

    def test_05_timezone_naive_requested_at_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_run_request(**_human_request_kwargs(requested_at=NAIVE_AT))

    def test_06_canonical_digest_deterministic(self) -> None:
        a = compute_run_request_digest(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            initiator_type=InitiatorType.HUMAN,
            initiator_id="operator-local",
            project_code="PRJ_001",
            month_key="2026-09",
            scope_request={"facility": "A", "discipline": "vent"},
            requested_mission_id="mission-001",
            orchestration_run_id=None,
            predecessor_run_id=None,
            trigger_type=TriggerType.MANUAL,
        )
        b = compute_run_request_digest(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            initiator_type="HUMAN",
            initiator_id="operator-local",
            project_code="PRJ_001",
            month_key="2026-09",
            scope_request={"discipline": "vent", "facility": "A"},
            requested_mission_id="mission-001",
            orchestration_run_id=None,
            predecessor_run_id=None,
            trigger_type="MANUAL",
        )
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_07_requested_at_does_not_affect_digest(self) -> None:
        first = build_run_request(**_human_request_kwargs(requested_at=FIXED_AT))
        second = build_run_request(**_human_request_kwargs(requested_at=LATER_AT))
        self.assertEqual(first.canonical_request_digest, second.canonical_request_digest)

    def test_08_metadata_does_not_affect_digest(self) -> None:
        first = build_run_request(**_human_request_kwargs(metadata={"ui": "a"}))
        second = build_run_request(**_human_request_kwargs(metadata={"ui": "b"}))
        self.assertEqual(first.canonical_request_digest, second.canonical_request_digest)

    def test_09_scope_change_changes_digest(self) -> None:
        first = build_run_request(**_human_request_kwargs(scope_request={"facility": "A"}))
        second = build_run_request(**_human_request_kwargs(scope_request={"facility": "B"}))
        self.assertNotEqual(first.canonical_request_digest, second.canonical_request_digest)

    def test_10_mission_change_changes_digest(self) -> None:
        first = build_run_request(**_human_request_kwargs(requested_mission_id="mission-001"))
        second = build_run_request(**_human_request_kwargs(requested_mission_id="mission-002"))
        self.assertNotEqual(first.canonical_request_digest, second.canonical_request_digest)

    def test_11_agent_run_thread_id_mismatch_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_agent_run(**_agent_run_kwargs(thread_id="other-thread"))

    def test_12_attempt_n_below_one_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_agent_run(**_agent_run_kwargs(attempt_n=0))

    def test_13_resume_n_negative_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_agent_run(**_agent_run_kwargs(resume_n=-1))

    def test_14_projection_version_negative_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_agent_run(**_agent_run_kwargs(projection_version=-1))

    def test_15_terminal_status_completion_timestamp_semantics(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_agent_run(
                **_agent_run_kwargs(operational_status=OperationalStatus.COMPLETED)
            )
        done = build_agent_run(
            **_agent_run_kwargs(
                operational_status=OperationalStatus.COMPLETED,
                completed_at=LATER_AT,
            )
        )
        self.assertEqual(done.completed_at, LATER_AT)
        with self.assertRaises(ObservabilityContractError):
            build_agent_run(
                **_agent_run_kwargs(
                    operational_status=OperationalStatus.RUNNING,
                    completed_at=LATER_AT,
                )
            )

    def test_16_observability_event_timezone_requirement(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(occurred_at=NAIVE_AT))
        event = build_observability_event(**_event_kwargs())
        self.assertEqual(event.occurred_at.tzinfo, timezone.utc)

    def test_17_artifact_type_without_artifact_id_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(
                    event_type=EventType.ARTIFACT_CREATED,
                    artifact_type="CANDIDATE_PACKAGE",
                )
            )

    def test_18_artifact_id_without_artifact_type_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(
                    event_type=EventType.ARTIFACT_CREATED,
                    artifact_id="pkg-001",
                )
            )

    def test_19_detail_accepts_bounded_safe_json(self) -> None:
        event = build_observability_event(
            **_event_kwargs(detail={"count": 3, "ok": True, "tags": ["a", "b"]})
        )
        self.assertEqual(event.detail[0], "__obs_dict__")
        payload = event.to_dict()
        self.assertEqual(payload["detail"]["count"], 3)

    def test_20_detail_rejects_excessive_keys(self) -> None:
        too_many = {f"k{i}": i for i in range(MAX_DETAIL_KEYS + 1)}
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(detail=too_many))

    def test_21_excessive_nesting_rejected(self) -> None:
        nested: Any = {"leaf": 1}
        for _ in range(MAX_NESTING_DEPTH + 2):
            nested = {"child": nested}
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(detail=nested))

    def test_22_excessive_string_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(detail={"note": "x" * (MAX_STRING_LENGTH + 1)})
            )

    def test_23_excessive_serialized_size_rejected(self) -> None:
        bulky = {f"k{i:02d}": "v" * 400 for i in range(MAX_DETAIL_KEYS)}
        encoded = json.dumps(bulky, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertGreater(len(encoded.encode("utf-8")), MAX_SERIALIZED_BYTES)
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(detail=bulky))

    def test_24_excessive_list_length_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(detail={"items": list(range(MAX_LIST_LENGTH + 1))})
            )

    def test_25_unsupported_object_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(detail={"obj": object()}))
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(detail={"raw": b"abc"}))
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(detail={"s": {1, 2}}))

    def test_26_nan_infinity_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(detail={"n": math.nan}))
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(detail={"n": math.inf}))

    def test_27_safe_serialization_deterministic(self) -> None:
        event = build_observability_event(
            **_event_kwargs(detail={"b": 2, "a": 1})
        )
        first = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        second = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(first, second)
        self.assertEqual(event.to_dict()["event_type"], "RUN_STARTED")
        self.assertTrue(event.to_dict()["occurred_at"].endswith("+00:00"))

    def test_28_event_enum_taxonomy_exact(self) -> None:
        expected = [
            "RUN_REQUESTED",
            "RUN_AUTHORIZATION_STARTED",
            "RUN_AUTHORIZED",
            "RUN_DENIED",
            "RUN_STARTED",
            "RUN_ADVANCING",
            "RUN_COMPLETED",
            "RUN_FAILED",
            "RUN_ABORTED",
            "MISSION_BOUND",
            "STAGE_STARTED",
            "STAGE_COMPLETED",
            "STAGE_FAILED",
            "TOOL_CALL_STARTED",
            "TOOL_CALL_COMPLETED",
            "TOOL_CALL_DENIED",
            "ARTIFACT_CREATED",
            "EXCEPTION_RAISED",
            "HUMAN_WAIT_STARTED",
            "HUMAN_DECISION_RECEIVED",
            "RUN_RESUMED",
            "REALITY_REFRESH_STARTED",
            "REALITY_REFRESH_COMPLETED",
            "RETRY_REQUESTED",
            "RETRY_STARTED",
            "REPLAY_DETECTED",
            "HANDOFF_CREATED",
            "HANDOFF_PERSISTED",
            "HANDOFF_PERSIST_FAILED",
            "SECURITY_EVENT",
        ]
        self.assertEqual([item.value for item in EVENT_TYPES], expected)
        self.assertNotIn("NODE_STARTED", {item.value for item in EventType})
        self.assertEqual(EVENT_FAMILY_BY_TYPE[EventType.MISSION_BOUND], EventFamily.MISSION)
        self.assertEqual(len(EVENT_FAMILY_BY_TYPE), len(EventType))
        names = {item.name for item in InitiatorType}
        self.assertEqual(names, {"HUMAN", "ORCHESTRATOR"})
        self.assertNotIn("RESUME", names)
        self.assertNotIn("RETRY", names)
        self.assertNotIn("SYSTEM_EVENT", names)
        self.assertIn("SYSTEM_EVENT", {item.name for item in TriggerType})

    def test_29_constructor_stage_catalog_ordered_1_to_11(self) -> None:
        self.assertEqual(len(CONSTRUCTOR_STAGE_CATALOG), 11)
        self.assertEqual([item.sequence for item in CONSTRUCTOR_STAGE_CATALOG], list(range(1, 12)))
        self.assertEqual(
            [item.stage_id for item in CONSTRUCTOR_STAGE_CATALOG],
            [
                "AUTHORIZATION",
                "MISSION_BINDING",
                "REALITY_READ",
                "CANDIDATE_ASSEMBLY",
                "LABOR_NORM_RESOLUTION",
                "EXCEPTION_ANALYSIS",
                "HUMAN_GATE",
                "REALITY_REVALIDATION",
                "HANDOFF_PREPARATION",
                "HANDOFF_PERSISTENCE",
                "RUN_COMPLETION",
            ],
        )

    def test_30_stage_definition_is_agent_neutral(self) -> None:
        stage = StageDefinition(
            schema_version="stage_definition.v0.1",
            stage_id="ADMISSION_CHECK",
            sequence=1,
            code="ADMISSION_CHECK",
            display_name="Admission check",
        )
        self.assertIsInstance(stage, StageDefinition)
        self.assertNotIn("color", stage.to_dict())
        source = CONTRACTS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("<div", source)
        self.assertNotIn("background:", source)

    def test_31_schema_version_preserved(self) -> None:
        req = build_run_request(**_human_request_kwargs())
        run = build_agent_run(**_agent_run_kwargs())
        event = build_observability_event(**_event_kwargs())
        self.assertEqual(req.schema_version, RUN_REQUEST_SCHEMA_VERSION)
        self.assertEqual(run.schema_version, AGENT_RUN_SCHEMA_VERSION)
        self.assertEqual(event.schema_version, OBSERVABILITY_EVENT_SCHEMA_VERSION)
        self.assertEqual(OBSERVABILITY_SCHEMA_VERSION, "0.1")
        with self.assertRaises(ObservabilityContractError):
            build_run_request(**_human_request_kwargs(schema_version="9.9"))

    def test_32_no_secret_bearing_detail_accepted(self) -> None:
        forbidden_keys = (
            "api_key",
            "apikey",
            "access_token",
            "refresh_token",
            "authorization",
            "bearer_token",
            "service_role",
            "service_role_key",
            "password",
            "passwd",
            "secret",
            "client_secret",
            "database_url",
            "dsn",
            "supabase_key",
            "supabase_secret_key",
            "API-Key",
        )
        for key in forbidden_keys:
            with self.subTest(key=key):
                with self.assertRaises(ObservabilityContractError):
                    build_observability_event(
                        **_event_kwargs(detail={key: "placeholder"})
                    )

    def test_33_no_dataframe_dependency_in_public_contracts(self) -> None:
        source = CONTRACTS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import pandas", source)
        self.assertNotIn("from pandas", source)

    def test_34_importing_contracts_does_not_import_streamlit(self) -> None:
        self._assert_isolated_import_excludes("streamlit")

    def test_35_importing_contracts_does_not_import_langgraph(self) -> None:
        self._assert_isolated_import_excludes("langgraph")

    def test_36_importing_contracts_does_not_import_supabase(self) -> None:
        self._assert_isolated_import_excludes("supabase")

    def test_frozen_contracts_are_immutable(self) -> None:
        req = build_run_request(**_human_request_kwargs())
        event = build_observability_event(**_event_kwargs())
        with self.assertRaises(Exception):
            req.request_id = "mutated"  # type: ignore[misc]
        with self.assertRaises(Exception):
            event.title = "mutated"  # type: ignore[misc]

    def test_unknown_event_type_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**_event_kwargs(event_type="NODE_STARTED"))

    def test_family_mismatch_fails(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(family=EventFamily.HANDOFF, event_type=EventType.RUN_STARTED)
            )

    def test_artifact_pair_accepted(self) -> None:
        event = build_observability_event(
            **_event_kwargs(
                event_type=EventType.ARTIFACT_CREATED,
                artifact_type="CANDIDATE_PACKAGE",
                artifact_id="pkg-001",
            )
        )
        self.assertEqual(event.artifact_type, "CANDIDATE_PACKAGE")
        self.assertEqual(event.artifact_id, "pkg-001")

    def test_digest_excludes_idempotency_key(self) -> None:
        first = build_run_request(**_human_request_kwargs(idempotency_key="idem-a"))
        second = build_run_request(**_human_request_kwargs(idempotency_key="idem-b"))
        self.assertEqual(first.canonical_request_digest, second.canonical_request_digest)

    def test_digest_is_sha256_of_canonical_json(self) -> None:
        digest = compute_run_request_digest(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            initiator_type=InitiatorType.HUMAN,
            initiator_id="operator-local",
            project_code="PRJ_001",
            month_key="2026-09",
            scope_request={"facility": "A"},
            requested_mission_id="mission-001",
            orchestration_run_id=None,
            predecessor_run_id=None,
            trigger_type=TriggerType.MANUAL,
        )
        payload = {
            "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
            "initiator_id": "operator-local",
            "initiator_type": "HUMAN",
            "month_key": "2026-09",
            "orchestration_run_id": None,
            "predecessor_run_id": None,
            "project_code": "PRJ_001",
            "requested_mission_id": "mission-001",
            "scope_request": {"facility": "A"},
            "trigger_type": "MANUAL",
        }
        expected = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(digest, expected)

    def test_observability_package_source_has_no_forbidden_imports(self) -> None:
        for path in (CONTRACTS_PATH, PACKAGE_INIT_PATH):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], _FORBIDDEN_IMPORTS)
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    self.assertNotIn(root, _FORBIDDEN_IMPORTS)
                    self.assertFalse(node.module.startswith("agents.monthly_plan_constructor"))

    def test_stage_display_state_closed(self) -> None:
        self.assertEqual(
            [item.value for item in StageDisplayState],
            ["NOT_STARTED", "RUNNING", "WAITING", "BLOCKED", "FAILED", "COMPLETED"],
        )

    def test_replace_preserves_invariants(self) -> None:
        run = build_agent_run(**_agent_run_kwargs())
        with self.assertRaises(ObservabilityContractError):
            replace(run, thread_id="mismatch")

    def test_scope_request_isolated_from_caller_mutation(self) -> None:
        source = {
            "facility": "A",
            "tags": ["alpha", "beta"],
            "window": {"month": "2026-09"},
        }
        req = build_run_request(**_human_request_kwargs(scope_request=source))
        source["facility"] = "Z"
        source["tags"].append("mutated")
        source["window"]["month"] = "2099-01"
        stored = req.to_dict()["scope_request"]
        self.assertEqual(stored["facility"], "A")
        self.assertEqual(stored["tags"], ["alpha", "beta"])
        self.assertEqual(stored["window"]["month"], "2026-09")

    def test_scope_request_isolated_from_to_dict_mutation(self) -> None:
        req = build_run_request(
            **_human_request_kwargs(
                scope_request={
                    "facility": "A",
                    "tags": ["alpha", "beta"],
                    "window": {"month": "2026-09"},
                }
            )
        )
        serialized = req.to_dict()
        serialized["scope_request"]["facility"] = "Z"
        serialized["scope_request"]["tags"].append("from-dict")
        serialized["scope_request"]["window"]["month"] = "changed"
        stored = req.to_dict()["scope_request"]
        self.assertEqual(stored["facility"], "A")
        self.assertEqual(stored["tags"], ["alpha", "beta"])
        self.assertEqual(stored["window"]["month"], "2026-09")

    def test_event_detail_isolated_from_caller_mutation(self) -> None:
        source = {
            "count": 3,
            "tags": ["a", "b"],
            "window": {"stage": "start"},
        }
        event = build_observability_event(**_event_kwargs(detail=source))
        source["count"] = 99
        source["tags"].append("mutated")
        source["window"]["stage"] = "changed"
        stored = event.to_dict()["detail"]
        self.assertEqual(stored["count"], 3)
        self.assertEqual(stored["tags"], ["a", "b"])
        self.assertEqual(stored["window"]["stage"], "start")

    def test_event_detail_isolated_from_to_dict_mutation(self) -> None:
        event = build_observability_event(
            **_event_kwargs(
                detail={
                    "count": 3,
                    "tags": ["a", "b"],
                    "window": {"stage": "start"},
                }
            )
        )
        serialized = event.to_dict()
        serialized["detail"]["count"] = 99
        serialized["detail"]["tags"].append("from-dict")
        serialized["detail"]["window"]["stage"] = "changed"
        stored = event.to_dict()["detail"]
        self.assertEqual(stored["count"], 3)
        self.assertEqual(stored["tags"], ["a", "b"])
        self.assertEqual(stored["window"]["stage"], "start")

    def test_event_family_mapping_complete(self) -> None:
        expected = {
            EventType.RUN_REQUESTED: EventFamily.RUN_CONTROL,
            EventType.RUN_AUTHORIZATION_STARTED: EventFamily.RUN_CONTROL,
            EventType.RUN_AUTHORIZED: EventFamily.RUN_CONTROL,
            EventType.RUN_DENIED: EventFamily.RUN_CONTROL,
            EventType.RUN_STARTED: EventFamily.RUN_CONTROL,
            EventType.RUN_ADVANCING: EventFamily.RUN_CONTROL,
            EventType.RUN_COMPLETED: EventFamily.RUN_CONTROL,
            EventType.RUN_FAILED: EventFamily.RUN_CONTROL,
            EventType.RUN_ABORTED: EventFamily.RUN_CONTROL,
            EventType.MISSION_BOUND: EventFamily.MISSION,
            EventType.STAGE_STARTED: EventFamily.STAGE,
            EventType.STAGE_COMPLETED: EventFamily.STAGE,
            EventType.STAGE_FAILED: EventFamily.STAGE,
            EventType.TOOL_CALL_STARTED: EventFamily.TOOL,
            EventType.TOOL_CALL_COMPLETED: EventFamily.TOOL,
            EventType.TOOL_CALL_DENIED: EventFamily.TOOL,
            EventType.ARTIFACT_CREATED: EventFamily.ARTIFACT,
            EventType.EXCEPTION_RAISED: EventFamily.EXCEPTION,
            EventType.HUMAN_WAIT_STARTED: EventFamily.HITL,
            EventType.HUMAN_DECISION_RECEIVED: EventFamily.HITL,
            EventType.RUN_RESUMED: EventFamily.HITL,
            EventType.REALITY_REFRESH_STARTED: EventFamily.REALITY,
            EventType.REALITY_REFRESH_COMPLETED: EventFamily.REALITY,
            EventType.RETRY_REQUESTED: EventFamily.RETRY,
            EventType.RETRY_STARTED: EventFamily.RETRY,
            EventType.REPLAY_DETECTED: EventFamily.RETRY,
            EventType.HANDOFF_CREATED: EventFamily.HANDOFF,
            EventType.HANDOFF_PERSISTED: EventFamily.HANDOFF,
            EventType.HANDOFF_PERSIST_FAILED: EventFamily.HANDOFF,
            EventType.SECURITY_EVENT: EventFamily.SECURITY,
        }
        self.assertEqual(dict(EVENT_FAMILY_BY_TYPE), expected)
        self.assertEqual(set(EVENT_FAMILY_BY_TYPE), set(EventType))
        self.assertEqual(len(EVENT_FAMILY_BY_TYPE), len(EventType))

    def test_ordinary_business_keys_and_urls_are_accepted(self) -> None:
        detail = {
            "token_count": 4,
            "secretary": "ops",
            "madison": "unit-1",
            "authorization_status": "PASS",
            "api_key_count": 0,
            "url": "https://example.invalid/docs",
            "source_url": "https://example.invalid/evidence/123",
            "evidence_url": "https://example.invalid/evidence/123",
        }
        event = build_observability_event(**_event_kwargs(detail=detail))
        stored = event.to_dict()["detail"]
        self.assertEqual(stored["token_count"], 4)
        self.assertEqual(stored["secretary"], "ops")
        self.assertEqual(stored["madison"], "unit-1")
        self.assertEqual(stored["authorization_status"], "PASS")
        self.assertEqual(stored["source_url"], "https://example.invalid/evidence/123")

    def test_direct_constructors_store_canonical_utc(self) -> None:
        self.assertEqual(OFFSET_AT.utcoffset(), timedelta(hours=3))
        base_req = build_run_request(**_human_request_kwargs())
        direct_req = RunRequest(
            schema_version=base_req.schema_version,
            request_id=base_req.request_id,
            requested_at=OFFSET_AT,
            agent_code=base_req.agent_code,
            requested_agent_version=base_req.requested_agent_version,
            initiator_type=base_req.initiator_type,
            initiator_id=base_req.initiator_id,
            trigger_type=base_req.trigger_type,
            trigger_reason=base_req.trigger_reason,
            project_code=base_req.project_code,
            month_key=base_req.month_key,
            scope_request=base_req.scope_request,
            orchestration_run_id=base_req.orchestration_run_id,
            predecessor_run_id=base_req.predecessor_run_id,
            requested_mission_id=base_req.requested_mission_id,
            idempotency_key=base_req.idempotency_key,
            metadata=base_req.metadata,
            canonical_request_digest=base_req.canonical_request_digest,
        )
        self.assertEqual(direct_req.requested_at.utcoffset(), timedelta(0))
        self.assertEqual(direct_req.requested_at, FIXED_AT)
        self.assertTrue(direct_req.to_dict()["requested_at"].endswith("+00:00"))

        built_req = build_run_request(**_human_request_kwargs(requested_at=OFFSET_AT))
        self.assertEqual(built_req.requested_at, FIXED_AT)

        base_run = build_agent_run(
            **_agent_run_kwargs(
                operational_status=OperationalStatus.COMPLETED,
                started_at=FIXED_AT,
                completed_at=LATER_AT,
            )
        )
        direct_run = replace(
            base_run,
            requested_at=OFFSET_AT,
            started_at=OFFSET_AT,
            updated_at=OFFSET_AT,
            completed_at=datetime(2026, 8, 31, 16, 0, 0, tzinfo=timezone(timedelta(hours=3))),
        )
        self.assertEqual(direct_run.requested_at.utcoffset(), timedelta(0))
        self.assertEqual(direct_run.started_at.utcoffset(), timedelta(0))
        self.assertEqual(direct_run.updated_at.utcoffset(), timedelta(0))
        self.assertEqual(direct_run.completed_at.utcoffset(), timedelta(0))
        self.assertEqual(direct_run.requested_at, FIXED_AT)
        self.assertEqual(direct_run.started_at, FIXED_AT)
        self.assertEqual(direct_run.updated_at, FIXED_AT)
        self.assertEqual(
            direct_run.completed_at,
            datetime(2026, 8, 31, 13, 0, 0, tzinfo=timezone.utc),
        )
        payload = direct_run.to_dict()
        self.assertTrue(payload["requested_at"].endswith("+00:00"))
        self.assertTrue(payload["started_at"].endswith("+00:00"))
        self.assertTrue(payload["updated_at"].endswith("+00:00"))
        self.assertTrue(payload["completed_at"].endswith("+00:00"))

        base_event = build_observability_event(**_event_kwargs())
        direct_event = ObservabilityEvent(
            schema_version=base_event.schema_version,
            event_id=base_event.event_id,
            run_id=base_event.run_id,
            agent_code=base_event.agent_code,
            occurred_at=OFFSET_AT,
            family=base_event.family,
            event_type=base_event.event_type,
            status=base_event.status,
            title=base_event.title,
            stage_id=base_event.stage_id,
            span_id=base_event.span_id,
            request_id=base_event.request_id,
            mission_id=base_event.mission_id,
            orchestration_run_id=base_event.orchestration_run_id,
            authorization_id=base_event.authorization_id,
            checkpoint_id=base_event.checkpoint_id,
            interrupt_id=base_event.interrupt_id,
            decision_id=base_event.decision_id,
            artifact_type=base_event.artifact_type,
            artifact_id=base_event.artifact_id,
            handoff_id=base_event.handoff_id,
            tool_name=base_event.tool_name,
            node_name=base_event.node_name,
            attempt_n=base_event.attempt_n,
            resume_n=base_event.resume_n,
            human_decision_request=base_event.human_decision_request,
            human_decision_record=base_event.human_decision_record,
            detail=base_event.detail,
        )
        self.assertEqual(direct_event.occurred_at.utcoffset(), timedelta(0))
        self.assertEqual(direct_event.occurred_at, FIXED_AT)
        self.assertTrue(direct_event.to_dict()["occurred_at"].endswith("+00:00"))

    def test_authorization_denied_allows_missing_started_at(self) -> None:
        run = build_agent_run(
            **_agent_run_kwargs(
                operational_status=OperationalStatus.AUTHORIZATION_DENIED,
                started_at=None,
                completed_at=LATER_AT,
            )
        )
        self.assertIsNone(run.started_at)
        self.assertEqual(run.completed_at, LATER_AT)
        with self.assertRaises(ObservabilityContractError):
            build_agent_run(
                **_agent_run_kwargs(
                    operational_status=OperationalStatus.AUTHORIZATION_DENIED,
                    started_at=None,
                    completed_at=None,
                )
            )

    def _assert_isolated_import_excludes(self, module_name: str) -> None:
        script = (
            "import sys\n"
            "from agents.observability import contracts\n"
            f"raise SystemExit(0 if {module_name!r} not in sys.modules else 2)\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


class HumanDecisionObservabilitySubcontractTests(unittest.TestCase):
    def test_request_subcontract_valid(self) -> None:
        from agents.observability.contracts import (
            HUMAN_DECISION_REQUEST_OBSERVABILITY_SCHEMA_VERSION,
            build_human_decision_request_observability_context,
        )

        ctx = build_human_decision_request_observability_context(
            reason_code="ambiguous_scope",
            allowed_decisions=("CLARIFY_SCOPE", "ABORT_RUN"),
            human_readable_reason="Scope ambiguous",
            evidence_refs=("ref-1",),
        )
        self.assertEqual(ctx.schema_version, HUMAN_DECISION_REQUEST_OBSERVABILITY_SCHEMA_VERSION)
        self.assertEqual(ctx.reason_code, "AMBIGUOUS_SCOPE")

    def test_record_subcontract_valid(self) -> None:
        from agents.observability.contracts import (
            HUMAN_DECISION_RECORD_OBSERVABILITY_SCHEMA_VERSION,
            build_human_decision_record_observability_context,
        )

        ctx = build_human_decision_record_observability_context(
            decision_code="CLARIFY_SCOPE",
            actor_id="operator-1",
            actor_type="HUMAN",
        )
        self.assertEqual(ctx.schema_version, HUMAN_DECISION_RECORD_OBSERVABILITY_SCHEMA_VERSION)

    def test_human_wait_started_requires_request(self) -> None:
        from agents.observability.contracts import build_human_decision_request_observability_context

        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(
                    event_type=EventType.HUMAN_WAIT_STARTED,
                    family=EventFamily.HITL,
                    interrupt_id="intr-001",
                )
            )
        event = build_observability_event(
            **_event_kwargs(
                event_type=EventType.HUMAN_WAIT_STARTED,
                family=EventFamily.HITL,
                interrupt_id="intr-001",
                human_decision_request=build_human_decision_request_observability_context(
                    reason_code="WAIT",
                    allowed_decisions=("CONTINUE",),
                ),
            )
        )
        self.assertIsNotNone(event.human_decision_request)

    def test_human_decision_received_requires_record(self) -> None:
        from agents.observability.contracts import build_human_decision_record_observability_context

        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(
                    event_type=EventType.HUMAN_DECISION_RECEIVED,
                    family=EventFamily.HITL,
                    interrupt_id="intr-001",
                    decision_id="dec-001",
                )
            )

    def test_wrong_subcontract_placement_fails(self) -> None:
        from agents.observability.contracts import (
            build_human_decision_record_observability_context,
            build_human_decision_request_observability_context,
        )

        record = build_human_decision_record_observability_context(
            decision_code="ABORT_RUN",
            actor_id="op-1",
            actor_type="HUMAN",
        )
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(
                    event_type=EventType.HUMAN_WAIT_STARTED,
                    family=EventFamily.HITL,
                    interrupt_id="intr-001",
                    human_decision_record=record,
                )
            )
        request = build_human_decision_request_observability_context(
            reason_code="WAIT",
            allowed_decisions=("CONTINUE",),
        )
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                **_event_kwargs(
                    event_type=EventType.RUN_STARTED,
                    human_decision_request=request,
                )
            )

    def test_fingerprint_includes_hitl_semantics(self) -> None:
        from agents.observability.recorder import compute_observability_event_fingerprint
        from agents.observability.contracts import (
            build_human_decision_request_observability_context,
        )

        request_a = build_human_decision_request_observability_context(
            reason_code="REASON_A",
            allowed_decisions=("CONTINUE",),
        )
        request_b = build_human_decision_request_observability_context(
            reason_code="REASON_B",
            allowed_decisions=("CONTINUE",),
        )
        base = _event_kwargs(
            event_id="evt-hitl-fp",
            event_type=EventType.HUMAN_WAIT_STARTED,
            family=EventFamily.HITL,
            interrupt_id="intr-001",
        )
        event_a = build_observability_event(**base, human_decision_request=request_a)
        event_b = build_observability_event(**base, human_decision_request=request_b)
        self.assertNotEqual(
            compute_observability_event_fingerprint(event_a),
            compute_observability_event_fingerprint(event_b),
        )
        replay = build_observability_event(**base, human_decision_request=request_a)
        self.assertEqual(
            compute_observability_event_fingerprint(event_a),
            compute_observability_event_fingerprint(replay),
        )

    def test_legacy_deserialization_without_subcontracts(self) -> None:
        from agents.observability.store import _observability_event_from_dict

        payload = build_observability_event(
            **_event_kwargs(
                event_type=EventType.RUN_STARTED,
            )
        ).to_dict()
        roundtrip = _observability_event_from_dict(payload)
        self.assertIsNone(roundtrip.human_decision_request)
        legacy_wait = {
            "schema_version": OBSERVABILITY_EVENT_SCHEMA_VERSION,
            "event_id": "evt-legacy-wait",
            "run_id": "run-001",
            "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
            "occurred_at": FIXED_AT.isoformat(),
            "family": EventFamily.HITL.value,
            "event_type": EventType.HUMAN_WAIT_STARTED.value,
            "status": EventStatus.OK.value,
            "title": "Legacy wait",
            "stage_id": "HUMAN_GATE",
            "interrupt_id": "intr-legacy",
            "attempt_n": 1,
            "resume_n": 1,
            "detail": {"reason_code": "SHOULD_NOT_MATTER"},
        }
        legacy = _observability_event_from_dict(legacy_wait)
        self.assertIsNone(legacy.human_decision_request)


if __name__ == "__main__":
    unittest.main()
