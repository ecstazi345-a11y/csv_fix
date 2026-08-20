"""
MPCA-001 — thin agent-facing READ tool wrappers.

No credentials. No Supabase client. Project comes from AgentExecutionContext.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from security.agent_execution_context import AgentExecutionContext
from security.trusted_read_executor import (
    execute_constructor_adjustments_read,
    execute_constructor_plan_lines_read,
    execute_constructor_scope_read,
)


def load_scope(context: AgentExecutionContext) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Tool wrapper → trusted executor scope read."""
    return execute_constructor_scope_read(context)


def load_adjustments(
    context: AgentExecutionContext,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Tool wrapper → trusted executor adjustments read."""
    return execute_constructor_adjustments_read(context)


def load_existing_month_plan_lines(
    context: AgentExecutionContext,
    stored_month_key: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Tool wrapper → trusted executor plan-lines read (month is operational)."""
    return execute_constructor_plan_lines_read(context, stored_month_key)
