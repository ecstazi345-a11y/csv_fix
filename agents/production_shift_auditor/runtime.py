"""Thin PSAA runtime — S01 only. No LangGraph. No Constructor packages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from agents.observability.contracts import (
    EventStatus,
    EventType,
    build_observability_event,
)
from agents.observability.recorder import (
    InMemoryObservabilityRecorder,
    ObservabilityRecorder,
)
from agents.production_shift_auditor import AGENT_CODE, AGENT_VERSION
from agents.production_shift_auditor.contracts import (
    INPUT_SCHEMA_VERSION,
    DataSourceKind,
    LaborSemanticsStatus,
    ShiftAuditArtifact,
    ShiftAuditInput,
)
from agents.production_shift_auditor.read_adapter import (
    DEFAULT_PRODUCTIVE_HOURS_PER_PERSON,
    ShiftGrainError,
    rows_to_shift_audit_input,
)
from agents.production_shift_auditor.s01_mathematical_integrity import evaluate_s01
from agents.production_shift_auditor.tools import load_shift_daily_progress
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)


@dataclass(frozen=True)
class PsaaAuditResult:
    artifact: ShiftAuditArtifact
    run_id: str
    live_data_proof: str
    read_meta: dict[str, Any]
    observability_event_ids: tuple[str, ...] = ()


def audit_shift_from_input(
    audit_input: ShiftAuditInput,
    *,
    run_id: Optional[str] = None,
    recorder: Optional[ObservabilityRecorder] = None,
) -> PsaaAuditResult:
    """Deterministic S01 over an already-built ShiftAuditInput (fixture or mapped)."""
    rid = run_id or f"run_psaa_{uuid.uuid4().hex[:12]}"
    event_ids: list[str] = []
    rec = recorder or InMemoryObservabilityRecorder()
    _record_lifecycle(rec, rid, audit_input.project_code, event_ids, started=True)

    artifact = evaluate_s01(audit_input, run_id=rid)
    _record_lifecycle(
        rec,
        rid,
        audit_input.project_code,
        event_ids,
        started=False,
        artifact=artifact,
        failed=False,
    )

    return PsaaAuditResult(
        artifact=artifact,
        run_id=rid,
        live_data_proof="NOT_APPLICABLE_FIXTURE_OR_PREBUILT_INPUT",
        read_meta={"source_kind": audit_input.source_kind.value},
        observability_event_ids=tuple(event_ids),
    )


def audit_shift_from_daily_progress(
    *,
    project_code: str,
    crew_id: str,
    work_date: str,
    shift_type: Optional[str] = None,
    productive_hours_per_person: float = DEFAULT_PRODUCTIVE_HOURS_PER_PERSON,
    context: Optional[AgentExecutionContext] = None,
    recorder: Optional[ObservabilityRecorder] = None,
) -> PsaaAuditResult:
    """Trusted READ → map → S01. Live proof status comes from executor meta."""
    ctx = context or issue_read_only_agent_context(
        agent_code=AGENT_CODE,
        project_code=project_code,
    )
    rid = ctx.run_id
    rec = recorder or InMemoryObservabilityRecorder()
    event_ids: list[str] = []
    _record_lifecycle(rec, rid, project_code, event_ids, started=True)

    df, meta = load_shift_daily_progress(
        ctx,
        crew_id=crew_id,
        work_date=work_date,
        shift_type=shift_type,
    )
    live_proof = str(meta.get("live_data_proof") or "UNKNOWN")

    if meta.get("error") or df.empty:
        shell = ShiftAuditInput(
            schema_version=INPUT_SCHEMA_VERSION,
            source_kind=DataSourceKind.DAILY_PROGRESS_ACTIVE,
            project_code=project_code,
            work_date=work_date,
            shift_type=shift_type,
            crew_id=crew_id,
            crew_size=0,
            productive_hours_per_person=productive_hours_per_person,
            operations=(),
            labor_semantics_status=LaborSemanticsStatus.UNPROVEN,
            labor_semantics_note="READ failed or returned no rows",
            provenance_notes=(
                f"live_data_proof={live_proof}",
                f"read_error={meta.get('error')}",
            ),
        )
        artifact = evaluate_s01(shell, run_id=rid)
        _record_lifecycle(
            rec, rid, project_code, event_ids, started=False, artifact=artifact, failed=True
        )
        return PsaaAuditResult(
            artifact=artifact,
            run_id=rid,
            live_data_proof=live_proof,
            read_meta=dict(meta),
            observability_event_ids=tuple(event_ids),
        )

    try:
        audit_input = rows_to_shift_audit_input(
            df,
            project_code=project_code,
            crew_id=crew_id,
            work_date=work_date,
            shift_type=shift_type,
            productive_hours_per_person=productive_hours_per_person,
        )
    except ShiftGrainError as exc:
        source_ids: tuple[str, ...] = ()
        if "airtable_record_id" in df.columns:
            source_ids = tuple(
                str(x) for x in df["airtable_record_id"].tolist() if str(x).strip()
            )
        shell = ShiftAuditInput(
            schema_version=INPUT_SCHEMA_VERSION,
            source_kind=DataSourceKind.DAILY_PROGRESS_ACTIVE,
            project_code=project_code,
            work_date=work_date,
            shift_type=shift_type,
            crew_id=crew_id,
            crew_size=0,
            productive_hours_per_person=productive_hours_per_person,
            operations=(),
            labor_semantics_status=LaborSemanticsStatus.UNPROVEN,
            labor_semantics_note=str(exc),
            provenance_notes=(
                f"shift_grain_error={exc.code}",
                f"diagnostics={exc.diagnostics}",
                f"live_data_proof={live_proof}",
            ),
            source_record_ids=source_ids,
        )
        artifact = evaluate_s01(shell, run_id=rid)
        _record_lifecycle(
            rec, rid, project_code, event_ids, started=False, artifact=artifact, failed=True
        )
        return PsaaAuditResult(
            artifact=artifact,
            run_id=rid,
            live_data_proof=live_proof,
            read_meta={
                **dict(meta),
                "shift_grain_error": exc.code,
                "diagnostics": exc.diagnostics,
            },
            observability_event_ids=tuple(event_ids),
        )

    artifact = evaluate_s01(audit_input, run_id=rid)
    _record_lifecycle(
        rec, rid, project_code, event_ids, started=False, artifact=artifact, failed=False
    )
    return PsaaAuditResult(
        artifact=artifact,
        run_id=rid,
        live_data_proof=live_proof,
        read_meta=dict(meta),
        observability_event_ids=tuple(event_ids),
    )


def _record_lifecycle(
    recorder: ObservabilityRecorder,
    run_id: str,
    project_code: str,
    event_ids: list[str],
    *,
    started: bool,
    artifact: Optional[ShiftAuditArtifact] = None,
    failed: bool = False,
) -> None:
    """Best-effort Class-A lifecycle events. Observability must not block S01."""
    now = datetime.now(timezone.utc)
    try:
        if started:
            ev = build_observability_event(
                event_id=f"evt_{run_id}_start",
                run_id=run_id,
                agent_code=AGENT_CODE,
                occurred_at=now,
                event_type=EventType.RUN_STARTED,
                status=EventStatus.OK,
                title="PSAA S01 run started",
                detail={
                    "agent_version": AGENT_VERSION,
                    "skill": "S01",
                    "project_code": project_code,
                },
            )
        else:
            assert artifact is not None
            ev = build_observability_event(
                event_id=f"evt_{run_id}_done",
                run_id=run_id,
                agent_code=AGENT_CODE,
                occurred_at=now,
                event_type=EventType.RUN_FAILED if failed else EventType.RUN_COMPLETED,
                status=EventStatus.FAILED if failed else EventStatus.OK,
                title="PSAA S01 run finished",
                artifact_type="ShiftAuditArtifact",
                artifact_id=artifact.audit_id,
                detail={
                    "math_integrity_status": artifact.math_integrity_status.value,
                    "data_completeness_status": artifact.data_completeness_status.value,
                    "rules_version": artifact.rules_version,
                    "project_code": project_code,
                },
            )
        recorder.record_event(ev)
        event_ids.append(ev.event_id)
    except Exception:  # noqa: BLE001
        pass
