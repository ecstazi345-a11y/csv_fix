"""
Constructor Runtime v0.1 Increment 5 — Exception Engine capability.

Deterministic service inside Constructor Agent. Not a professional agent.
Maps known Constructor failure/outcome semantics to immutable exception artifacts.

Does not weaken Increments 1–4 fail-closed behavior.
Does not call mission scope, secure read, package builder, or labor resolver.
Does not implement lifecycle, HITL, LangGraph, Streamlit, LLM, SQL, or writes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, Union

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_NOT_AVAILABLE,
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    PackageExceptionSummary,
)
from agents.monthly_plan_constructor.labor_norm_resolver import LaborNormResolutionSet

SCHEMA_VERSION = "1.0"

# --- Active taxonomy (Increment 1–4 only) ---
CODE_DATA_CONTRACT_BLOCKER = "DATA_CONTRACT_BLOCKER"
CODE_AMBIGUOUS_SCOPE = "AMBIGUOUS_SCOPE"
CODE_SECURITY_DENIED = "SECURITY_DENIED"
CODE_READ_FAILED = "READ_FAILED"
CODE_LABOR_NORM_UNRESOLVED = "LABOR_NORM_UNRESOLVED"

ACTIVE_EXCEPTION_CODES = frozenset(
    {
        CODE_DATA_CONTRACT_BLOCKER,
        CODE_AMBIGUOUS_SCOPE,
        CODE_SECURITY_DENIED,
        CODE_READ_FAILED,
        CODE_LABOR_NORM_UNRESOLVED,
    }
)

# Lower-level secure-read / executor codes → SECURITY_DENIED
_SECURITY_ALIAS_CODES = frozenset(
    {
        "TOOL_NOT_ALLOWED",
        "CONTEXT_EXPIRED",
        "CONTEXT_MISSING",
        CODE_SECURITY_DENIED,
    }
)

SEVERITY_BLOCKING = "BLOCKING"
SEVERITY_NON_BLOCKING = "NON_BLOCKING"
SEVERITY_WARNING = "WARNING"
SEVERITIES = frozenset(
    {SEVERITY_BLOCKING, SEVERITY_NON_BLOCKING, SEVERITY_WARNING}
)

ROUTE_FAIL_RUN = "FAIL_RUN"
ROUTE_WAIT_HUMAN = "WAIT_HUMAN"
ROUTE_WAIT_FRESH_REALITY = "WAIT_FRESH_REALITY"
ROUTE_CONTINUE = "CONTINUE"
ROUTES = frozenset(
    {
        ROUTE_FAIL_RUN,
        ROUTE_WAIT_HUMAN,
        ROUTE_WAIT_FRESH_REALITY,
        ROUTE_CONTINUE,
    }
)

SOURCE_MISSION_SCOPE = "MISSION_SCOPE"
SOURCE_CANDIDATE_PACKAGE = "CANDIDATE_PACKAGE"
SOURCE_SECURE_READ = "SECURE_READ"
SOURCE_LABOR_NORM = "LABOR_NORM"
SOURCE_CAPABILITIES = frozenset(
    {
        SOURCE_MISSION_SCOPE,
        SOURCE_CANDIDATE_PACKAGE,
        SOURCE_SECURE_READ,
        SOURCE_LABOR_NORM,
    }
)

CODE_ENGINE_CONTRACT_BLOCKER = "EXCEPTION_ENGINE_CONTRACT_BLOCKER"


class ExceptionEngineError(ValueError):
    """Fail-closed Exception Engine contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ConstructorExceptionDetails:
    """Bounded, JSON-safe data-only provenance. Not instructions."""

    original_failure_code: Optional[str] = None
    rejection_codes: tuple[str, ...] = ()
    ambiguity_evidence_ids: tuple[str, ...] = ()
    resolution_reason: Optional[str] = None
    resolution_status: Optional[str] = None


@dataclass(frozen=True)
class ConstructorException:
    exception_id: str
    schema_version: str
    exception_code: str
    severity: str
    route: str
    reason: str
    source_capability: str
    observed_at: datetime
    package_id: Optional[str] = None
    candidate_id: Optional[str] = None
    resolution_id: Optional[str] = None
    details: ConstructorExceptionDetails = field(
        default_factory=ConstructorExceptionDetails
    )

    @property
    def requires_human(self) -> bool:
        return self.route == ROUTE_WAIT_HUMAN

    @property
    def requires_fresh_reality(self) -> bool:
        return self.route == ROUTE_WAIT_FRESH_REALITY

    @property
    def automatic_continuation_allowed(self) -> bool:
        return (
            self.severity != SEVERITY_BLOCKING and self.route == ROUTE_CONTINUE
        )


@dataclass(frozen=True)
class ConstructorExceptionSet:
    schema_version: str
    exceptions: tuple[ConstructorException, ...]
    summary: PackageExceptionSummary
    package_id: Optional[str] = None

    def codes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.exception_code for item in self.exceptions))

    def blocking(self) -> tuple[ConstructorException, ...]:
        return tuple(
            item
            for item in self.exceptions
            if item.severity == SEVERITY_BLOCKING
        )

    def handoff_allowed(self) -> bool:
        return not any(
            item.severity == SEVERITY_BLOCKING for item in self.exceptions
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            f"{field_name} must be datetime",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            f"{field_name} must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc)


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _require_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    return text


def _require_source(value: Any) -> str:
    source = _require_text(value, "source_capability").upper()
    if source not in SOURCE_CAPABILITIES:
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            f"unknown source_capability {source}",
        )
    return source


def _normalize_details(
    details: Optional[Union[ConstructorExceptionDetails, Mapping[str, Any]]],
) -> ConstructorExceptionDetails:
    if details is None:
        return ConstructorExceptionDetails()
    if isinstance(details, ConstructorExceptionDetails):
        return details
    if not isinstance(details, Mapping):
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            "details must be ConstructorExceptionDetails or mapping",
        )
    rejection = details.get("rejection_codes") or ()
    ambiguity = details.get("ambiguity_evidence_ids") or ()
    if isinstance(rejection, str) or isinstance(ambiguity, str):
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            "rejection_codes and ambiguity_evidence_ids must be sequences",
        )
    return ConstructorExceptionDetails(
        original_failure_code=_optional_text(details.get("original_failure_code")),
        rejection_codes=tuple(str(item) for item in rejection),
        ambiguity_evidence_ids=tuple(str(item) for item in ambiguity),
        resolution_reason=_optional_text(details.get("resolution_reason")),
        resolution_status=_optional_text(details.get("resolution_status")),
    )


def _default_policy(canonical_code: str) -> tuple[str, str]:
    if canonical_code == CODE_DATA_CONTRACT_BLOCKER:
        return SEVERITY_BLOCKING, ROUTE_FAIL_RUN
    if canonical_code == CODE_AMBIGUOUS_SCOPE:
        return SEVERITY_BLOCKING, ROUTE_WAIT_HUMAN
    if canonical_code == CODE_SECURITY_DENIED:
        return SEVERITY_BLOCKING, ROUTE_FAIL_RUN
    if canonical_code == CODE_READ_FAILED:
        return SEVERITY_BLOCKING, ROUTE_FAIL_RUN
    if canonical_code == CODE_LABOR_NORM_UNRESOLVED:
        return SEVERITY_NON_BLOCKING, ROUTE_CONTINUE
    raise ExceptionEngineError(
        CODE_ENGINE_CONTRACT_BLOCKER,
        f"no default policy for {canonical_code}",
    )


def _canonicalize_failure_code(raw_code: str) -> tuple[str, Optional[str]]:
    """Return (canonical_exception_code, original_lower_level_or_None)."""
    code = raw_code.strip().upper()
    if code in _SECURITY_ALIAS_CODES:
        original = None if code == CODE_SECURITY_DENIED else code
        return CODE_SECURITY_DENIED, original
    if code in ACTIVE_EXCEPTION_CODES:
        return code, None
    raise ExceptionEngineError(
        CODE_ENGINE_CONTRACT_BLOCKER,
        f"unknown or unapproved failure code {raw_code!r}",
    )


def _dedup_key(item: ConstructorException) -> tuple[Any, ...]:
    return (
        item.exception_code,
        item.source_capability,
        item.package_id or "",
        item.candidate_id or "",
        item.resolution_id or "",
        item.details.original_failure_code or "",
    )


def _summarize(exceptions: Sequence[ConstructorException]) -> PackageExceptionSummary:
    blocking = 0
    non_blocking = 0
    warning = 0
    for item in exceptions:
        if item.severity == SEVERITY_BLOCKING:
            blocking += 1
        elif item.severity == SEVERITY_NON_BLOCKING:
            non_blocking += 1
        elif item.severity == SEVERITY_WARNING:
            warning += 1
        else:
            raise ExceptionEngineError(
                CODE_ENGINE_CONTRACT_BLOCKER,
                f"unknown severity {item.severity}",
            )
    return PackageExceptionSummary(
        blocking_count=blocking,
        non_blocking_count=non_blocking,
        warning_count=warning,
    )


def build_constructor_exception(
    *,
    exception_code: str,
    reason: str,
    source_capability: str,
    severity: Optional[str] = None,
    route: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    package_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    resolution_id: Optional[str] = None,
    details: Optional[Union[ConstructorExceptionDetails, Mapping[str, Any]]] = None,
    exception_id: Optional[str] = None,
) -> ConstructorException:
    """Build one immutable ConstructorException. Fail closed on contract errors."""
    canonical, _ = _canonicalize_failure_code(_require_text(exception_code, "exception_code"))
    # LABOR and active codes that are already canonical: canonicalize may pass through.
    # For SECURITY aliases callers should use exception_from_failure.
    if exception_code.strip().upper() in _SECURITY_ALIAS_CODES and exception_code.strip().upper() != CODE_SECURITY_DENIED:
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            "use exception_from_failure for security alias codes",
        )

    default_severity, default_route = _default_policy(canonical)
    sev = (severity or default_severity).strip().upper()
    rte = (route or default_route).strip().upper()
    if sev not in SEVERITIES:
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            f"unknown severity {sev}",
        )
    if rte not in ROUTES:
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            f"unknown route {rte}",
        )

    # Security may never downgrade.
    if canonical == CODE_SECURITY_DENIED:
        if sev != SEVERITY_BLOCKING or rte != ROUTE_FAIL_RUN:
            raise ExceptionEngineError(
                CODE_ENGINE_CONTRACT_BLOCKER,
                "SECURITY_DENIED must remain BLOCKING + FAIL_RUN",
            )

    stamp = _require_aware_utc(observed_at or _utc_now(), "observed_at")
    normalized = _normalize_details(details)
    return ConstructorException(
        exception_id=_optional_text(exception_id) or str(uuid.uuid4()),
        schema_version=SCHEMA_VERSION,
        exception_code=canonical,
        severity=sev,
        route=rte,
        reason=_require_text(reason, "reason"),
        source_capability=_require_source(source_capability),
        observed_at=stamp,
        package_id=_optional_text(package_id),
        candidate_id=_optional_text(candidate_id),
        resolution_id=_optional_text(resolution_id),
        details=normalized,
    )


def exception_from_failure(
    failure_code: str,
    *,
    source_capability: str,
    reason: str,
    package_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    resolution_id: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    details: Optional[Union[ConstructorExceptionDetails, Mapping[str, Any]]] = None,
) -> ConstructorException:
    """
    Pure mapper: known machine-readable failure code → ConstructorException.

    Does not execute Constructor capabilities. Unknown codes fail closed.
    """
    canonical, original = _canonicalize_failure_code(
        _require_text(failure_code, "failure_code")
    )
    severity, route = _default_policy(canonical)
    merged = _normalize_details(details)
    if original is not None:
        merged = ConstructorExceptionDetails(
            original_failure_code=original,
            rejection_codes=merged.rejection_codes,
            ambiguity_evidence_ids=merged.ambiguity_evidence_ids,
            resolution_reason=merged.resolution_reason,
            resolution_status=merged.resolution_status,
        )
    elif merged.original_failure_code is None and failure_code.strip().upper() != canonical:
        merged = ConstructorExceptionDetails(
            original_failure_code=failure_code.strip().upper(),
            rejection_codes=merged.rejection_codes,
            ambiguity_evidence_ids=merged.ambiguity_evidence_ids,
            resolution_reason=merged.resolution_reason,
            resolution_status=merged.resolution_status,
        )

    return build_constructor_exception(
        exception_code=canonical,
        reason=reason,
        source_capability=source_capability,
        severity=severity,
        route=route,
        observed_at=observed_at,
        package_id=package_id,
        candidate_id=candidate_id,
        resolution_id=resolution_id,
        details=merged,
    )


def build_exception_set(
    exceptions: Sequence[ConstructorException],
    *,
    package_id: Optional[str] = None,
) -> ConstructorExceptionSet:
    """Immutable set with semantic deduplication. First occurrence wins."""
    if exceptions is None or isinstance(exceptions, (str, bytes)):
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            "exceptions must be a sequence of ConstructorException",
        )

    ordered: list[ConstructorException] = []
    seen: set[tuple[Any, ...]] = set()
    for item in exceptions:
        if not isinstance(item, ConstructorException):
            raise ExceptionEngineError(
                CODE_ENGINE_CONTRACT_BLOCKER,
                "exceptions items must be ConstructorException",
            )
        key = _dedup_key(item)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)

    pkg = _optional_text(package_id)
    if pkg is None:
        for item in ordered:
            if item.package_id:
                pkg = item.package_id
                break

    frozen = tuple(ordered)
    return ConstructorExceptionSet(
        schema_version=SCHEMA_VERSION,
        exceptions=frozen,
        summary=_summarize(frozen),
        package_id=pkg,
    )


def exceptions_from_labor_resolutions(
    resolution_set: LaborNormResolutionSet,
    *,
    observed_at: Optional[datetime] = None,
) -> ConstructorExceptionSet:
    """
    Emit LABOR_NORM_UNRESOLVED for unresolved resolutions only.

    VALIDATED / PROVISIONAL → no exception.
    Does not recompute norms. Does not mutate package or candidates.
    """
    if not isinstance(resolution_set, LaborNormResolutionSet):
        raise ExceptionEngineError(
            CODE_ENGINE_CONTRACT_BLOCKER,
            "resolution_set must be LaborNormResolutionSet",
        )

    stamp = _require_aware_utc(observed_at or _utc_now(), "observed_at")
    package_id = resolution_set.package_id
    built: list[ConstructorException] = []

    for resolution in resolution_set.resolutions:
        status = str(resolution.status or "").strip().upper()
        if status in {LABOR_VALIDATED, LABOR_PROVISIONAL}:
            continue
        if status not in {LABOR_UNRESOLVED, LABOR_NOT_AVAILABLE}:
            raise ExceptionEngineError(
                CODE_ENGINE_CONTRACT_BLOCKER,
                f"unsupported labor resolution status {status!r}",
            )

        reason = resolution.resolution_reason or "labor norm unresolved"
        built.append(
            build_constructor_exception(
                exception_code=CODE_LABOR_NORM_UNRESOLVED,
                reason=reason,
                source_capability=SOURCE_LABOR_NORM,
                severity=SEVERITY_NON_BLOCKING,
                route=ROUTE_CONTINUE,
                observed_at=stamp,
                package_id=package_id,
                candidate_id=resolution.candidate_id,
                resolution_id=resolution.resolution_id,
                details=ConstructorExceptionDetails(
                    rejection_codes=tuple(resolution.rejection_codes),
                    ambiguity_evidence_ids=tuple(resolution.ambiguity_evidence_ids),
                    resolution_reason=_optional_text(resolution.resolution_reason),
                    resolution_status=status,
                ),
            )
        )

    return build_exception_set(built, package_id=package_id)
