"""Optional performance audit logging for Streamlit / Supabase load paths.

Enable with environment variable PERF_AUDIT=1 (true/yes/on).
When disabled, helpers are near no-ops and add no output.
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


def perf_audit_enabled() -> bool:
    return os.getenv("PERF_AUDIT", "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class _PageSession:
    page: str
    t0: float = field(default_factory=time.perf_counter)
    stages: List[tuple[float, str]] = field(default_factory=list)
    supabase_calls: List[Dict[str, Any]] = field(default_factory=list)

    def log(self, label: str) -> None:
        elapsed = time.perf_counter() - self.t0
        self.stages.append((elapsed, label))
        if perf_audit_enabled():
            print(f"[PERF] [{elapsed:.2f}s] {self.page} — {label}", file=sys.stderr, flush=True)

    def finish(self) -> None:
        if not perf_audit_enabled():
            return
        total = time.perf_counter() - self.t0
        for elapsed, label in self.stages:
            print(f"[PERF] [{elapsed:.2f}s] {label}", file=sys.stderr, flush=True)
        print(f"[PERF] TOTAL PAGE TIME {self.page}: {total:.2f}s", file=sys.stderr, flush=True)
        if self.supabase_calls:
            print(f"[PERF] Supabase calls ({len(self.supabase_calls)}):", file=sys.stderr, flush=True)
            for call in self.supabase_calls:
                print(
                    f"[PERF]   [{call.get('seconds', 0):.2f}s] "
                    f"{call.get('table')} rows={call.get('rows')} "
                    f"pages={call.get('pages', 1)}",
                    file=sys.stderr,
                    flush=True,
                )


_current: Optional[_PageSession] = None


def start_page(page_name: str) -> _PageSession:
    global _current
    _current = _PageSession(page=page_name)
    if perf_audit_enabled():
        print(f"[PERF] START PAGE {page_name}", file=sys.stderr, flush=True)
    return _current


def get_session() -> Optional[_PageSession]:
    return _current


@contextmanager
def stage(label: str, *, page: Optional[str] = None) -> Iterator[None]:
    if not perf_audit_enabled() and _current is None:
        yield
        return
    sess = _current
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = time.perf_counter() - t0
        if sess is not None:
            sess.log(f"{label} (+{dt:.2f}s)")
        elif perf_audit_enabled():
            name = page or "?"
            print(f"[PERF] [{dt:.2f}s] {name} — {label}", file=sys.stderr, flush=True)


def log_supabase_query(
    table: str,
    seconds: float,
    rows: int,
    *,
    pages: int = 1,
) -> None:
    entry = {"table": table, "seconds": seconds, "rows": rows, "pages": pages}
    if _current is not None:
        _current.supabase_calls.append(entry)
    if perf_audit_enabled():
        print(
            f"[PERF] [supabase {seconds:.2f}s] {table} rows={rows} pages={pages}",
            file=sys.stderr,
            flush=True,
        )


def finish_page() -> None:
    global _current
    if _current is not None:
        _current.finish()
        _current = None
