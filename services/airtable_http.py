"""
Shared Airtable HTTP transport for sync scripts.

READ-only GET with bounded retry. No business mapping. No Supabase writes.
TLS verification always ON (certificate validation is never disabled).
"""

from __future__ import annotations

import os
import time
from typing import Any, Mapping, MutableMapping, Sequence

import requests

DEFAULT_TIMEOUT: tuple[float, float] = (10, 60)
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (2.0, 5.0, 10.0)

RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
NON_RETRY_HTTP_STATUS: frozenset[int] = frozenset({400, 401, 403, 404, 422})

RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ReadTimeout,
    requests.exceptions.Timeout,
)

_PROXY_ENV_KEYS: tuple[str, ...] = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def strip_proxy_env(environ: MutableMapping[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    for key in _PROXY_ENV_KEYS:
        env.pop(key, None)


def make_airtable_session() -> requests.Session:
    """Direct session: ignore process proxy env for Airtable reads."""
    strip_proxy_env()
    session = requests.Session()
    session.trust_env = False
    return session


def _safe_error_label(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc)
    # Avoid leaking bearer tokens if somehow present in message.
    lowered = text.lower()
    if "bearer " in lowered or "authorization" in lowered:
        return name
    # Keep short, no headers/secrets.
    compact = " ".join(text.replace("\n", " ").split())
    if len(compact) > 180:
        compact = compact[:177] + "..."
    return f"{name}: {compact}" if compact else name


def airtable_get(
    url: str,
    *,
    headers: Mapping[str, str],
    params: Mapping[str, Any] | None = None,
    timeout: tuple[float, float] | float = DEFAULT_TIMEOUT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
    session: requests.Session | None = None,
    sleep: Any = time.sleep,
    log: Any = print,
) -> requests.Response:
    """
    GET with bounded retry for transient transport / selected HTTP errors.

    FAIL CLOSED on persistent TLS/certificate failures after attempts exhausted.
    Does not disable certificate verification.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    own_session = session is None
    sess = make_airtable_session() if own_session else session
    assert sess is not None

    last_error: BaseException | None = None
    try:
        for attempt in range(1, max_attempts + 1):
            log(f"AIRTABLE READ attempt {attempt}/{max_attempts}")
            try:
                resp = sess.get(
                    url,
                    headers=dict(headers),
                    params=dict(params) if params is not None else None,
                    timeout=timeout,
                )
            except RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                log(f"FAILED: {_safe_error_label(exc)}")
                if attempt >= max_attempts:
                    break
                delay = float(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
                log(f"RETRY IN {delay:g}s")
                sleep(delay)
                continue

            status = int(resp.status_code)
            if status in RETRYABLE_HTTP_STATUS:
                last_error = requests.exceptions.HTTPError(
                    f"{status} Server Error for Airtable GET",
                    response=resp,
                )
                log(f"FAILED: HTTP {status}")
                if attempt >= max_attempts:
                    resp.raise_for_status()
                delay = float(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
                log(f"RETRY IN {delay:g}s")
                sleep(delay)
                continue

            if status >= 400:
                # Permanent / non-retry application errors — fail closed immediately.
                log(f"FAILED: HTTP {status} (no retry)")
                resp.raise_for_status()

            log("SUCCESS")
            return resp

        if last_error is not None:
            raise last_error
        raise RuntimeError("Airtable GET failed without exception detail")
    finally:
        if own_session:
            sess.close()
