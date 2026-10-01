"""
LND-R1 — Labor Norm Decision durable human register.

Table: public.labor_norm_decisions
RPC:   apply_labor_norm_decision / cancel_labor_norm_decision

Historical P50/P80 are UI hints only. This module never emits VALIDATED.
Does not wire Constructor / LaborNormResolver / Daily Progress.

Security (R1):
- labor_norm_decisions reads + apply/cancel RPCs require SUPABASE_SECRET_KEY
  (service_role). Never fall back to the anon client.
- approved_by is a required operator label, NOT cryptographic identity.
  Cryptographic user identification is not implemented in R1.
"""

from __future__ import annotations

import math
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from services.supabase_client import supabase

TABLE = "labor_norm_decisions"
RPC_APPLY = "apply_labor_norm_decision"
RPC_CANCEL = "cancel_labor_norm_decision"
SCOPE_VIEW = "monthly_scope_picker_view"
NORMS_VIEW = "boq_productivity_norms_v2"

DECISION_APPROVED_PROVISIONAL = "APPROVED_PROVISIONAL"
DECISION_MANUAL_PROVISIONAL = "MANUAL_PROVISIONAL"
DECISION_REJECTED = "REJECTED"

DECISION_CODES = frozenset(
    {
        DECISION_APPROVED_PROVISIONAL,
        DECISION_MANUAL_PROVISIONAL,
        DECISION_REJECTED,
    }
)

# Explicitly forbidden — never accepted from UI/service.
FORBIDDEN_DECISION_CODES = frozenset(
    {
        "VALIDATED",
        "PROVISIONAL",
        "UNRESOLVED",
        "APPROVED_VALIDATED",
        "COMPANY_NORM",
        "OFFICIAL_NORMATIVE",
    }
)

STATUS_ACTIVE = "ACTIVE"
STATUS_CANCELLED = "CANCELLED"

SOURCE_PAGE_DEFAULT = "PAGE_13_LABOR_NORM_DECISION"
SUGGESTED_SOURCE_HISTORICAL_P50 = "HISTORICAL_P50_HINT"

DECISION_RU = {
    DECISION_APPROVED_PROVISIONAL: "Принять как временную норму",
    DECISION_MANUAL_PROVISIONAL: "Задать временную норму вручную",
    DECISION_REJECTED: "Отклонить",
}

DECISION_RU_TO_EN = {v: k for k, v in DECISION_RU.items()}

HINT_WARNING_RU = (
    "Историческая статистика является подсказкой и не является "
    "подтверждённой производственной нормой."
)

HINT_UNAVAILABLE_WARNING_RU = (
    "Историческая статистика временно недоступна.\n"
    "Решение можно принять вручную.\n"
    "Автоматическая историческая норма не используется."
)

HINT_NOT_LOADED_RU = (
    "Историческая подсказка не загружена.\n"
    "Можно принять ручное временное решение."
)

APPROVED_BY_OPERATOR_LABEL_NOTE = (
    "ФИО/идентификатор утверждающего является операторской меткой. "
    "Криптографическая идентификация пользователя в R1 не реализована."
)

SERVICE_ROLE_MISSING_MSG = (
    "SUPABASE_SECRET_KEY не задан — доступ к labor_norm_decisions "
    "через anon запрещён (fail-closed)."
)


def decision_codes_for_hint_availability(hints_available: bool) -> tuple[str, ...]:
    """
    Page13 decision menu.
    When historical hints are unavailable, APPROVED_PROVISIONAL (accept P50)
    must not be offered — only MANUAL_PROVISIONAL and REJECTED.
    """
    if hints_available:
        return (
            DECISION_APPROVED_PROVISIONAL,
            DECISION_MANUAL_PROVISIONAL,
            DECISION_REJECTED,
        )
    return (DECISION_MANUAL_PROVISIONAL, DECISION_REJECTED)


def decision_labels_for_hint_availability(hints_available: bool) -> list[str]:
    return [DECISION_RU[code] for code in decision_codes_for_hint_availability(hints_available)]


def page13_remote_plan(
    *,
    load_hints_clicked: bool,
    load_history_clicked: bool,
    load_active_clicked: bool = False,
) -> dict[str, bool]:
    """
    Explicit remote-work plan for Page13.

    Initial / normal widget reruns pass all False → no optional network I/O.
    """
    return {
        "fetch_hints": bool(load_hints_clicked),
        "fetch_history": bool(load_history_clicked),
        "fetch_active": bool(load_active_clicked),
    }


SELECT_COLS = (
    "decision_id,project_code,facility_building,construction_discipline,"
    "boq_code,boq_name,unit_of_measure,"
    "suggested_norm,suggested_source,sample_count,confidence,"
    "decision,decision_status,approved_norm,comment,source_reference,"
    "approved_by,approved_at,updated_by,updated_at,"
    "cancelled_by,cancelled_at,source_page,created_at"
)


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "nat", "<na>"}:
        return ""
    return text


def normalize_boq(value: Any) -> str:
    return safe_text(value).upper()


def normalize_unit(value: Any) -> str:
    return safe_text(value)


def units_compatible(left: Any, right: Any) -> bool:
    a = normalize_unit(left)
    b = normalize_unit(right)
    if not a or not b:
        return False
    return a.casefold() == b.casefold()


def optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and not safe_text(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def optional_int(value: Any) -> Optional[int]:
    number = optional_float(value)
    if number is None:
        return None
    return int(number)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_decision_code(decision: Any) -> str:
    raw = safe_text(decision)
    if not raw:
        return ""
    upper = raw.upper()
    if upper in FORBIDDEN_DECISION_CODES:
        return ""
    if upper in DECISION_CODES:
        return upper
    return DECISION_RU_TO_EN.get(raw, "")


def decision_to_ru(decision: Any) -> str:
    code = normalize_decision_code(decision)
    return DECISION_RU.get(code, safe_text(decision))


def _result_ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _result_err(error: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": error}


@dataclass(frozen=True)
class LaborNormDecisionRecord:
    decision_id: str
    project_code: str
    facility_building: str
    construction_discipline: str
    boq_code: str
    unit_of_measure: str
    decision: str
    decision_status: str
    approved_by: str
    approved_at: str
    boq_name: str = ""
    suggested_norm: Optional[float] = None
    suggested_source: str = ""
    sample_count: Optional[int] = None
    confidence: str = ""
    approved_norm: Optional[float] = None
    comment: str = ""
    source_reference: str = ""
    updated_by: str = ""
    updated_at: str = ""
    cancelled_by: str = ""
    cancelled_at: str = ""
    source_page: str = SOURCE_PAGE_DEFAULT
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LaborNormDecisionDraft:
    project_code: str
    facility_building: str
    construction_discipline: str
    boq_code: str
    unit_of_measure: str
    decision: str
    approved_by: str
    comment: str
    approved_norm: Optional[float] = None
    boq_name: str = ""
    suggested_norm: Optional[float] = None
    suggested_source: str = ""
    sample_count: Optional[int] = None
    confidence: str = ""
    source_reference: str = ""
    expected_unit: str = ""
    source_page: str = SOURCE_PAGE_DEFAULT


def validate_decision_draft(draft: LaborNormDecisionDraft) -> tuple[Optional[str], Optional[LaborNormDecisionDraft]]:
    """
    Fail-closed validation. Returns (error, normalized_draft).
    Never accepts VALIDATED or unknown codes.
    """
    project = safe_text(draft.project_code)
    facility = safe_text(draft.facility_building)
    discipline = safe_text(draft.construction_discipline)
    boq = normalize_boq(draft.boq_code)
    unit = normalize_unit(draft.unit_of_measure)
    actor = safe_text(draft.approved_by)
    comment = safe_text(draft.comment)
    code = normalize_decision_code(draft.decision)

    raw_decision = safe_text(draft.decision).upper()
    if raw_decision in FORBIDDEN_DECISION_CODES or "VALIDATED" in raw_decision:
        return "Код VALIDATED / недопустимое решение запрещены для этого реестра", None
    if not project:
        return "Укажите project_code", None
    if not facility:
        return "Укажите facility_building (титул/объект)", None
    if not discipline:
        return "Укажите construction_discipline", None
    if not boq:
        return "Укажите boq_code", None
    if not unit:
        return "Укажите unit_of_measure", None
    if not actor:
        return "Не указан approved_by — сохранить решение нельзя", None
    if not code:
        return f"Некорректное решение: {safe_text(draft.decision)}", None
    if not comment:
        return "Комментарий обязателен", None

    expected = normalize_unit(draft.expected_unit) if safe_text(draft.expected_unit) else ""
    if expected and not units_compatible(unit, expected):
        return (
            f"Несовпадение единиц: решение={unit}, ожидается={expected}. "
            "Тихая конвертация запрещена.",
            None,
        )

    approved_norm: Optional[float] = None
    if code in {DECISION_APPROVED_PROVISIONAL, DECISION_MANUAL_PROVISIONAL}:
        approved_norm = optional_float(draft.approved_norm)
        if approved_norm is None:
            return "Для временной нормы укажите конечное число approved_norm > 0", None
        if approved_norm <= 0:
            return "approved_norm должен быть > 0", None
    else:
        # REJECTED — norm must be absent
        if optional_float(draft.approved_norm) is not None:
            return "Для REJECTED поле approved_norm должно быть пустым", None

    suggested = optional_float(draft.suggested_norm)
    sample = optional_int(draft.sample_count)
    normalized = LaborNormDecisionDraft(
        project_code=project,
        facility_building=facility,
        construction_discipline=discipline,
        boq_code=boq,
        unit_of_measure=unit,
        decision=code,
        approved_by=actor,
        comment=comment,
        approved_norm=approved_norm,
        boq_name=safe_text(draft.boq_name),
        suggested_norm=suggested,
        suggested_source=safe_text(draft.suggested_source) or (
            SUGGESTED_SOURCE_HISTORICAL_P50 if suggested is not None else ""
        ),
        sample_count=sample,
        confidence=safe_text(draft.confidence),
        source_reference=safe_text(draft.source_reference),
        expected_unit=expected,
        source_page=safe_text(draft.source_page) or SOURCE_PAGE_DEFAULT,
    )
    return None, normalized


class LaborNormDecisionStore(Protocol):
    def get_active(
        self,
        *,
        project_code: str,
        facility_building: str,
        construction_discipline: str,
        boq_code: str,
    ) -> Optional[LaborNormDecisionRecord]:
        ...

    def list_decisions(
        self,
        *,
        project_code: str,
        facility_building: Optional[str] = None,
        construction_discipline: Optional[str] = None,
        boq_code: Optional[str] = None,
        include_cancelled: bool = False,
        limit: int = 500,
    ) -> list[LaborNormDecisionRecord]:
        ...

    def apply(self, draft: LaborNormDecisionDraft) -> dict[str, Any]:
        ...

    def cancel(
        self,
        *,
        project_code: str,
        facility_building: str,
        construction_discipline: str,
        boq_code: str,
        cancelled_by: str,
        reason: str = "",
    ) -> dict[str, Any]:
        ...


def _record_from_mapping(row: dict[str, Any]) -> LaborNormDecisionRecord:
    return LaborNormDecisionRecord(
        decision_id=safe_text(row.get("decision_id")),
        project_code=safe_text(row.get("project_code")),
        facility_building=safe_text(row.get("facility_building")),
        construction_discipline=safe_text(row.get("construction_discipline")),
        boq_code=normalize_boq(row.get("boq_code")),
        unit_of_measure=normalize_unit(row.get("unit_of_measure")),
        decision=normalize_decision_code(row.get("decision")) or safe_text(row.get("decision")),
        decision_status=safe_text(row.get("decision_status")).upper() or STATUS_ACTIVE,
        approved_by=safe_text(row.get("approved_by")),
        approved_at=safe_text(row.get("approved_at")),
        boq_name=safe_text(row.get("boq_name")),
        suggested_norm=optional_float(row.get("suggested_norm")),
        suggested_source=safe_text(row.get("suggested_source")),
        sample_count=optional_int(row.get("sample_count")),
        confidence=safe_text(row.get("confidence")),
        approved_norm=optional_float(row.get("approved_norm")),
        comment=safe_text(row.get("comment")),
        source_reference=safe_text(row.get("source_reference")),
        updated_by=safe_text(row.get("updated_by")),
        updated_at=safe_text(row.get("updated_at")),
        cancelled_by=safe_text(row.get("cancelled_by")),
        cancelled_at=safe_text(row.get("cancelled_at")),
        source_page=safe_text(row.get("source_page")) or SOURCE_PAGE_DEFAULT,
        created_at=safe_text(row.get("created_at")),
    )


@dataclass
class MemoryLaborNormDecisionStore:
    """In-process store mirroring RPC cancel-then-insert semantics (tests)."""

    rows: list[LaborNormDecisionRecord] = field(default_factory=list)

    def get_active(
        self,
        *,
        project_code: str,
        facility_building: str,
        construction_discipline: str,
        boq_code: str,
    ) -> Optional[LaborNormDecisionRecord]:
        project = safe_text(project_code)
        facility = safe_text(facility_building)
        discipline = safe_text(construction_discipline)
        boq = normalize_boq(boq_code)
        for row in reversed(self.rows):
            if (
                row.decision_status == STATUS_ACTIVE
                and row.project_code == project
                and row.facility_building == facility
                and row.construction_discipline == discipline
                and row.boq_code == boq
            ):
                return row
        return None

    def list_decisions(
        self,
        *,
        project_code: str,
        facility_building: Optional[str] = None,
        construction_discipline: Optional[str] = None,
        boq_code: Optional[str] = None,
        include_cancelled: bool = False,
        limit: int = 500,
    ) -> list[LaborNormDecisionRecord]:
        project = safe_text(project_code)
        facility = safe_text(facility_building) if facility_building else ""
        discipline = safe_text(construction_discipline) if construction_discipline else ""
        boq = normalize_boq(boq_code) if boq_code else ""
        out: list[LaborNormDecisionRecord] = []
        for row in self.rows:
            if row.project_code != project:
                continue
            if facility and row.facility_building != facility:
                continue
            if discipline and row.construction_discipline != discipline:
                continue
            if boq and row.boq_code != boq:
                continue
            if not include_cancelled and row.decision_status != STATUS_ACTIVE:
                continue
            out.append(row)
        return out[-limit:]

    def apply(self, draft: LaborNormDecisionDraft) -> dict[str, Any]:
        err, normalized = validate_decision_draft(draft)
        if err or normalized is None:
            return _result_err(err or "validation failed")
        now = utc_now().isoformat()
        cancelled_id = None
        active = self.get_active(
            project_code=normalized.project_code,
            facility_building=normalized.facility_building,
            construction_discipline=normalized.construction_discipline,
            boq_code=normalized.boq_code,
        )
        if active is not None:
            cancelled_id = active.decision_id
            replaced: list[LaborNormDecisionRecord] = []
            for row in self.rows:
                if row.decision_id == active.decision_id:
                    replaced.append(
                        LaborNormDecisionRecord(
                            **{
                                **row.to_dict(),
                                "decision_status": STATUS_CANCELLED,
                                "cancelled_by": normalized.approved_by,
                                "cancelled_at": now,
                                "updated_by": normalized.approved_by,
                                "updated_at": now,
                            }
                        )
                    )
                else:
                    replaced.append(row)
            self.rows = replaced
        new_id = str(uuid.uuid4())
        record = LaborNormDecisionRecord(
            decision_id=new_id,
            project_code=normalized.project_code,
            facility_building=normalized.facility_building,
            construction_discipline=normalized.construction_discipline,
            boq_code=normalized.boq_code,
            unit_of_measure=normalized.unit_of_measure,
            decision=normalized.decision,
            decision_status=STATUS_ACTIVE,
            approved_by=normalized.approved_by,
            approved_at=now,
            boq_name=normalized.boq_name,
            suggested_norm=normalized.suggested_norm,
            suggested_source=normalized.suggested_source,
            sample_count=normalized.sample_count,
            confidence=normalized.confidence,
            approved_norm=normalized.approved_norm,
            comment=normalized.comment,
            source_reference=normalized.source_reference or new_id,
            updated_by=normalized.approved_by,
            updated_at=now,
            source_page=normalized.source_page,
            created_at=now,
        )
        self.rows.append(record)
        active_count = sum(
            1
            for row in self.rows
            if row.decision_status == STATUS_ACTIVE
            and row.project_code == record.project_code
            and row.facility_building == record.facility_building
            and row.construction_discipline == record.construction_discipline
            and row.boq_code == record.boq_code
        )
        if active_count != 1:
            return _result_err("invariant broken: expected exactly one ACTIVE per grain")
        return _result_ok(
            {
                "status": "inserted" if cancelled_id is None else "replaced",
                "decision_id": record.decision_id,
                "cancelled_decision_id": cancelled_id,
                "record": record.to_dict(),
            }
        )

    def cancel(
        self,
        *,
        project_code: str,
        facility_building: str,
        construction_discipline: str,
        boq_code: str,
        cancelled_by: str,
        reason: str = "",
    ) -> dict[str, Any]:
        actor = safe_text(cancelled_by)
        if not actor:
            return _result_err("Не указан cancelled_by")
        active = self.get_active(
            project_code=project_code,
            facility_building=facility_building,
            construction_discipline=construction_discipline,
            boq_code=boq_code,
        )
        if active is None:
            return _result_ok({"status": "not_found"})
        now = utc_now().isoformat()
        replaced: list[LaborNormDecisionRecord] = []
        for row in self.rows:
            if row.decision_id == active.decision_id:
                replaced.append(
                    LaborNormDecisionRecord(
                        **{
                            **row.to_dict(),
                            "decision_status": STATUS_CANCELLED,
                            "cancelled_by": actor,
                            "cancelled_at": now,
                            "updated_by": actor,
                            "updated_at": now,
                            "comment": safe_text(reason) or row.comment,
                        }
                    )
                )
            else:
                replaced.append(row)
        self.rows = replaced
        return _result_ok({"status": "cancelled", "decision_id": active.decision_id})


def get_write_client():
    """
    Return service_role Supabase client, or None if credentials missing.
    Never returns the anon client.
    """
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    url = os.getenv("SUPABASE_URL")
    if not secret_key or not url:
        return None
    from supabase import create_client

    return create_client(url, secret_key)


def require_service_role_client():
    """
    service_role client for labor_norm_decisions table + RPCs.
    Fail-closed: never falls back to anon.
    """
    client = get_write_client()
    if client is None:
        raise RuntimeError(SERVICE_ROLE_MISSING_MSG)
    return client


class SupabaseLaborNormDecisionStore:
    """
    Durable store for labor_norm_decisions.

    All table reads and apply/cancel RPCs use SUPABASE_SECRET_KEY only.
    Missing secret → fail closed (no anon fallback).
    """

    def get_active(
        self,
        *,
        project_code: str,
        facility_building: str,
        construction_discipline: str,
        boq_code: str,
    ) -> Optional[LaborNormDecisionRecord]:
        client = require_service_role_client()
        try:
            response = (
                client.table(TABLE)
                .select(SELECT_COLS)
                .eq("project_code", safe_text(project_code))
                .eq("facility_building", safe_text(facility_building))
                .eq("construction_discipline", safe_text(construction_discipline))
                .eq("boq_code", normalize_boq(boq_code))
                .eq("decision_status", STATUS_ACTIVE)
                .limit(2)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Ошибка чтения {TABLE}: {exc}") from exc
        rows = list(response.data or [])
        if not rows:
            return None
        return _record_from_mapping(rows[0])

    def list_decisions(
        self,
        *,
        project_code: str,
        facility_building: Optional[str] = None,
        construction_discipline: Optional[str] = None,
        boq_code: Optional[str] = None,
        include_cancelled: bool = False,
        limit: int = 500,
    ) -> list[LaborNormDecisionRecord]:
        client = require_service_role_client()
        query = (
            client.table(TABLE)
            .select(SELECT_COLS)
            .eq("project_code", safe_text(project_code))
            .order("approved_at", desc=True)
            .limit(limit)
        )
        if facility_building:
            query = query.eq("facility_building", safe_text(facility_building))
        if construction_discipline:
            query = query.eq(
                "construction_discipline", safe_text(construction_discipline)
            )
        if boq_code:
            query = query.eq("boq_code", normalize_boq(boq_code))
        if not include_cancelled:
            query = query.eq("decision_status", STATUS_ACTIVE)
        try:
            response = query.execute()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Ошибка чтения {TABLE}: {exc}") from exc
        return [_record_from_mapping(row) for row in (response.data or [])]

    def apply(self, draft: LaborNormDecisionDraft) -> dict[str, Any]:
        err, normalized = validate_decision_draft(draft)
        if err or normalized is None:
            return _result_err(err or "validation failed")
        try:
            client = require_service_role_client()
        except RuntimeError as exc:
            return _result_err(str(exc))
        payload = {
            "boq_name": normalized.boq_name,
            "suggested_norm": (
                None if normalized.suggested_norm is None else str(normalized.suggested_norm)
            ),
            "suggested_source": normalized.suggested_source,
            "sample_count": (
                None if normalized.sample_count is None else str(normalized.sample_count)
            ),
            "confidence": normalized.confidence,
            "approved_norm": (
                None if normalized.approved_norm is None else str(normalized.approved_norm)
            ),
            "comment": normalized.comment,
            "source_reference": normalized.source_reference,
            "source_page": normalized.source_page,
        }
        try:
            response = client.rpc(
                RPC_APPLY,
                {
                    "p_project_code": normalized.project_code,
                    "p_facility_building": normalized.facility_building,
                    "p_construction_discipline": normalized.construction_discipline,
                    "p_boq_code": normalized.boq_code,
                    "p_unit_of_measure": normalized.unit_of_measure,
                    "p_decision": normalized.decision,
                    "p_approved_by": normalized.approved_by,
                    "p_payload": payload,
                },
            ).execute()
        except Exception as exc:  # noqa: BLE001
            return _result_err(f"{RPC_APPLY}: {exc}")
        data = response.data
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if not isinstance(data, dict):
            return _result_err(f"{RPC_APPLY}: unexpected response")
        return _result_ok(data)

    def cancel(
        self,
        *,
        project_code: str,
        facility_building: str,
        construction_discipline: str,
        boq_code: str,
        cancelled_by: str,
        reason: str = "",
    ) -> dict[str, Any]:
        actor = safe_text(cancelled_by)
        if not actor:
            return _result_err("Не указан cancelled_by")
        try:
            client = require_service_role_client()
        except RuntimeError as exc:
            return _result_err(str(exc))
        try:
            response = client.rpc(
                RPC_CANCEL,
                {
                    "p_project_code": safe_text(project_code),
                    "p_facility_building": safe_text(facility_building),
                    "p_construction_discipline": safe_text(construction_discipline),
                    "p_boq_code": normalize_boq(boq_code),
                    "p_cancelled_by": actor,
                    "p_reason": safe_text(reason) or None,
                },
            ).execute()
        except Exception as exc:  # noqa: BLE001
            return _result_err(f"{RPC_CANCEL}: {exc}")
        data = response.data
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if not isinstance(data, dict):
            return _result_err(f"{RPC_CANCEL}: unexpected response")
        return _result_ok(data)


def save_decision(
    draft: LaborNormDecisionDraft,
    *,
    store: Optional[LaborNormDecisionStore] = None,
) -> dict[str, Any]:
    backend: LaborNormDecisionStore = store or SupabaseLaborNormDecisionStore()
    return backend.apply(draft)


def get_active_decision(
    *,
    project_code: str,
    facility_building: str,
    construction_discipline: str,
    boq_code: str,
    store: Optional[LaborNormDecisionStore] = None,
) -> Optional[LaborNormDecisionRecord]:
    backend: LaborNormDecisionStore = store or SupabaseLaborNormDecisionStore()
    return backend.get_active(
        project_code=project_code,
        facility_building=facility_building,
        construction_discipline=construction_discipline,
        boq_code=boq_code,
    )


def list_decisions(
    *,
    project_code: str,
    facility_building: Optional[str] = None,
    construction_discipline: Optional[str] = None,
    boq_code: Optional[str] = None,
    include_cancelled: bool = False,
    limit: int = 500,
    store: Optional[LaborNormDecisionStore] = None,
) -> list[LaborNormDecisionRecord]:
    backend: LaborNormDecisionStore = store or SupabaseLaborNormDecisionStore()
    return backend.list_decisions(
        project_code=project_code,
        facility_building=facility_building,
        construction_discipline=construction_discipline,
        boq_code=boq_code,
        include_cancelled=include_cancelled,
        limit=limit,
    )


def load_boq_norm_hints(
    *,
    project_code: str,
    facility_building: Optional[str] = None,
    construction_discipline: Optional[str] = None,
    limit: int = 5000,
    max_attempts: int = 2,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """
    Read-only hints from monthly_scope_picker_view (+ optional norms sample_count).
    Never elevates P50 to validated authority.

    Prefer service_role when SUPABASE_SECRET_KEY is set (same Streamlit server
    credential as LND writes). At most ``max_attempts`` tries (default 2) —
    optional hint load must not block the human register for long retry chains.
    """
    project = safe_text(project_code)
    if not project:
        return [], "Укажите project_code"
    client = get_write_client() or supabase
    picker_cols = (
        "project_code,facility_building,construction_discipline,boq_code,boq_name,"
        "unit_of_measure,p50_hours_per_unit,p80_hours_per_unit,confidence_level,"
        "norm_status,executed_qty_all_time,planning_remaining_qty"
    )
    rows: list[dict[str, Any]] = []
    last_error: Optional[str] = None
    attempts = max(1, int(max_attempts))
    for attempt in range(attempts):
        try:
            query = (
                client.table(SCOPE_VIEW)
                .select(picker_cols)
                .eq("project_code", project)
                .limit(limit)
            )
            response = query.execute()
            rows = list(response.data or [])
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001
            last_error = f"Ошибка чтения {SCOPE_VIEW}: {exc}"
            if attempt + 1 < attempts:
                time.sleep(0.35 * (attempt + 1))
    if last_error is not None:
        return [], last_error

    # Optional sample_count from norms (best-effort; ignore failures)
    sample_by_key: dict[tuple[str, str, str, str], int] = {}
    try:
        norms = (
            client.table(NORMS_VIEW)
            .select(
                "project_code,facility_building,construction_discipline,"
                "boq_code_norm,records_count"
            )
            .eq("project_code", project)
            .limit(limit)
            .execute()
            .data
            or []
        )
        for row in norms:
            key = (
                safe_text(row.get("project_code")),
                safe_text(row.get("facility_building")),
                safe_text(row.get("construction_discipline")),
                normalize_boq(row.get("boq_code_norm")),
            )
            count = optional_int(row.get("records_count"))
            if count is not None:
                sample_by_key[key] = count
    except Exception:  # noqa: BLE001
        sample_by_key = {}

    facility_filter = safe_text(facility_building) if facility_building else ""
    discipline_filter = (
        safe_text(construction_discipline) if construction_discipline else ""
    )
    hints: list[dict[str, Any]] = []
    for row in rows:
        facility = safe_text(row.get("facility_building"))
        discipline = safe_text(row.get("construction_discipline"))
        if facility_filter and facility != facility_filter:
            continue
        if discipline_filter and discipline != discipline_filter:
            continue
        boq = normalize_boq(row.get("boq_code"))
        if not boq:
            continue
        sample = sample_by_key.get((project, facility, discipline, boq))
        hints.append(
            {
                "project_code": project,
                "facility_building": facility,
                "construction_discipline": discipline,
                "boq_code": boq,
                "boq_name": safe_text(row.get("boq_name")),
                "unit_of_measure": normalize_unit(row.get("unit_of_measure")),
                "p50_hours_per_unit": optional_float(row.get("p50_hours_per_unit")),
                "p80_hours_per_unit": optional_float(row.get("p80_hours_per_unit")),
                "confidence": safe_text(row.get("confidence_level")),
                "norm_status": safe_text(row.get("norm_status")),
                "sample_count": sample,
                "executed_qty_all_time": optional_float(row.get("executed_qty_all_time")),
                "planning_remaining_qty": optional_float(
                    row.get("planning_remaining_qty")
                ),
                "hint_authority": "HINT_ONLY",
                "validated": False,
                "warning": HINT_WARNING_RU,
            }
        )
    hints.sort(
        key=lambda item: (
            item["facility_building"],
            item["construction_discipline"],
            item["boq_code"],
        )
    )
    return hints, None
