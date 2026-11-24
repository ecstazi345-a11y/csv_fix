"""PSAA-02 — Shift Audit History contracts.

SOURCE-NEUTRAL. Not observability logs. Not acceptance workflow.
Uses existing ShiftAuditInput / ShiftAuditArtifact snapshots only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional

from agents.production_shift_auditor.contracts import (
    ShiftAuditArtifact,
    ShiftAuditInput,
)

HISTORY_SCHEMA_VERSION = "psaa_shift_audit_history.v0.1"
CODE_HISTORY_BLOCKER = "PSAA_HISTORY_BLOCKER"
CODE_HISTORY_CONFLICT = "PSAA_HISTORY_CONFLICT"
CODE_HISTORY_READBACK_MISMATCH = "PSAA_HISTORY_READBACK_MISMATCH"
CODE_HISTORY_PROJECT_DENIED = "PSAA_HISTORY_PROJECT_DENIED"
CODE_HISTORY_WRITE_FAILED = "PSAA_HISTORY_WRITE_FAILED"

STATUS_CREATED = "CREATED"
STATUS_IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


class ShiftAuditHistoryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"Object of type {type(obj)!r} is not JSON serializable")


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
        default=_json_default,
    )


def content_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _to_plain(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    return obj


@dataclass(frozen=True)
class ShiftAuditHistoryRecord:
    """Immutable persisted professional audit fact."""

    schema_version: str
    audit_id: str
    project_code: str
    work_date: str
    shift_type: Optional[str]
    crew_id: str
    source_kind: str
    source_record_ids: tuple[str, ...]
    input_schema_version: str
    rules_version: str
    agent_code: str
    agent_version: str
    run_id: Optional[str]
    audited_at_utc: str
    math_integrity_status: str
    data_completeness_status: str
    professional_credibility_status: str
    managerial_acceptance_status: str
    input_content_hash: str
    artifact_content_hash: str
    record_content_hash: str
    input_snapshot: Mapping[str, Any]
    artifact_snapshot: Mapping[str, Any]
    uncertainties: tuple[str, ...]
    persisted_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "audit_id": self.audit_id,
            "project_code": self.project_code,
            "work_date": self.work_date,
            "shift_type": self.shift_type,
            "crew_id": self.crew_id,
            "source_kind": self.source_kind,
            "source_record_ids": list(self.source_record_ids),
            "input_schema_version": self.input_schema_version,
            "rules_version": self.rules_version,
            "agent_code": self.agent_code,
            "agent_version": self.agent_version,
            "run_id": self.run_id,
            "audited_at_utc": self.audited_at_utc,
            "math_integrity_status": self.math_integrity_status,
            "data_completeness_status": self.data_completeness_status,
            "professional_credibility_status": self.professional_credibility_status,
            "managerial_acceptance_status": self.managerial_acceptance_status,
            "input_content_hash": self.input_content_hash,
            "artifact_content_hash": self.artifact_content_hash,
            "record_content_hash": self.record_content_hash,
            "input_snapshot": _to_plain(dict(self.input_snapshot)),
            "artifact_snapshot": _to_plain(dict(self.artifact_snapshot)),
            "uncertainties": list(self.uncertainties),
            "persisted_at_utc": self.persisted_at_utc,
        }


@dataclass(frozen=True)
class PersistHistoryResult:
    status: str
    record: ShiftAuditHistoryRecord


def build_history_record(
    audit_input: ShiftAuditInput,
    artifact: ShiftAuditArtifact,
    *,
    persisted_at_utc: Optional[str] = None,
) -> ShiftAuditHistoryRecord:
    if artifact.audit_id.strip() == "":
        raise ShiftAuditHistoryError(CODE_HISTORY_BLOCKER, "audit_id is required")
    if audit_input.project_code.strip() == "":
        raise ShiftAuditHistoryError(CODE_HISTORY_BLOCKER, "project_code is required")

    input_snap = _to_plain(asdict(audit_input))
    art_snap = _to_plain(asdict(artifact))
    in_hash = content_hash(input_snap)
    art_hash = content_hash(art_snap)

    uncertainties: list[str] = []
    uncertainties.extend(str(x) for x in artifact.missing_data)
    uncertainties.extend(str(x) for x in artifact.clarification_questions)
    uncertainties.extend(str(x) for x in artifact.hypotheses_unproven)

    stamp = persisted_at_utc or datetime.now(timezone.utc).isoformat()
    body = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "audit_id": artifact.audit_id,
        "project_code": audit_input.project_code,
        "work_date": audit_input.work_date,
        "shift_type": audit_input.shift_type,
        "crew_id": audit_input.crew_id,
        "source_kind": audit_input.source_kind.value
        if isinstance(audit_input.source_kind, Enum)
        else str(audit_input.source_kind),
        "source_record_ids": list(audit_input.source_record_ids),
        "input_schema_version": audit_input.schema_version,
        "rules_version": artifact.rules_version,
        "agent_code": artifact.agent_code,
        "agent_version": artifact.agent_version,
        "run_id": artifact.run_id,
        "audited_at_utc": artifact.created_at_utc,
        "math_integrity_status": artifact.math_integrity_status.value
        if isinstance(artifact.math_integrity_status, Enum)
        else str(artifact.math_integrity_status),
        "data_completeness_status": artifact.data_completeness_status.value
        if isinstance(artifact.data_completeness_status, Enum)
        else str(artifact.data_completeness_status),
        "professional_credibility_status": (
            artifact.professional_credibility_status.value
            if isinstance(artifact.professional_credibility_status, Enum)
            else str(artifact.professional_credibility_status)
        ),
        "managerial_acceptance_status": (
            artifact.managerial_acceptance_status.value
            if isinstance(artifact.managerial_acceptance_status, Enum)
            else str(artifact.managerial_acceptance_status)
        ),
        "input_content_hash": in_hash,
        "artifact_content_hash": art_hash,
        "uncertainties": uncertainties,
        "input_snapshot": input_snap,
        "artifact_snapshot": art_snap,
    }
    # record hash excludes persisted_at so idempotent replay compares content
    rec_hash = content_hash(body)

    return ShiftAuditHistoryRecord(
        schema_version=HISTORY_SCHEMA_VERSION,
        audit_id=artifact.audit_id,
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        shift_type=audit_input.shift_type,
        crew_id=audit_input.crew_id,
        source_kind=str(body["source_kind"]),
        source_record_ids=tuple(audit_input.source_record_ids),
        input_schema_version=audit_input.schema_version,
        rules_version=artifact.rules_version,
        agent_code=artifact.agent_code,
        agent_version=artifact.agent_version,
        run_id=artifact.run_id,
        audited_at_utc=artifact.created_at_utc,
        math_integrity_status=str(body["math_integrity_status"]),
        data_completeness_status=str(body["data_completeness_status"]),
        professional_credibility_status=str(body["professional_credibility_status"]),
        managerial_acceptance_status=str(body["managerial_acceptance_status"]),
        input_content_hash=in_hash,
        artifact_content_hash=art_hash,
        record_content_hash=rec_hash,
        input_snapshot=input_snap,
        artifact_snapshot=art_snap,
        uncertainties=tuple(uncertainties),
        persisted_at_utc=stamp,
    )


def record_from_dict(payload: Mapping[str, Any]) -> ShiftAuditHistoryRecord:
    return ShiftAuditHistoryRecord(
        schema_version=str(payload["schema_version"]),
        audit_id=str(payload["audit_id"]),
        project_code=str(payload["project_code"]),
        work_date=str(payload["work_date"]),
        shift_type=payload.get("shift_type"),
        crew_id=str(payload["crew_id"]),
        source_kind=str(payload["source_kind"]),
        source_record_ids=tuple(payload.get("source_record_ids") or ()),
        input_schema_version=str(payload["input_schema_version"]),
        rules_version=str(payload["rules_version"]),
        agent_code=str(payload["agent_code"]),
        agent_version=str(payload["agent_version"]),
        run_id=payload.get("run_id"),
        audited_at_utc=str(payload["audited_at_utc"]),
        math_integrity_status=str(payload["math_integrity_status"]),
        data_completeness_status=str(payload["data_completeness_status"]),
        professional_credibility_status=str(payload["professional_credibility_status"]),
        managerial_acceptance_status=str(payload["managerial_acceptance_status"]),
        input_content_hash=str(payload["input_content_hash"]),
        artifact_content_hash=str(payload["artifact_content_hash"]),
        record_content_hash=str(payload["record_content_hash"]),
        input_snapshot=dict(payload.get("input_snapshot") or {}),
        artifact_snapshot=dict(payload.get("artifact_snapshot") or {}),
        uncertainties=tuple(payload.get("uncertainties") or ()),
        persisted_at_utc=str(payload["persisted_at_utc"]),
    )
