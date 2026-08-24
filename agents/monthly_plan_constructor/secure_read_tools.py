"""
Constructor Runtime v0.1 Increment 3 — secure read tool adapters.

AGENT HAS ACCESS ONLY TO NARROW ALLOWLISTED TOOLS.
MODEL IS NOT A SECURITY BOUNDARY. NO SERVICE BYPASS.

Read-time mission is passed into the trusted-read port (LAYER 1).
Post-read assertion reuses Increment 1 (LAYER 2). Extra-scope rows fail closed.

Does not import dirty tools.py / read_service.py.
Does not call load_constructor_line_economics.
Does not call economics. No Streamlit, LangGraph, SQL, or writes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

import pandas as pd

from agents.monthly_plan_constructor.mission_scope import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_DATA_CONTRACT_BLOCKER,
    ConstructorMissionScope,
    MissionScopeError,
    assert_rows_belong_to_mission_scope,
)
from security.agent_execution_context import (
    TOOL_LOAD_SCOPE,
    AgentExecutionContext,
)
from security.trusted_read_executor import (
    ToolPermissionError,
    validate_context_for_tool,
)

SCHEMA_VERSION = "constructor_reality_read.v0.1"
CODE_SECURITY_DENIED = "SECURITY_DENIED"

ScopeReader = Callable[[AgentExecutionContext, ConstructorMissionScope], Sequence[Mapping[str, Any]]]


class SecureReadError(ValueError):
    """Fail-closed Constructor secure read violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ScopeReadCapabilities:
    """What the injected trusted-read port can enforce at read time."""

    facility: bool = True
    discipline: bool = True
    system: bool = True
    iwp: bool = True
    queue: bool = False


DEFAULT_SCOPE_READ_CAPABILITIES = ScopeReadCapabilities()


@dataclass(frozen=True)
class ConstructorRealityRow:
    project_code: str
    month_key: str
    facility: str
    discipline: str
    system: str
    iwp: str
    queue: str
    boq_code: str
    boq_name: str
    unit: str


@dataclass(frozen=True)
class ConstructorReadProvenance:
    read_id: str
    read_at: str
    tool_name: str
    project_code: str
    month_key: str
    authorization_id: str
    row_count: int
    source_reference: str


@dataclass(frozen=True)
class ConstructorRealityRead:
    """Bounded operational-reality snapshot. Not a CandidatePackage. Not a DataFrame."""

    read_id: str
    schema_version: str
    read_at: str
    tool_name: str
    project_code: str
    month_key: str
    scope: ConstructorMissionScope
    row_count: int
    rows: tuple[ConstructorRealityRow, ...]
    provenance: ConstructorReadProvenance
    warnings: tuple[str, ...]

    @property
    def snapshot_id(self) -> str:
        return self.read_id


class ConstructorScopeReader(Protocol):
    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> Sequence[Mapping[str, Any]]:
        ...


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_project(value: Any) -> str:
    return str(value or "").strip().upper()


def _cell(raw: Mapping[str, Any], *names: str) -> str:
    for name in names:
        if name not in raw:
            continue
        value = raw.get(name)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        text = str(value).strip()
        if text.lower() in {"", "nan", "none", "<na>"}:
            continue
        return text
    return ""


def _require_context_and_mission(
    context: Optional[AgentExecutionContext],
    mission: ConstructorMissionScope,
) -> None:
    if context is None:
        raise SecureReadError(CODE_SECURITY_DENIED, "AgentExecutionContext is required")
    if not isinstance(context, AgentExecutionContext):
        raise SecureReadError(CODE_SECURITY_DENIED, "invalid AgentExecutionContext")
    if not isinstance(mission, ConstructorMissionScope):
        raise SecureReadError(
            CODE_DATA_CONTRACT_BLOCKER,
            "mission must be ConstructorMissionScope",
        )
    if _norm_project(context.project_code) != _norm_project(mission.project_code):
        raise SecureReadError(
            CODE_SECURITY_DENIED,
            "authorized project does not match mission project",
        )
    if not mission.month_key or not mission.month_key_canonical:
        raise SecureReadError(
            CODE_DATA_CONTRACT_BLOCKER,
            "mission month_key is required",
        )


def _assert_optional_capabilities(
    mission: ConstructorMissionScope,
    capabilities: ScopeReadCapabilities,
) -> None:
    checks = (
        ("facility_scope", capabilities.facility),
        ("discipline_scope", capabilities.discipline),
        ("system_scope", capabilities.system),
        ("iwp_scope", capabilities.iwp),
        ("queue_scope", capabilities.queue),
    )
    for field_name, supported in checks:
        requested = getattr(mission, field_name)
        if requested is not None and not supported:
            raise SecureReadError(
                CODE_AMBIGUOUS_SCOPE,
                f"{field_name} is set but the approved read tool cannot enforce it",
            )


def _rows_to_assertion_frame(
    records: Sequence[Mapping[str, Any]],
    mission: ConstructorMissionScope,
) -> pd.DataFrame:
    rows = []
    for raw in records:
        month = _cell(raw, "month_key") or mission.month_key
        rows.append(
            {
                "project_code": _cell(raw, "project_code") or mission.project_code,
                "month_key": month,
                "facility": _cell(raw, "facility", "facility_building"),
                "facility_building": _cell(raw, "facility_building", "facility"),
                "discipline": _cell(raw, "discipline", "construction_discipline"),
                "construction_discipline": _cell(
                    raw, "construction_discipline", "discipline"
                ),
                "system": _cell(raw, "system", "system_label"),
                "system_label": _cell(raw, "system_label", "system"),
                "iwp": _cell(raw, "iwp", "iwp_id"),
                "iwp_id": _cell(raw, "iwp_id", "iwp"),
                "construction_queue": _cell(raw, "construction_queue", "queue"),
                "queue": _cell(raw, "queue", "construction_queue"),
                "boq_code": _cell(raw, "boq_code"),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "project_code",
                "month_key",
                "facility",
                "facility_building",
                "discipline",
                "construction_discipline",
                "system",
                "system_label",
                "iwp",
                "iwp_id",
                "construction_queue",
                "queue",
                "boq_code",
            ]
        )
    return pd.DataFrame(rows)


def _to_reality_row(
    raw: Mapping[str, Any],
    mission: ConstructorMissionScope,
) -> ConstructorRealityRow:
    return ConstructorRealityRow(
        project_code=_cell(raw, "project_code") or mission.project_code,
        month_key=_cell(raw, "month_key") or mission.month_key,
        facility=_cell(raw, "facility", "facility_building"),
        discipline=_cell(raw, "discipline", "construction_discipline"),
        system=_cell(raw, "system", "system_label"),
        iwp=_cell(raw, "iwp", "iwp_id"),
        queue=_cell(raw, "queue", "construction_queue"),
        boq_code=_cell(raw, "boq_code"),
        boq_name=_cell(raw, "boq_name"),
        unit=_cell(raw, "unit", "unit_of_measure"),
    )


def default_executor_scope_reader(
    context: AgentExecutionContext,
    mission: ConstructorMissionScope,
) -> Sequence[Mapping[str, Any]]:
    """
    Production port: approved executor only, then Increment 1 bind as
    adapter-level read-time narrowing of the tool result.

    Query-side filters on load_constructor_scope are not added here because
    that service file is a preserved dirty MPCA-002/003 experiment.
    """
    from security.trusted_read_executor import execute_constructor_scope_read

    frame, meta = execute_constructor_scope_read(context)
    if meta.get("error"):
        raise SecureReadError("READ_FAILED", str(meta.get("error")))
    work = frame.copy() if frame is not None else pd.DataFrame()
    if "month_key" not in work.columns:
        work["month_key"] = mission.month_key
    from agents.monthly_plan_constructor.mission_scope import bind_scope_to_mission

    scoped = bind_scope_to_mission(work, mission)
    return scoped.to_dict(orient="records")


def read_constructor_reality(
    context: AgentExecutionContext,
    mission: ConstructorMissionScope,
    *,
    scope_reader: Optional[ScopeReader] = None,
    capabilities: ScopeReadCapabilities = DEFAULT_SCOPE_READ_CAPABILITIES,
    read_at: Optional[str] = None,
    source_reference: str = "monthly_scope_picker_view",
) -> ConstructorRealityRead:
    """
    Secure Constructor remaining-scope read.

    LAYER 1: mission is passed to the trusted-read port.
    LAYER 2: Increment 1 post-read assertion; out-of-scope rows fail closed.
    """
    _require_context_and_mission(context, mission)
    _assert_optional_capabilities(mission, capabilities)
    try:
        validate_context_for_tool(context, TOOL_LOAD_SCOPE)
    except ToolPermissionError as exc:
        raise SecureReadError(exc.code, str(exc)) from exc

    reader = scope_reader or default_executor_scope_reader
    try:
        raw_rows = list(reader(context, mission))
    except SecureReadError:
        raise
    except MissionScopeError as exc:
        raise SecureReadError(exc.code, str(exc)) from exc
    except ToolPermissionError as exc:
        raise SecureReadError(exc.code, str(exc)) from exc

    assertion_frame = _rows_to_assertion_frame(raw_rows, mission)
    try:
        assert_rows_belong_to_mission_scope(assertion_frame, mission)
    except MissionScopeError as exc:
        raise SecureReadError(
            exc.code,
            "post-read assertion failed: row is outside mission scope",
        ) from exc

    typed_rows = tuple(_to_reality_row(raw, mission) for raw in raw_rows)
    stamp = read_at or _utc_now_iso()
    read_id = str(uuid.uuid4())
    return ConstructorRealityRead(
        read_id=read_id,
        schema_version=SCHEMA_VERSION,
        read_at=stamp,
        tool_name=TOOL_LOAD_SCOPE,
        project_code=mission.project_code,
        month_key=mission.month_key,
        scope=mission,
        row_count=len(typed_rows),
        rows=typed_rows,
        provenance=ConstructorReadProvenance(
            read_id=read_id,
            read_at=stamp,
            tool_name=TOOL_LOAD_SCOPE,
            project_code=mission.project_code,
            month_key=mission.month_key,
            authorization_id=context.authorization_id,
            row_count=len(typed_rows),
            source_reference=source_reference,
        ),
        warnings=(
            "labor/economic metadata NOT_AVAILABLE until approved economics tool",
        ),
    )
