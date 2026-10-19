"""
Durable immutable Approved Monthly Package store.

Creates only:
<checkpoints directory>/approved_monthly_packages.sqlite

Not handoff.sqlite, not web/db.sqlite3, not a product database.
No update-in-place business API.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agents.monthly_plan_constructor.approved_monthly_package import (
    ApprovedMonthlyPackage,
    canonical_json,
    package_from_payload,
    package_to_payload,
)

CODE_APPROVED_STORE_CONFLICT = "APPROVED_PACKAGE_CONFLICT"
CODE_APPROVED_STORE_BLOCKER = "APPROVED_STORE_BLOCKER"
DB_FILENAME = "approved_monthly_packages.sqlite"

_BOOTSTRAP_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS approved_monthly_packages (
    approved_package_id TEXT PRIMARY KEY,
    source_candidate_package_id TEXT NOT NULL,
    source_review_content_hash TEXT NOT NULL,
    source_preview_content_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_approved_source_snapshot
ON approved_monthly_packages (
    source_candidate_package_id,
    source_review_content_hash,
    source_preview_content_hash
);
"""


class ApprovedMonthlyPackageStoreError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ApprovedPackagePutResult:
    created: bool
    package: ApprovedMonthlyPackage


class ApprovedMonthlyPackageStore:
    def __init__(self, *, db_path: Path, connection: sqlite3.Connection) -> None:
        self._db_path = db_path
        self._connection = connection
        self._closed = False
        self._lock = threading.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._connection.close()

    def get_by_id(self, approved_package_id: str) -> Optional[ApprovedMonthlyPackage]:
        self._require_open()
        key = str(approved_package_id or "").strip()
        if not key:
            raise ApprovedMonthlyPackageStoreError(
                CODE_APPROVED_STORE_BLOCKER,
                "approved_package_id is required",
            )
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json
                FROM approved_monthly_packages
                WHERE approved_package_id = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return package_from_payload(_loads(row[0]))

    def find_by_source_package_and_review_hash(
        self,
        *,
        source_candidate_package_id: str,
        source_review_content_hash: str,
        source_preview_content_hash: str,
    ) -> Optional[ApprovedMonthlyPackage]:
        self._require_open()
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json
                FROM approved_monthly_packages
                WHERE source_candidate_package_id = ?
                  AND source_review_content_hash = ?
                  AND source_preview_content_hash = ?
                """,
                (
                    source_candidate_package_id,
                    source_review_content_hash,
                    source_preview_content_hash,
                ),
            ).fetchone()
        if row is None:
            return None
        return package_from_payload(_loads(row[0]))

    def put_if_absent(self, package: ApprovedMonthlyPackage) -> ApprovedPackagePutResult:
        self._require_open()
        payload = package_to_payload(package)
        payload_json = canonical_json(payload)
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                existing = self._connection.execute(
                    """
                    SELECT approved_package_id, content_hash, payload_json
                    FROM approved_monthly_packages
                    WHERE source_candidate_package_id = ?
                      AND source_review_content_hash = ?
                      AND source_preview_content_hash = ?
                    """,
                    (
                        package.source_candidate_package_id,
                        package.source_review_content_hash,
                        package.source_preview_content_hash,
                    ),
                ).fetchone()
                if existing is not None:
                    if str(existing[1]) != package.content_hash:
                        raise ApprovedMonthlyPackageStoreError(
                            CODE_APPROVED_STORE_CONFLICT,
                            "source snapshot already stored with a different payload",
                        )
                    self._connection.execute("COMMIT")
                    return ApprovedPackagePutResult(
                        created=False,
                        package=package_from_payload(_loads(existing[2])),
                    )
                by_id = self._connection.execute(
                    """
                    SELECT content_hash FROM approved_monthly_packages
                    WHERE approved_package_id = ?
                    """,
                    (package.approved_package_id,),
                ).fetchone()
                if by_id is not None and str(by_id[0]) != package.content_hash:
                    raise ApprovedMonthlyPackageStoreError(
                        CODE_APPROVED_STORE_CONFLICT,
                        "approved_package_id already stored with a different payload",
                    )
                self._connection.execute(
                    """
                    INSERT INTO approved_monthly_packages (
                        approved_package_id,
                        source_candidate_package_id,
                        source_review_content_hash,
                        source_preview_content_hash,
                        content_hash,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        package.approved_package_id,
                        package.source_candidate_package_id,
                        package.source_review_content_hash,
                        package.source_preview_content_hash,
                        package.content_hash,
                        payload_json,
                    ),
                )
                self._connection.execute("COMMIT")
                return ApprovedPackagePutResult(created=True, package=package)
            except ApprovedMonthlyPackageStoreError:
                self._connection.execute("ROLLBACK")
                raise
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ApprovedMonthlyPackageStoreError(
                    CODE_APPROVED_STORE_CONFLICT,
                    "approved package identity collision",
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _require_open(self) -> None:
        if self._closed:
            raise ApprovedMonthlyPackageStoreError(
                CODE_APPROVED_STORE_BLOCKER,
                "ApprovedMonthlyPackageStore is closed",
            )


def _loads(payload_json: str) -> dict:
    import json

    loaded = json.loads(payload_json)
    if not isinstance(loaded, dict):
        raise ApprovedMonthlyPackageStoreError(
            CODE_APPROVED_STORE_BLOCKER,
            "stored payload must be an object",
        )
    return loaded


def open_approved_monthly_package_store(db_path: Path) -> ApprovedMonthlyPackageStore:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(_BOOTSTRAP_SQL)
    connection.commit()
    return ApprovedMonthlyPackageStore(db_path=path, connection=connection)


def open_existing_approved_monthly_package_store(
    db_path: Path,
) -> Optional[ApprovedMonthlyPackageStore]:
    path = Path(db_path)
    if not path.is_file():
        return None
    connection = sqlite3.connect(path)
    return ApprovedMonthlyPackageStore(db_path=path, connection=connection)
