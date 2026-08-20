"""
EOS-SEC-1.1 SEC-STEP-1 — AgentExecutionContext + trusted issuer.

Context is immutable and never contains credentials.
Issuer loads allowed_tools from a static trusted registry — not from the agent.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional


SECURITY_POLICY_VERSION = "EOS-SEC-1.1"

# Transitional actor — NOT verified human identity (no Auth / membership yet).
ACTOR_TYPE_LOCAL_APPLICATION = "LOCAL_APPLICATION"
ACTOR_ID_EXECUTION_OS_LOCAL_HOST = "EXECUTION_OS_LOCAL_HOST"

TOOL_LOAD_SCOPE = "load_constructor_scope"
TOOL_LOAD_ADJUSTMENTS = "load_constructor_adjustments"
TOOL_LOAD_PLAN_LINES = "load_constructor_month_plan_lines"

MPCA_ALLOWED_TOOLS: tuple[str, ...] = (
    TOOL_LOAD_SCOPE,
    TOOL_LOAD_ADJUSTMENTS,
    TOOL_LOAD_PLAN_LINES,
)

# Trusted static registry — agent cannot invent entries.
_TRUSTED_AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    "MONTHLY_PLAN_CONSTRUCTOR": {
        "agent_version": "0.1",
        "allowed_tools": MPCA_ALLOWED_TOOLS,
        "permission_tier": "TIER_0_READ_ONLY_DETERMINISTIC",
        "write_allowed": False,
        "security_policy_version": SECURITY_POLICY_VERSION,
    }
}


class ContextIssueError(ValueError):
    """Fail-closed context issuance failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class AgentExecutionContext:
    """
    Immutable trusted execution scope for an agent run.

    THIS IS NOT VERIFIED HUMAN IDENTITY.
    Transitional local application identity until Auth + project membership.
    """

    actor_id: str
    actor_type: str
    agent_code: str
    agent_version: str
    run_id: str
    project_code: str
    allowed_tools: tuple[str, ...]
    permission_tier: str
    authorization_id: str
    issued_at: str
    expires_at: str
    security_policy_version: str
    write_allowed: bool
    identity_note: str = (
        "THIS IS NOT VERIFIED HUMAN IDENTITY. "
        "Transitional LOCAL_APPLICATION execution identity."
    )

    def to_safe_dict(self) -> dict[str, Any]:
        """Safe metadata for AgentConstructorRun (no secrets, no clients)."""
        return {
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "agent_code": self.agent_code,
            "agent_version": self.agent_version,
            "run_id": self.run_id,
            "project_code": self.project_code,
            "authorization_id": self.authorization_id,
            "security_policy_version": self.security_policy_version,
            "permission_tier": self.permission_tier,
            "write_allowed": self.write_allowed,
            "identity_note": self.identity_note,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "allowed_tools": list(self.allowed_tools),
        }

    def is_expired(self, *, now: Optional[datetime] = None) -> bool:
        current = now or datetime.now(timezone.utc)
        try:
            exp = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return current >= exp


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text


def get_trusted_agent_policy(agent_code: str) -> Mapping[str, Any]:
    code = _safe_text(agent_code)
    policy = _TRUSTED_AGENT_REGISTRY.get(code)
    if not policy:
        raise ContextIssueError("UNKNOWN_AGENT", f"Unknown agent_code={code!r}")
    return policy


def issue_read_only_agent_context(
    *,
    agent_code: str,
    project_code: str,
    run_id: Optional[str] = None,
    ttl_seconds: int = 3600,
) -> AgentExecutionContext:
    """
    Trusted issuer. Caller cannot supply allowed_tools / write_allowed / tier.

    Fail closed on unknown agent or blank project.
    """
    code = _safe_text(agent_code)
    project = _safe_text(project_code)
    if not project:
        raise ContextIssueError("BLANK_PROJECT", "project_code is required")
    policy = get_trusted_agent_policy(code)
    if bool(policy.get("write_allowed")):
        raise ContextIssueError(
            "WRITE_NOT_ALLOWED_FOR_ISSUER",
            "Read-only issuer refuses write_allowed=true policies",
        )
    tools = tuple(policy["allowed_tools"])
    if not tools:
        raise ContextIssueError("EMPTY_TOOL_POLICY", "allowed_tools empty in registry")

    now = _utcnow()
    if ttl_seconds <= 0:
        raise ContextIssueError("INVALID_TTL", "ttl_seconds must be positive")
    expires = now + timedelta(seconds=ttl_seconds)
    rid = _safe_text(run_id) or str(uuid.uuid4())

    return AgentExecutionContext(
        actor_id=ACTOR_ID_EXECUTION_OS_LOCAL_HOST,
        actor_type=ACTOR_TYPE_LOCAL_APPLICATION,
        agent_code=code,
        agent_version=str(policy["agent_version"]),
        run_id=rid,
        project_code=project,
        allowed_tools=tools,
        permission_tier=str(policy["permission_tier"]),
        authorization_id=str(uuid.uuid4()),
        issued_at=now.isoformat(),
        expires_at=expires.isoformat(),
        security_policy_version=str(policy["security_policy_version"]),
        write_allowed=False,
    )
