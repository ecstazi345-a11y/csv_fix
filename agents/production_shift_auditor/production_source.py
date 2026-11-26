"""PSAA I2-A — trusted production AuditInputResolver for managed runtime.

Reuses existing EOS-SEC trusted READ + rows_to_shift_audit_input.
Does NOT persist to durable history (I2-B).
Does NOT invent source versions from content hashes.
Legacy BHK / daily_progress_active is a pilot source — not target SINTARK.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from agents.observability.contracts import AgentRun, RunRequest, _unfreeze_jsonable
from agents.production_shift_auditor.contracts import (
    DataSourceKind,
    LaborSemanticsStatus,
    LaborUnit,
    OperationLaborClaim,
    ShiftAuditInput,
)
from agents.production_shift_auditor.history_contracts import content_hash
from agents.production_shift_auditor.managed_run_contracts import (
    CODE_PSAA_INVALID_INPUT,
    CODE_PSAA_MISSING_SOURCE,
    CODE_PSAA_SCOPE_MISMATCH,
    PsaaManagedLauncherError,
)
from agents.production_shift_auditor.read_adapter import (
    DEFAULT_PRODUCTIVE_HOURS_PER_PERSON,
    ShiftGrainError,
    rows_to_shift_audit_input,
)
from agents.production_shift_auditor.tools import load_shift_daily_progress
from security.agent_execution_context import AgentExecutionContext

SOURCE_ACQUISITION_PATH = (
    "EOS-SEC:load_shift_daily_progress→execute_shift_daily_progress_read"
    "→psaa_shift_read_service.daily_progress_active→rows_to_shift_audit_input"
)

# Matches services/psaa_shift_read_service.py soft limit.
TRUSTED_READ_ROW_LIMIT = 5000

KNOWN_LEGACY_LIMITATIONS: tuple[str, ...] = (
    "LEGACY_BHK_AIRTABLE_SYNC_OVERWRITE_SEMANTICS",
    "COMPOSITE_QUERY_GRAIN_NOT_PERMANENT_SHIFT_IDENTITY",
    "DIRECT_WORK_HOURS_SEMANTICS_PARTIALLY_PROVEN",
    "CREW_SIZE_NOT_PROVEN_HEADCOUNT",
    "NO_VERIFIED_PHYSICAL_EXECUTION_AUTHORITY",
    "SOURCE_VERSION_REF_TYPICALLY_ABSENT",
    "PILOT_SOURCE_NOT_TARGET_SINTARK",
    "HOUR_FIELD_UNPROVEN_NUMERIC_VALUE_IS_NOT_PROVEN_MAN_MINUTES",
    "MISSING_DIRECT_WORK_HOURS_MAY_APPEAR_AS_NUMERIC_ZERO_PLACEHOLDER",
)

SELECTION_COMPLETE_WITHIN_LIMIT = "COMPLETE_WITHIN_TRUSTED_READ_LIMIT"
SELECTION_POSSIBLY_TRUNCATED = "POSSIBLY_TRUNCATED_AT_TRUSTED_READ_LIMIT"


@dataclass(frozen=True)
class ProductionSourceSnapshot:
    """Process-local immutable acquisition snapshot. NOT durable history.

    Nested row mappings are MappingProxyType-frozen. Callers must not rely on
    mutating returned rows; mutations raise TypeError / fail closed.
    """

    snapshot_id: str
    retrieved_at_utc: str
    project_code: str
    work_date: str
    crew_id: str
    shift_type: Optional[str]
    source_table: str
    acquisition_path: str
    source_record_ids: tuple[str, ...]
    row_count: int
    original_rows: tuple[Mapping[str, Any], ...]
    original_rows_content_hash: str
    normalized_input_content_hash: Optional[str]
    source_version_ref: Optional[str]
    live_data_proof: str
    missing_context: tuple[str, ...]
    known_limitations: tuple[str, ...]
    selection_limit: int = TRUSTED_READ_ROW_LIMIT
    selection_completeness: str = SELECTION_COMPLETE_WITHIN_LIMIT
    read_meta_safe: Mapping[str, Any] = field(default_factory=dict)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "retrieved_at_utc": self.retrieved_at_utc,
            "project_code": self.project_code,
            "work_date": self.work_date,
            "crew_id": self.crew_id,
            "shift_type": self.shift_type,
            "source_table": self.source_table,
            "acquisition_path": self.acquisition_path,
            "source_record_ids": list(self.source_record_ids),
            "row_count": self.row_count,
            "original_rows_content_hash": self.original_rows_content_hash,
            "normalized_input_content_hash": self.normalized_input_content_hash,
            "source_version_ref": self.source_version_ref,
            "live_data_proof": self.live_data_proof,
            "missing_context": list(self.missing_context),
            "known_limitations": list(self.known_limitations),
            "selection_limit": self.selection_limit,
            "selection_completeness": self.selection_completeness,
            # Explicit: content hash is NOT a production source revision.
            "content_hash_is_not_source_version": True,
            "durable_history_persisted": False,
            "composite_grain_is_not_permanent_shift_identity": True,
        }


class TrustedProductionAuditInputResolver:
    """Production AuditInputResolver for PsaaManagedRuntimeLauncher.

    Uses authorized AgentExecutionContext + existing trusted READ tool only.
    Fixture resolver remains available separately and is NOT this class.
    """

    def __init__(
        self,
        *,
        productive_hours_per_person: float = DEFAULT_PRODUCTIVE_HOURS_PER_PERSON,
        read_loader=None,
    ) -> None:
        self._productive_hours_per_person = float(productive_hours_per_person)
        # Injected only for deterministic tests; default = real tool façade.
        self._read_loader = read_loader or load_shift_daily_progress
        self._last_snapshot: Optional[ProductionSourceSnapshot] = None

    @property
    def last_snapshot(self) -> Optional[ProductionSourceSnapshot]:
        return self._last_snapshot

    def __call__(
        self,
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> ShiftAuditInput:
        return self.resolve(run_request, agent_run, context)

    def resolve(
        self,
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> ShiftAuditInput:
        scope = _scope_dict(run_request)
        work_date = _require_scope_text(scope, "work_date")
        crew_id = _require_scope_text(scope, "crew_id")
        shift_raw = scope.get("shift_type")
        shift_type = (
            str(shift_raw).strip()
            if shift_raw is not None and str(shift_raw).strip()
            else None
        )

        if context.project_code != run_request.project_code:
            raise PsaaManagedLauncherError(
                CODE_PSAA_SCOPE_MISMATCH,
                "context.project_code does not match run_request.project_code",
            )
        if agent_run.project_code != run_request.project_code:
            raise PsaaManagedLauncherError(
                CODE_PSAA_SCOPE_MISMATCH,
                "agent_run.project_code does not match run_request.project_code",
            )

        try:
            df, meta = self._read_loader(
                context,
                crew_id=crew_id,
                work_date=work_date,
                shift_type=shift_type,
            )
        except PsaaManagedLauncherError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PsaaManagedLauncherError(
                CODE_PSAA_MISSING_SOURCE,
                f"trusted source acquisition failed: {exc}",
            ) from exc

        live_proof = str(meta.get("live_data_proof") or "UNKNOWN")
        safe_meta = _safe_read_meta(meta)
        if meta.get("error"):
            raise PsaaManagedLauncherError(
                CODE_PSAA_MISSING_SOURCE,
                f"trusted READ error: {meta.get('error')}",
            )
        if df is None or getattr(df, "empty", True):
            raise PsaaManagedLauncherError(
                CODE_PSAA_MISSING_SOURCE,
                "trusted READ returned no rows for requested shift grain",
            )

        plain_rows = _rows_as_mappings(df)
        frozen_rows = _freeze_rows(plain_rows)
        record_ids = _collect_record_ids(plain_rows)
        rows_hash = content_hash(list(plain_rows))
        retrieved_at = datetime.now(timezone.utc).isoformat()
        snapshot_id = f"psaa_src:{agent_run.run_id}:{rows_hash[:16]}"

        missing_context: list[str] = []
        if not record_ids:
            missing_context.append("SOURCE_RECORD_IDS_ABSENT")
        if shift_type is None:
            missing_context.append("SHIFT_TYPE_NOT_DECLARED_IN_SCOPE")

        selection_completeness = SELECTION_COMPLETE_WITHIN_LIMIT
        if len(plain_rows) >= TRUSTED_READ_ROW_LIMIT:
            selection_completeness = SELECTION_POSSIBLY_TRUNCATED
            missing_context.append("SOURCE_SELECTION_MAY_BE_TRUNCATED_AT_LIMIT")
            missing_context.append("SNAPSHOT_COMPLETENESS_NOT_FULLY_PROVEN")

        try:
            audit_input = rows_to_shift_audit_input(
                df,
                project_code=context.project_code,
                crew_id=crew_id,
                work_date=work_date,
                shift_type=shift_type,
                productive_hours_per_person=self._productive_hours_per_person,
            )
        except ShiftGrainError as exc:
            self._last_snapshot = ProductionSourceSnapshot(
                snapshot_id=snapshot_id,
                retrieved_at_utc=retrieved_at,
                project_code=context.project_code,
                work_date=work_date,
                crew_id=crew_id,
                shift_type=shift_type,
                source_table="daily_progress_active",
                acquisition_path=SOURCE_ACQUISITION_PATH,
                source_record_ids=record_ids,
                row_count=len(plain_rows),
                original_rows=frozen_rows,
                original_rows_content_hash=rows_hash,
                normalized_input_content_hash=None,
                source_version_ref=None,
                live_data_proof=live_proof,
                missing_context=tuple(
                    dict.fromkeys(missing_context + [f"SHIFT_GRAIN:{exc.code}"])
                ),
                known_limitations=KNOWN_LEGACY_LIMITATIONS,
                selection_limit=TRUSTED_READ_ROW_LIMIT,
                selection_completeness=selection_completeness,
                read_meta_safe=MappingProxyType(dict(safe_meta)),
            )
            code = (
                CODE_PSAA_SCOPE_MISMATCH
                if exc.code
                in {
                    "MIXED_PROJECT",
                    "MIXED_CREW",
                    "MIXED_DATE",
                    "MIXED_SHIFT_TYPE",
                    "AMBIGUOUS_SHIFT_TYPE",
                    "CONFLICTING_CREW_SIZE",
                }
                else CODE_PSAA_INVALID_INPUT
            )
            raise PsaaManagedLauncherError(
                code,
                f"source grain validation failed: {exc.code}: {exc}",
            ) from exc

        # Annotate labor uncertainty at source boundary without rewriting skill engines.
        annotated_ops = _annotate_unproven_labor_operations(
            audit_input.operations, plain_rows
        )

        # Provenance is determined by trusted acquisition path — not caller flags.
        provenance = list(audit_input.provenance_notes) + [
            f"acquisition_path={SOURCE_ACQUISITION_PATH}",
            f"snapshot_id={snapshot_id}",
            f"original_rows_content_hash={rows_hash}",
            "content_hash_is_not_source_version=true",
            f"live_data_proof={live_proof}",
            f"run_id={agent_run.run_id}",
            f"request_id={run_request.request_id}",
            "durable_history_persisted=false",
            f"selection_completeness={selection_completeness}",
            "HOUR_FIELD_UNPROVEN_NOT_ACTUAL_PROVEN_LABOR",
            "NUMERIC_ZERO_WITH_HOUR_FIELD_UNPROVEN_IS_NOT_PROVEN_ZERO_LABOR",
            *KNOWN_LEGACY_LIMITATIONS,
        ]
        # Never promote snapshot hash to source_version_ref.
        if audit_input.source_version_ref is not None:
            source_version = audit_input.source_version_ref
        else:
            source_version = None
            missing_context.append("SOURCE_VERSION_REF_ABSENT")

        if audit_input.labor_semantics_status is LaborSemanticsStatus.PARTIALLY_PROVEN:
            missing_context.append("LABOR_SEMANTICS_PARTIALLY_PROVEN")
        if any(op.labor_unit is LaborUnit.HOUR_FIELD_UNPROVEN for op in annotated_ops):
            missing_context.append("HOUR_FIELD_UNPROVEN_PRESENT")
        if any(
            "MISSING_DIRECT_WORK_HOURS_NUMERIC_PLACEHOLDER_NOT_ACTUAL_ZERO_LABOR" in op.notes
            for op in annotated_ops
        ):
            missing_context.append("MISSING_LABOR_NUMERIC_PLACEHOLDER_PRESENT")
        if audit_input.source_kind is not DataSourceKind.DAILY_PROGRESS_ACTIVE:
            missing_context.append(
                f"UNEXPECTED_SOURCE_KIND:{audit_input.source_kind.value}"
            )

        labor_note = audit_input.labor_semantics_note
        if "HOUR_FIELD_UNPROVEN" not in labor_note:
            labor_note = (
                f"{labor_note} | HOUR_FIELD_UNPROVEN values are not proven man-hours "
                "or man-minutes; numeric zero placeholder is not proven actual zero labor."
            )

        enriched = ShiftAuditInput(
            schema_version=audit_input.schema_version,
            source_kind=DataSourceKind.DAILY_PROGRESS_ACTIVE,
            project_code=audit_input.project_code,
            work_date=audit_input.work_date,
            shift_type=audit_input.shift_type,
            crew_id=audit_input.crew_id,
            crew_size=audit_input.crew_size,
            productive_hours_per_person=audit_input.productive_hours_per_person,
            operations=annotated_ops,
            labor_semantics_status=audit_input.labor_semantics_status,
            labor_semantics_note=labor_note,
            source_record_ids=audit_input.source_record_ids,
            physical_volumes=audit_input.physical_volumes,
            facility_building=audit_input.facility_building,
            construction_discipline=audit_input.construction_discipline,
            foreman=audit_input.foreman,
            provenance_notes=tuple(provenance),
            source_version_ref=source_version,
        )
        input_hash = content_hash(enriched.to_dict())
        self._last_snapshot = ProductionSourceSnapshot(
            snapshot_id=snapshot_id,
            retrieved_at_utc=retrieved_at,
            project_code=context.project_code,
            work_date=work_date,
            crew_id=crew_id,
            shift_type=shift_type,
            source_table="daily_progress_active",
            acquisition_path=SOURCE_ACQUISITION_PATH,
            source_record_ids=tuple(enriched.source_record_ids) or record_ids,
            row_count=len(plain_rows),
            original_rows=frozen_rows,
            original_rows_content_hash=rows_hash,
            normalized_input_content_hash=input_hash,
            source_version_ref=source_version,
            live_data_proof=live_proof,
            missing_context=tuple(dict.fromkeys(missing_context)),
            known_limitations=KNOWN_LEGACY_LIMITATIONS,
            selection_limit=TRUSTED_READ_ROW_LIMIT,
            selection_completeness=selection_completeness,
            read_meta_safe=MappingProxyType(dict(safe_meta)),
        )
        return enriched


def build_trusted_production_audit_input_resolver(
    *,
    productive_hours_per_person: float = DEFAULT_PRODUCTIVE_HOURS_PER_PERSON,
    read_loader=None,
) -> TrustedProductionAuditInputResolver:
    """Factory for managed-runtime production source acquisition."""
    return TrustedProductionAuditInputResolver(
        productive_hours_per_person=productive_hours_per_person,
        read_loader=read_loader,
    )


def _scope_dict(run_request: RunRequest) -> dict[str, Any]:
    raw = _unfreeze_jsonable(run_request.scope_request)
    return dict(raw) if isinstance(raw, dict) else {}


def _require_scope_text(scope: Mapping[str, Any], key: str) -> str:
    value = scope.get(key)
    text = "" if value is None else str(value).strip()
    if not text:
        raise PsaaManagedLauncherError(
            CODE_PSAA_INVALID_INPUT,
            f"scope_request.{key} is required for production source acquisition",
        )
    return text


def _rows_as_mappings(df: Any) -> tuple[dict[str, Any], ...]:
    records = df.to_dict(orient="records")
    plain: list[dict[str, Any]] = []
    for row in records:
        item: dict[str, Any] = {}
        for key, value in dict(row).items():
            if value is None:
                item[str(key)] = None
            elif hasattr(value, "item") and callable(value.item):
                try:
                    item[str(key)] = value.item()
                except Exception:  # noqa: BLE001
                    item[str(key)] = value
            else:
                if isinstance(value, float) and math.isnan(value):
                    item[str(key)] = None
                    continue
                item[str(key)] = value
        plain.append(item)
    return tuple(plain)


def _freeze_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    """Deep-freeze row mappings so snapshot exposure is immutable."""
    frozen: list[Mapping[str, Any]] = []
    for row in rows:
        frozen.append(MappingProxyType(dict(row)))
    return tuple(frozen)


def _annotate_unproven_labor_operations(
    operations: Sequence[OperationLaborClaim],
    plain_rows: Sequence[Mapping[str, Any]],
) -> tuple[OperationLaborClaim, ...]:
    """Source-boundary honesty notes; does not rewrite skill engines."""
    out: list[OperationLaborClaim] = []
    for idx, op in enumerate(operations):
        notes = list(op.notes)
        if op.labor_unit is LaborUnit.HOUR_FIELD_UNPROVEN:
            notes.append("HOUR_FIELD_UNPROVEN_NOT_CONVERTIBLE_TO_MAN_MINUTES")
            notes.append("NUMERIC_VALUE_IS_NOT_PROVEN_ACTUAL_LABOR")
            raw = None
            if idx < len(plain_rows):
                raw = plain_rows[idx].get("direct_work_hours")
            if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                notes.append(
                    "MISSING_DIRECT_WORK_HOURS_NUMERIC_PLACEHOLDER_NOT_ACTUAL_ZERO_LABOR"
                )
            else:
                notes.append("DIRECT_WORK_HOURS_PRESENT_BUT_SEMANTICS_UNPROVEN")
        out.append(replace(op, notes=tuple(dict.fromkeys(notes))))
    return tuple(out)


def _collect_record_ids(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    ids: list[str] = []
    for row in rows:
        rid = str(row.get("airtable_record_id") or "").strip()
        if rid and rid not in ids:
            ids.append(rid)
    return tuple(ids)


def _safe_read_meta(meta: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "error",
        "error_code",
        "row_count",
        "source",
        "live_data_proof",
        "filters",
        "credential_policy_code",
        "project_code",
    }
    out: dict[str, Any] = {}
    for key in allowed:
        if key in meta and meta[key] is not None:
            if key == "credential_env":
                continue
            out[key] = meta[key]
    return out
