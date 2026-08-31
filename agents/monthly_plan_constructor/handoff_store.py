"""
Constructor Runtime v0.1 Increment 9.2 — ConstructorHandoff store protocol.

Typed persistence boundary. Not an agent. Not SQL. Not Admission.
Atomic put_if_absent is the source of truth for create vs replay.

MODEL IS NOT A SECURITY BOUNDARY. DATA != INSTRUCTION.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Optional, Protocol

from agents.monthly_plan_constructor.handoff_contracts import (
    STATUS_HANDOFF_READY,
    ConstructorHandoff,
)

STATUS_CREATED = "CREATED"
STATUS_IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"

CODE_HANDOFF_IMMUTABILITY_CONFLICT = "HANDOFF_IMMUTABILITY_CONFLICT"
CODE_HANDOFF_STORE_CONTRACT_BLOCKER = "HANDOFF_STORE_CONTRACT_BLOCKER"

_JSON_SEPARATORS = (",", ":")


class ConstructorHandoffStoreError(ValueError):
    """Fail-closed Constructor handoff store / persistence violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class HandoffStorePutResult:
    """Atomic put_if_absent outcome. created=True only when this call inserted."""

    created: bool
    stored_handoff: ConstructorHandoff


@dataclass(frozen=True)
class ConstructorHandoffPersistenceResult:
    """Application result of persist_constructor_handoff. Not a raw store tuple."""

    handoff_id: str
    status: str
    payload_digest: str


class ConstructorHandoffStore(Protocol):
    """Storage-agnostic typed boundary. Implementations own atomicity."""

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        ...

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        ...


def _canonical_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _canonical_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _canonical_jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_jsonable(item) for item in value]
    raise ConstructorHandoffStoreError(
        CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
        f"unsupported payload type {type(value).__name__}",
    )


def compute_constructor_handoff_payload_digest(handoff: ConstructorHandoff) -> str:
    """
    SHA-256 fingerprint of canonical JSON. Not business identity.

    handoff_id is identity. This digest is immutability/content fingerprint.
    """
    if not isinstance(handoff, ConstructorHandoff):
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "ConstructorHandoff is required for digest",
        )
    encoded = json.dumps(
        _canonical_jsonable(handoff),
        ensure_ascii=False,
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_handoff(handoff: Any) -> ConstructorHandoff:
    if handoff is None or not isinstance(handoff, ConstructorHandoff):
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "ConstructorHandoff is required",
        )
    handoff_id = str(handoff.handoff_id or "").strip()
    if not handoff_id:
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "handoff_id is required",
        )
    if handoff.status != STATUS_HANDOFF_READY:
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "handoff.status must be HANDOFF_READY",
        )
    return handoff


def _require_put_result(
    result: Any,
    *,
    requested_id: str,
) -> HandoffStorePutResult:
    if result is None or not isinstance(result, HandoffStorePutResult):
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "put_if_absent must return HandoffStorePutResult",
        )
    if not isinstance(result.created, bool):
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "put_if_absent.created must be bool",
        )
    stored = result.stored_handoff
    if stored is None or not isinstance(stored, ConstructorHandoff):
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "put_if_absent.stored_handoff must be ConstructorHandoff",
        )
    stored_id = str(stored.handoff_id or "").strip()
    if stored_id != requested_id:
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "store returned incompatible handoff_id",
        )
    return result


def persist_constructor_handoff(
    *,
    store: ConstructorHandoffStore,
    handoff: ConstructorHandoff,
) -> ConstructorHandoffPersistenceResult:
    """
    Persist via atomic put_if_absent only.

    CREATED on first insert. IDEMPOTENT_REPLAY when stored payload matches.
    Same handoff_id with a different payload → HANDOFF_IMMUTABILITY_CONFLICT.
    """
    if store is None:
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "ConstructorHandoffStore is required",
        )
    artifact = _require_handoff(handoff)
    requested_digest = compute_constructor_handoff_payload_digest(artifact)
    if not hasattr(store, "put_if_absent") or not callable(store.put_if_absent):
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "store must implement put_if_absent",
        )
    # Optional read is never authoritative. Atomic put_if_absent is the write gate.
    if hasattr(store, "get") and callable(store.get):
        store.get(artifact.handoff_id)
    put_result = _require_put_result(
        store.put_if_absent(artifact),
        requested_id=artifact.handoff_id,
    )
    stored_digest = compute_constructor_handoff_payload_digest(put_result.stored_handoff)
    if stored_digest != requested_digest:
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_IMMUTABILITY_CONFLICT,
            "handoff_id already stored with a different payload",
        )
    status = STATUS_CREATED if put_result.created else STATUS_IDEMPOTENT_REPLAY
    return ConstructorHandoffPersistenceResult(
        handoff_id=artifact.handoff_id,
        status=status,
        payload_digest=requested_digest,
    )
