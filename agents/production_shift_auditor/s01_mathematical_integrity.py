"""S01 — Mathematical Integrity (deterministic).

Pure functions. No I/O. No LLM. No norms comparison.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from agents.production_shift_auditor.contracts import (
    ARTIFACT_SCHEMA_VERSION,
    RULES_VERSION,
    DataCompletenessStatus,
    LaborSemanticsStatus,
    LaborUnit,
    ManagerialAcceptanceStatus,
    MathIntegrityStatus,
    OperationAuditLine,
    ProfessionalCredibilityStatus,
    S01Metrics,
    ShiftAuditArtifact,
    ShiftAuditInput,
)

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"


def _to_man_minutes(quantity: float, unit: LaborUnit) -> Optional[float]:
    if unit == LaborUnit.MAN_MINUTE:
        return float(quantity)
    if unit == LaborUnit.MAN_HOUR:
        return float(quantity) * 60.0
    # HOUR_FIELD_UNPROVEN — do not silently treat as man-hours
    return None


def _is_multiple(value: float, step: float, *, tol: float = 1e-9) -> bool:
    if value < 0:
        return False
    q = value / step
    return abs(q - round(q)) <= tol


def evaluate_s01(
    audit_input: ShiftAuditInput,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    top_n: int = 3,
) -> ShiftAuditArtifact:
    missing: list[str] = []
    observations: list[str] = []
    questions: list[str] = []
    hypotheses: list[str] = []

    if audit_input.crew_size <= 0:
        missing.append("crew_size must be > 0")
    if audit_input.productive_hours_per_person <= 0:
        missing.append("productive_hours_per_person must be > 0")
    if not audit_input.operations:
        missing.append("operations list is empty")

    if audit_input.labor_semantics_status == LaborSemanticsStatus.UNPROVEN:
        hypotheses.append(
            "Семантика трудозатрат не доказана: показатели S01 ограничены или "
            "не вычисляются до явного labor_unit."
        )

    # Target productive fund (not timesheet fund, not violation proof)
    target_mm: Optional[float] = None
    target_mh: Optional[float] = None
    if audit_input.crew_size > 0 and audit_input.productive_hours_per_person > 0:
        target_mh = float(audit_input.crew_size) * float(
            audit_input.productive_hours_per_person
        )
        target_mm = target_mh * 60.0
        observations.append(
            "Целевой производительный фонд = crew_size × productive_hours_per_person; "
            "это не табельный фонд и не автоматическое доказательство нарушения."
        )

    # Convert each operation; refuse silent conversion for UNPROVEN hour field
    op_lines: list[OperationAuditLine] = []
    claimed_mm_values: list[tuple[str, float]] = []
    multiples_5 = 0
    multiples_10 = 0
    convertible_ops = 0
    conversion_blocked = 0

    for op in audit_input.operations:
        mm = _to_man_minutes(op.claimed_labor_quantity, op.labor_unit)
        mh: Optional[float] = None
        mult5: Optional[bool] = None
        mult10: Optional[bool] = None
        unit_mm: Optional[float] = None
        unit_mh: Optional[float] = None
        has_phys = op.physical_quantity is not None and op.physical_unit is not None

        if mm is None:
            conversion_blocked += 1
            observations.append(
                f"Операция «{op.operation_name}»: labor_unit={op.labor_unit.value} "
                "не конвертируется в чел·мин без доказанной семантики."
            )
        else:
            convertible_ops += 1
            mh = mm / 60.0
            claimed_mm_values.append((op.operation_name, mm))
            mult5 = _is_multiple(mm, 5.0)
            mult10 = _is_multiple(mm, 10.0)
            if mult5:
                multiples_5 += 1
            if mult10:
                multiples_10 += 1
            if has_phys and op.physical_quantity and op.physical_quantity > 0:
                unit_mm = mm / float(op.physical_quantity)
                unit_mh = unit_mm / 60.0

        share: Optional[float] = None
        if mm is not None and target_mm and target_mm > 0:
            share = (mm / target_mm) * 100.0

        # Prefer linked volumes from input.physical_volumes if op fields empty
        phys_q = op.physical_quantity
        phys_u = op.physical_unit
        if not has_phys:
            for vol in audit_input.physical_volumes:
                if vol.linked_operation_name == op.operation_name:
                    phys_q = vol.quantity
                    phys_u = vol.unit
                    has_phys = True
                    if mm is not None and phys_q and phys_q > 0:
                        unit_mm = mm / float(phys_q)
                        unit_mh = unit_mm / 60.0
                    break

        if not has_phys:
            observations.append(
                f"Операция «{op.operation_name}»: физический объём не указан "
                "(наблюдение, не нарушение)."
            )

        op_lines.append(
            OperationAuditLine(
                operation_name=op.operation_name,
                claimed_labor_man_minutes=mm,
                claimed_labor_man_hours=mh,
                share_of_target_fund_pct=share,
                physical_quantity=phys_q,
                physical_unit=phys_u,
                has_physical_volume=has_phys,
                unit_labor_man_minutes_per_physical=unit_mm,
                unit_labor_man_hours_per_physical=unit_mh,
                multiple_of_5_minutes=mult5,
                multiple_of_10_minutes=mult10,
                source_record_ids=op.source_record_ids,
            )
        )

    claimed_total_mm: Optional[float] = None
    claimed_total_mh: Optional[float] = None
    if convertible_ops == len(audit_input.operations) and claimed_mm_values:
        claimed_total_mm = sum(v for _, v in claimed_mm_values)
        claimed_total_mh = claimed_total_mm / 60.0
    elif claimed_mm_values and conversion_blocked:
        missing.append(
            "Не все операции имеют доказанную единицу трудозатрат; "
            "полная сумма заявленных трудозатрат не сформирована."
        )
    elif not claimed_mm_values:
        missing.append("Нет конвертируемых заявленных трудозатрат для S01.")

    abs_dev_mm: Optional[float] = None
    abs_dev_mh: Optional[float] = None
    coverage: Optional[float] = None
    if claimed_total_mm is not None and target_mm is not None:
        abs_dev_mm = target_mm - claimed_total_mm
        abs_dev_mh = abs_dev_mm / 60.0
        coverage = (claimed_total_mm / target_mm) * 100.0 if target_mm else None

    # Top-N concentration vs TARGET fund (not vs claimed total)
    top3_mm: Optional[float] = None
    top3_pct: Optional[float] = None
    top3_names: tuple[str, ...] = ()
    if claimed_mm_values and target_mm and target_mm > 0:
        ranked = sorted(claimed_mm_values, key=lambda x: x[1], reverse=True)
        top = ranked[: max(1, top_n)]
        top3_names = tuple(n for n, _ in top)
        top3_mm = sum(v for _, v in top)
        top3_pct = (top3_mm / target_mm) * 100.0
        observations.append(
            f"Концентрация top-{len(top)} операций считается относительно "
            "целевого фонда, не относительно суммы заявленного. "
            "Это диагностический показатель, не доказательство нарушения."
        )

    if convertible_ops:
        observations.append(
            f"Кратность 5 мин: {multiples_5}/{convertible_ops}; "
            f"кратность 10 мин: {multiples_10}/{convertible_ops}. "
            "Округление времени — наблюдение, не доказательство нарушения."
        )

    if audit_input.labor_semantics_status == LaborSemanticsStatus.PARTIALLY_PROVEN:
        hypotheses.append(audit_input.labor_semantics_note)
        questions.append(
            "Подтвердите, что поле Direct_Work_Hours / заявленные часы означают "
            "суммарные человеко-часы звена, а не продолжительность смены и не "
            "иную категорию времени."
        )

    # Statuses — kept separate
    if missing and (claimed_total_mm is None or target_mm is None):
        math_status = MathIntegrityStatus.DATA_INCOMPLETE
        completeness = (
            DataCompletenessStatus.INSUFFICIENT
            if claimed_total_mm is None or target_mm is None
            else DataCompletenessStatus.PARTIAL
        )
    elif claimed_total_mm is not None and target_mm is not None:
        # Arithmetic integrity: totals compute and are finite; deviation is informational
        math_status = MathIntegrityStatus.COHERENT
        completeness = (
            DataCompletenessStatus.COMPLETE_FOR_S01
            if conversion_blocked == 0 and audit_input.crew_size > 0
            else DataCompletenessStatus.PARTIAL
        )
        if abs_dev_mm is not None and abs(abs_dev_mm) > 1e-9:
            # Signed: target − claimed. Negative ⇒ overfund; positive ⇒ underfund.
            if abs_dev_mm < 0:
                over_mm = -abs_dev_mm
                observations.append(
                    f"Превышение целевого производительного фонда: {over_mm:.4g} чел·мин "
                    f"({over_mm / 60.0:.4g} чел·ч); направление=OVER_FUND; "
                    f"signed_deviation(target−claimed)={abs_dev_mm:.4g} чел·мин. "
                    "COHERENT означает арифметическую согласованность входа, "
                    "а не отсутствие отклонений. Превышение фонда — диагностическое "
                    "наблюдение, не доказательство нарушения или недостоверности. "
                    "Целевой производительный фонд ≠ табельное / фактически доступное "
                    "рабочее время."
                )
            else:
                observations.append(
                    f"Недобор относительно целевого производительного фонда: "
                    f"{abs_dev_mm:.4g} чел·мин ({abs_dev_mh:.4g} чел·ч); "
                    f"направление=UNDER_FUND; "
                    f"signed_deviation(target−claimed)={abs_dev_mm:.4g} чел·мин. "
                    "COHERENT означает арифметическую согласованность входа, "
                    "а не отсутствие отклонений. Недобор — диагностическое наблюдение, "
                    "не доказательство нарушения. Целевой производительный фонд ≠ "
                    "табельное / фактически доступное рабочее время."
                )
    else:
        math_status = MathIntegrityStatus.NOT_EVALUATED
        completeness = DataCompletenessStatus.INSUFFICIENT

    metrics = S01Metrics(
        target_fund_man_minutes=target_mm,
        target_fund_man_hours=target_mh,
        claimed_total_man_minutes=claimed_total_mm,
        claimed_total_man_hours=claimed_total_mh,
        absolute_deviation_man_minutes=abs_dev_mm,
        absolute_deviation_man_hours=abs_dev_mh,
        fund_coverage_pct=coverage,
        operations_count=len(audit_input.operations),
        multiples_of_5_minutes_count=multiples_5 if convertible_ops else None,
        multiples_of_10_minutes_count=multiples_10 if convertible_ops else None,
        top3_operations_man_minutes=top3_mm,
        top3_concentration_of_target_fund_pct=top3_pct,
        top3_operation_names=top3_names,
    )

    conclusion = _human_conclusion(
        audit_input,
        metrics,
        math_status,
        completeness,
    )

    return ShiftAuditArtifact(
        schema_version=ARTIFACT_SCHEMA_VERSION,
        rules_version=RULES_VERSION,
        audit_id=audit_id or str(uuid.uuid4()),
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        input_provenance={
            "source_kind": audit_input.source_kind.value,
            "project_code": audit_input.project_code,
            "work_date": audit_input.work_date,
            "shift_type": audit_input.shift_type,
            "crew_id": audit_input.crew_id,
            "source_record_ids": list(audit_input.source_record_ids),
            "source_version_ref": audit_input.source_version_ref,
            "labor_semantics_status": audit_input.labor_semantics_status.value,
            "labor_semantics_note": audit_input.labor_semantics_note,
            "provenance_notes": list(audit_input.provenance_notes),
            "input_schema_version": audit_input.schema_version,
        },
        s01_metrics=metrics,
        operations=tuple(op_lines),
        observations=tuple(observations),
        missing_data=tuple(missing),
        clarification_questions=tuple(questions),
        hypotheses_unproven=tuple(hypotheses),
        math_integrity_status=math_status,
        data_completeness_status=completeness,
        professional_credibility_status=ProfessionalCredibilityStatus.NOT_EVALUATED,
        managerial_acceptance_status=ManagerialAcceptanceStatus.NOT_IN_SCOPE,
        human_readable_conclusion=conclusion,
    )


def _human_conclusion(
    audit_input: ShiftAuditInput,
    metrics: S01Metrics,
    math_status: MathIntegrityStatus,
    completeness: DataCompletenessStatus,
) -> str:
    lines = [
        "PSAA S01 — Mathematical Integrity",
        f"Проект: {audit_input.project_code}",
        f"Смена: date={audit_input.work_date} shift_type={audit_input.shift_type} "
        f"crew_id={audit_input.crew_id} crew_size={audit_input.crew_size}",
        f"Math integrity: {math_status.value}",
        f"Data completeness: {completeness.value}",
        "Professional credibility: NOT_EVALUATED (S01 only)",
        "Managerial acceptance: NOT_IN_SCOPE",
    ]
    if metrics.target_fund_man_minutes is not None:
        lines.append(
            f"Целевой производительный фонд: {metrics.target_fund_man_minutes:.4g} чел·мин "
            f"({metrics.target_fund_man_hours:.4g} чел·ч)"
        )
    if metrics.claimed_total_man_minutes is not None:
        lines.append(
            f"Заявлено: {metrics.claimed_total_man_minutes:.4g} чел·мин "
            f"({metrics.claimed_total_man_hours:.4g} чел·ч)"
        )
    if metrics.absolute_deviation_man_minutes is not None:
        signed = metrics.absolute_deviation_man_minutes
        if signed < 0:
            lines.append(
                f"Превышение целевого фонда: {-signed:.4g} чел·мин "
                f"(signed_deviation={signed:.4g}; OVER_FUND)"
            )
        elif signed > 0:
            lines.append(
                f"Недобор относительно целевого фонда: {signed:.4g} чел·мин "
                f"(signed_deviation={signed:.4g}; UNDER_FUND)"
            )
        else:
            lines.append("Отклонение от целевого фонда: 0 чел·мин")
        lines.append(
            "COHERENT = арифметическая согласованность; не означает отсутствие отклонений."
        )
    if metrics.fund_coverage_pct is not None:
        lines.append(f"Покрытие фонда: {metrics.fund_coverage_pct:.4f}%")
    if metrics.top3_operation_names:
        lines.append(
            "Top операции: "
            + ", ".join(metrics.top3_operation_names)
            + f" = {metrics.top3_operations_man_minutes:.4g} чел·мин "
            f"({metrics.top3_concentration_of_target_fund_pct:.4g}% целевого фонда)"
        )
    if metrics.multiples_of_5_minutes_count is not None:
        lines.append(
            f"Кратность 5 мин: {metrics.multiples_of_5_minutes_count}/"
            f"{metrics.operations_count}; кратность 10 мин: "
            f"{metrics.multiples_of_10_minutes_count}/{metrics.operations_count}"
        )
    lines.append(
        "Заключение S01 не является приёмкой или отклонением смены и не подтверждает "
        "технологическую/физическую достоверность."
    )
    return "\n".join(lines)
