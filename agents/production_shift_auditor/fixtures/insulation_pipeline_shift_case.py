"""Explicit fixture for PSAA S01 — not a live Supabase/Airtable record."""

from __future__ import annotations

from agents.production_shift_auditor.contracts import (
    INPUT_SCHEMA_VERSION,
    DataSourceKind,
    LaborSemanticsStatus,
    LaborUnit,
    OperationLaborClaim,
    PhysicalVolume,
    ShiftAuditInput,
)


def build_insulation_pipeline_fixture() -> ShiftAuditInput:
    ops = (
        OperationLaborClaim("Подготовка поверхности", 30, LaborUnit.MAN_MINUTE),
        OperationLaborClaim("Замеры и разметка", 60, LaborUnit.MAN_MINUTE),
        OperationLaborClaim("Раскрой и устранение деформаций", 75, LaborUnit.MAN_MINUTE),
        OperationLaborClaim("Подготовка клея", 10, LaborUnit.MAN_MINUTE),
        OperationLaborClaim("Монтаж прямых участков", 200, LaborUnit.MAN_MINUTE),
        OperationLaborClaim("Фиксация малярным скотчем", 60, LaborUnit.MAN_MINUTE),
        OperationLaborClaim("Склеивание швов", 60, LaborUnit.MAN_MINUTE),
        OperationLaborClaim(
            "Изготовление фасонных изделий",
            400,
            LaborUnit.MAN_MINUTE,
            physical_quantity=40.0,
            physical_unit="шт",
        ),
        OperationLaborClaim(
            "Монтаж AL CLAD AD",
            200,
            LaborUnit.MAN_MINUTE,
            physical_quantity=6.0,
            physical_unit="м2",
        ),
        OperationLaborClaim("Проклейка теплоизоляционной лентой", 300, LaborUnit.MAN_MINUTE),
        OperationLaborClaim("Уборка рабочего места", 30, LaborUnit.MAN_MINUTE),
    )
    return ShiftAuditInput(
        schema_version=INPUT_SCHEMA_VERSION,
        source_kind=DataSourceKind.FIXTURE,
        project_code="FIXTURE_INSULATION_DEMO",
        work_date="2026-01-01",
        shift_type="DAY",
        crew_id="FIXTURE_CREW_3",
        crew_size=3,
        productive_hours_per_person=8.0,
        operations=ops,
        labor_semantics_status=LaborSemanticsStatus.EXPLICIT_CLAIM,
        labor_semantics_note=(
            "Трудозатраты заданы явно в человеко-минутах во входном кейсе; "
            "это не доказанная запись daily_progress_active."
        ),
        source_record_ids=(),
        physical_volumes=(
            PhysicalVolume(
                "Фасонные изделия",
                40.0,
                "шт",
                linked_operation_name="Изготовление фасонных изделий",
            ),
            PhysicalVolume(
                "Покрытие AL CLAD AD",
                6.0,
                "м2",
                linked_operation_name="Монтаж AL CLAD AD",
            ),
        ),
        construction_discipline="Изоляция трубопроводов",
        provenance_notes=(
            "FIXTURE ONLY — identifiers are synthetic and must not be treated as Airtable IDs.",
        ),
        source_version_ref=None,
    )
