"""Production Shift Auditor Agent (PSAA) — professional package v0.1 (S01 only)."""

from agents.production_shift_auditor.contracts import (
    ShiftAuditArtifact,
    ShiftAuditInput,
)
from agents.production_shift_auditor.s01_mathematical_integrity import evaluate_s01

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"

__all__ = [
    "AGENT_CODE",
    "AGENT_VERSION",
    "ShiftAuditInput",
    "ShiftAuditArtifact",
    "evaluate_s01",
]
