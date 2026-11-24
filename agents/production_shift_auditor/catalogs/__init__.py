"""Versioned working catalogs for PSAA skills. Not an approved Operation Registry."""

from agents.production_shift_auditor.catalogs.insulation_operations_v0_1 import (
    INSULATION_CATALOG_VERSION,
    INSULATION_OPERATION_CANDIDATES,
)

__all__ = [
    "INSULATION_CATALOG_VERSION",
    "INSULATION_OPERATION_CANDIDATES",
]
