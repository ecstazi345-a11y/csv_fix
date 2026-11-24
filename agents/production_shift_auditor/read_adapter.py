"""Map daily_progress_active rows → ShiftAuditInput.

Does NOT invent Airtable IDs. Does NOT silently treat direct_work_hours as man-hours.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from agents.production_shift_auditor.contracts import (
    INPUT_SCHEMA_VERSION,
    DataSourceKind,
    LaborSemanticsStatus,
    LaborUnit,
    OperationLaborClaim,
    PhysicalVolume,
    ShiftAuditInput,
)

DEFAULT_PRODUCTIVE_HOURS_PER_PERSON = 8.0

LABOR_SEMANTICS_NOTE_DP = (
    "Поле direct_work_hours в daily_progress_active связано в документации/"
    "UI с формулировкой вроде «Сумма по бригаде», но для PSAA v0.1 семантика "
    "человеко-часов vs продолжительность vs иная категория времени "
    "считается PARTIALLY_PROVEN / не доказанной как MAN_HOUR. "
    "Автоматическое преобразование в чел·мин запрещено."
)


class ShiftGrainError(ValueError):
    """Fail-closed shift grain / crew diagnostics."""

    def __init__(self, code: str, message: str, *, diagnostics: Optional[dict] = None) -> None:
        self.code = code
        self.diagnostics = diagnostics or {}
        super().__init__(message)


def _uniq_nonempty(series: pd.Series) -> list[str]:
    vals = []
    for v in series.tolist():
        s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()
        if s and s not in vals:
            vals.append(s)
    return vals


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def rows_to_shift_audit_input(
    rows: Sequence[Mapping[str, Any]] | pd.DataFrame,
    *,
    project_code: str,
    crew_id: str,
    work_date: str,
    shift_type: Optional[str] = None,
    productive_hours_per_person: float = DEFAULT_PRODUCTIVE_HOURS_PER_PERSON,
) -> ShiftAuditInput:
    """Build ShiftAuditInput from trusted-read rows.

    Raises ShiftGrainError on mixed grain or conflicting crew_size.
    """
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    if df.empty:
        raise ShiftGrainError(
            "NO_ROWS",
            "daily_progress_active returned no rows for the requested shift grain",
            diagnostics={
                "project_code": project_code,
                "crew_id": crew_id,
                "work_date": work_date,
                "shift_type": shift_type,
            },
        )

    projects = _uniq_nonempty(df["project_code"]) if "project_code" in df.columns else []
    crews = _uniq_nonempty(df["crew_id"]) if "crew_id" in df.columns else []
    dates = _uniq_nonempty(df["work_date"].astype(str)) if "work_date" in df.columns else []
    shifts = _uniq_nonempty(df["shift_type"]) if "shift_type" in df.columns else []

    if len(projects) > 1 or (projects and projects[0] != str(project_code).strip()):
        raise ShiftGrainError(
            "MIXED_PROJECT",
            "Rows span multiple projects or disagree with requested project_code",
            diagnostics={"projects": projects, "requested": project_code},
        )
    if len(crews) > 1 or (crews and crews[0] != str(crew_id).strip()):
        raise ShiftGrainError(
            "MIXED_CREW",
            "Rows span multiple crews or disagree with requested crew_id",
            diagnostics={"crews": crews, "requested": crew_id},
        )
    if len(dates) > 1 or (dates and dates[0][:10] != str(work_date).strip()[:10]):
        raise ShiftGrainError(
            "MIXED_DATE",
            "Rows span multiple work_dates or disagree with requested work_date",
            diagnostics={"dates": dates, "requested": work_date},
        )
    if shift_type:
        st = str(shift_type).strip()
        if len(shifts) > 1 or (shifts and shifts[0] != st):
            raise ShiftGrainError(
                "MIXED_SHIFT_TYPE",
                "Rows span multiple shift_types or disagree with requested shift_type",
                diagnostics={"shift_types": shifts, "requested": st},
            )
    elif len(shifts) > 1:
        raise ShiftGrainError(
            "AMBIGUOUS_SHIFT_TYPE",
            "shift_type not supplied but rows contain multiple shift_type values",
            diagnostics={"shift_types": shifts},
        )

    # crew_size: do NOT sum across operation rows
    crew_sizes: list[float] = []
    if "crew_size" in df.columns:
        for v in df["crew_size"].tolist():
            f = _as_float(v)
            if f is not None and f > 0 and f not in crew_sizes:
                # tolerate float equality for ints
                if not any(abs(f - x) < 1e-9 for x in crew_sizes):
                    crew_sizes.append(f)
    if len(crew_sizes) > 1:
        raise ShiftGrainError(
            "CONFLICTING_CREW_SIZE",
            "Conflicting crew_size values across operation rows; refusing to invent a size",
            diagnostics={"crew_sizes": crew_sizes},
        )
    if not crew_sizes:
        raise ShiftGrainError(
            "MISSING_CREW_SIZE",
            "crew_size absent or non-positive on all rows",
            diagnostics={},
        )
    crew_size = int(crew_sizes[0]) if abs(crew_sizes[0] - int(crew_sizes[0])) < 1e-9 else int(crew_sizes[0])

    ops: list[OperationLaborClaim] = []
    volumes: list[PhysicalVolume] = []
    record_ids: list[str] = []

    for _, row in df.iterrows():
        rid = str(row.get("airtable_record_id") or "").strip()
        if rid and rid not in record_ids:
            record_ids.append(rid)

        name = (
            str(row.get("operation_type") or "").strip()
            or str(row.get("boq_name") or "").strip()
            or str(row.get("boq") or "").strip()
            or "(unnamed operation)"
        )
        hours = _as_float(row.get("direct_work_hours"))
        qty = _as_float(row.get("quantity_today"))
        uom = str(row.get("unit_of_measure") or "").strip() or None
        op_qty = _as_float(row.get("operation_quantity"))

        phys_q = qty if qty is not None and qty > 0 else (
            op_qty if op_qty is not None and op_qty > 0 else None
        )
        phys_u = uom if phys_q is not None else None

        # Critical: do not claim MAN_HOUR without proof
        labor_qty = hours if hours is not None else 0.0
        ops.append(
            OperationLaborClaim(
                operation_name=name,
                claimed_labor_quantity=labor_qty,
                labor_unit=LaborUnit.HOUR_FIELD_UNPROVEN,
                physical_quantity=phys_q,
                physical_unit=phys_u,
                source_record_ids=(rid,) if rid else (),
                notes=(
                    "direct_work_hours carried as HOUR_FIELD_UNPROVEN",
                ),
            )
        )
        if phys_q is not None and phys_u:
            volumes.append(
                PhysicalVolume(
                    label=name,
                    quantity=phys_q,
                    unit=phys_u,
                    linked_operation_name=name,
                )
            )

    resolved_shift = (
        str(shift_type).strip()
        if shift_type
        else (shifts[0] if shifts else None)
    )
    facility = None
    if "facility_building" in df.columns:
        facs = _uniq_nonempty(df["facility_building"])
        facility = facs[0] if len(facs) == 1 else None
    discipline = None
    if "construction_discipline" in df.columns:
        discs = _uniq_nonempty(df["construction_discipline"])
        discipline = discs[0] if len(discs) == 1 else None
    foreman = None
    if "foreman" in df.columns:
        fm = _uniq_nonempty(df["foreman"])
        foreman = fm[0] if len(fm) == 1 else None

    return ShiftAuditInput(
        schema_version=INPUT_SCHEMA_VERSION,
        source_kind=DataSourceKind.DAILY_PROGRESS_ACTIVE,
        project_code=str(project_code).strip(),
        work_date=str(work_date).strip()[:10],
        shift_type=resolved_shift,
        crew_id=str(crew_id).strip(),
        crew_size=crew_size,
        productive_hours_per_person=float(productive_hours_per_person),
        operations=tuple(ops),
        labor_semantics_status=LaborSemanticsStatus.PARTIALLY_PROVEN,
        labor_semantics_note=LABOR_SEMANTICS_NOTE_DP,
        source_record_ids=tuple(record_ids),
        physical_volumes=tuple(volumes),
        facility_building=facility,
        construction_discipline=discipline,
        foreman=foreman,
        provenance_notes=(
            "Trusted READ from daily_progress_active via EOS-SEC executor.",
            "Composite (project, crew, date, shift) is a query grain, not a proven permanent shift identity.",
            "crew_size taken as a single consistent value — never summed across rows.",
        ),
        source_version_ref=None,
    )
