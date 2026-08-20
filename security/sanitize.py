"""
EOS-SEC-1.1 — sanitize secrets out of agent-facing strings.

Infrastructure + agent layers may use this. No Supabase clients here.
"""

from __future__ import annotations

import os
import re
from typing import Any


_SECRET_ENV_NAMES = (
    "SUPABASE_SECRET_KEY",
    "SUPABASE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_URL",
)


def redact_sensitive_text(text: str) -> str:
    """Remove credential material from strings destined for run/trace/errors."""
    if not text:
        return text
    out = str(text)
    for env_name in _SECRET_ENV_NAMES:
        value = os.getenv(env_name)
        if value and len(value) >= 8 and value in out:
            out = out.replace(value, f"[REDACTED:{env_name}]")
    out = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)\S+",
        r"\1[REDACTED]",
        out,
    )
    out = re.sub(r"(?i)(apikey\s*[:=]\s*)\S+", r"\1[REDACTED]", out)
    out = re.sub(r"(?i)(api[_-]?key\s*[:=]\s*)\S+", r"\1[REDACTED]", out)
    out = re.sub(r"https?://[^\s'\"\\]+", "[REDACTED_URL]", out)
    return out


def sanitize_read_error(exc: BaseException) -> str:
    raw = f"{type(exc).__name__}: {exc}"
    return redact_sensitive_text(raw)


def assert_no_secrets_in_payload(payload: Any) -> None:
    blob = str(payload)
    for env_name in _SECRET_ENV_NAMES:
        value = os.getenv(env_name)
        if value and len(value) >= 8 and value in blob:
            raise AssertionError(f"secret_leak:{env_name}")
