"""Working insulation operation candidates for PSAA S10.

NOT an approved Operation Registry.
NOT an exhaustive technological classification.
Working example for теплоизоляционные работы only.
"""

from __future__ import annotations

from dataclasses import dataclass

INSULATION_CATALOG_VERSION = "psaa.s10.insulation_catalog.v0.1"
RULES_VERSION = "psaa.s10.operation_classification.v0.1"


@dataclass(frozen=True)
class CanonicalOperationCandidate:
    operation_code: str
    canonical_name: str
    work_category: str
    # Exact / near-exact normalized aliases
    aliases: tuple[str, ...]
    # Distinctive tokens that support NORMALIZED_MATCH when co-occurring
    strong_tokens: tuple[str, ...]
    # Optional material / covering hints that bias toward this candidate
    context_tokens: tuple[str, ...] = ()


INSULATION_OPERATION_CANDIDATES: tuple[CanonicalOperationCandidate, ...] = (
    CanonicalOperationCandidate(
        operation_code="INS.SURFACE_PREP",
        canonical_name="Подготовка поверхности",
        work_category="preparation",
        aliases=(
            "подготовка поверхности",
            "очистка поверхности",
            "подготовка труб под изоляцию",
        ),
        strong_tokens=("подготовк", "поверхност", "очистк"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.MARKING",
        canonical_name="Замеры и разметка",
        work_category="preparation",
        aliases=(
            "замеры и разметка",
            "замер и разметка",
            "разметка",
            "разметка труб",
        ),
        strong_tokens=("разметк", "замер"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.CUTTING",
        canonical_name="Раскрой теплоизоляционного материала",
        work_category="fabrication",
        aliases=(
            "раскрой теплоизоляционного материала",
            "раскрой k-flex",
            "раскрой k flex",
            "раскрой каучука",
            "нарезка теплоизоляции",
            "резали каучук",
            "резка каучука",
            "нарезка каучука",
            "раскрой",
        ),
        # NOTE: "раскрой и устранение деформаций" is intentionally NOT an exact alias —
        # it joins cutting with another action and must surface as COMPOSITE_OPERATION.
        strong_tokens=("раскро", "нарезк", "резали", "резк"),
        context_tokens=("каучук", "k-flex", "kflex", "теплоизоляц", "изолятор"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.FITTING_FABRICATION",
        canonical_name="Изготовление фасонных изделий",
        work_category="fabrication",
        aliases=(
            "изготовление фасонных изделий",
            "изготовление фасонки",
            "фасонные изделия",
        ),
        strong_tokens=("изготовлен", "фасон"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.STRAIGHT_INSTALL",
        canonical_name="Монтаж прямых участков теплоизоляции",
        work_category="installation",
        aliases=(
            "монтаж прямых участков теплоизоляции",
            "монтаж прямых участков",
            "монтаж прямой изоляции",
            "монтаж изоляции",
        ),
        # Intentionally NO alias for Airtable/work-type enums like
        # "6.1. Монтаж теплоизоляции трубопроводов (Thermal_Insulation_Piping)" —
        # those are general work labels, not proven specific technological ops.
        strong_tokens=("монтаж", "прям"),
        context_tokens=("изоляц", "труб"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.FITTING_INSTALL",
        canonical_name="Монтаж фасонных изделий",
        work_category="installation",
        aliases=(
            "монтаж фасонных изделий",
            "монтаж фасонки",
            "установка фасонных изделий",
            "монтаж изоляции",
        ),
        strong_tokens=("монтаж", "фасон"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.ADHESIVE_PREP",
        canonical_name="Подготовка клеевого состава",
        work_category="bonding",
        aliases=(
            "подготовка клея",
            "подготовка клеевого состава",
        ),
        strong_tokens=("кле", "клеев", "подготовк"),
        context_tokens=("подготовк",),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.ADHESIVE_APPLY",
        canonical_name="Нанесение клеевого состава",
        work_category="bonding",
        aliases=(
            "нанесение клея",
            "нанесение клеевого состава",
        ),
        strong_tokens=("кле", "клеев", "нанесен"),
        context_tokens=("нанесен",),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.SEAM_BONDING",
        canonical_name="Склеивание швов и стыков",
        work_category="bonding",
        aliases=(
            "склеивание швов и стыков",
            "склеивание швов",
            "склейка швов",
            "склеивание стыков",
        ),
        strong_tokens=("склеив", "склейк", "шов", "стык"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.TAPE",
        canonical_name="Проклейка теплоизоляционной лентой",
        work_category="bonding",
        aliases=(
            "проклейка теплоизоляционной лентой",
            "проклейка лентой",
            "оклейка лентой",
        ),
        strong_tokens=("проклей", "лент"),
        context_tokens=("теплоизоляц",),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.CLADDING",
        canonical_name="Монтаж защитного покровного слоя",
        work_category="cladding",
        aliases=(
            "монтаж защитного покровного слоя",
            "монтаж al clad ad",
            "монтаж alclad",
            "монтаж покрытия al clad ad",
            "монтаж покровного слоя",
        ),
        strong_tokens=("покров", "clad", "alclad", "покрыт"),
        context_tokens=("монтаж", "защитн"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.AUX_TAPE_FIX",
        canonical_name="Вспомогательная фиксация (малярный скотч и аналоги)",
        work_category="auxiliary",
        aliases=(
            "фиксация малярным скотчем",
            "крепление малярным скотчем",
            "малярный скотч",
        ),
        strong_tokens=("скотч", "фиксац"),
        context_tokens=("малярн",),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.AUX_CLEANUP",
        canonical_name="Вспомогательные операции / уборка",
        work_category="auxiliary",
        aliases=(
            "уборка рабочего места",
            "уборка",
            "вспомогательные операции",
        ),
        strong_tokens=("уборк", "вспомогат"),
    ),
    CanonicalOperationCandidate(
        operation_code="INS.QA",
        canonical_name="Контроль качества",
        work_category="quality",
        aliases=(
            "контроль качества",
            "проверка качества изоляции",
            "осмотр изоляции",
        ),
        strong_tokens=("контрол", "качеств", "осмотр"),
    ),
)
