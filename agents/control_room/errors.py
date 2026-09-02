"""
Increment 10.6 — agent-neutral Control Room query-layer errors.

Safe operator-facing messages only. No SQLite paths or SQL leakage.
"""

from __future__ import annotations

CODE_CONTROL_ROOM_QUERY_BLOCKER = "CONTROL_ROOM_QUERY_BLOCKER"
CODE_CONTROL_ROOM_RUN_NOT_FOUND = "CONTROL_ROOM_RUN_NOT_FOUND"
CODE_CONTROL_ROOM_STORAGE_UNAVAILABLE = "CONTROL_ROOM_STORAGE_UNAVAILABLE"
CODE_CONTROL_ROOM_DERIVATION_INCONSISTENT = "CONTROL_ROOM_DERIVATION_INCONSISTENT"


class ControlRoomQueryError(ValueError):
    """Base Control Room read-side failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ControlRoomRunNotFoundError(ControlRoomQueryError):
    def __init__(self, message: str = "run not found") -> None:
        super().__init__(CODE_CONTROL_ROOM_RUN_NOT_FOUND, message)


class ControlRoomQueryBlockerError(ControlRoomQueryError):
    def __init__(self, message: str) -> None:
        super().__init__(CODE_CONTROL_ROOM_QUERY_BLOCKER, message)


class ControlRoomStorageUnavailableError(ControlRoomQueryError):
    def __init__(self, message: str = "storage unavailable") -> None:
        super().__init__(CODE_CONTROL_ROOM_STORAGE_UNAVAILABLE, message)


class ControlRoomDerivationError(ControlRoomQueryError):
    def __init__(self, message: str = "derivation inconsistent") -> None:
        super().__init__(CODE_CONTROL_ROOM_DERIVATION_INCONSISTENT, message)
