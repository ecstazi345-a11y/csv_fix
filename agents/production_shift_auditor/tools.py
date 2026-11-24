"""PSAA allowlisted tools — no credentials, no product writes, no SQL."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from security.agent_execution_context import (
    TOOL_LOAD_SHIFT_DAILY_PROGRESS,
    AgentExecutionContext,
)
from security.trusted_read_executor import (
    ToolPermissionError,
    execute_shift_daily_progress_read,
    validate_context_for_tool,
)


def load_shift_daily_progress(
    context: AgentExecutionContext,
    *,
    crew_id: str,
    work_date: str,
    shift_type: Optional[str] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Narrow READ tool: daily_progress_active for one shift grain."""
    validate_context_for_tool(context, TOOL_LOAD_SHIFT_DAILY_PROGRESS)
    return execute_shift_daily_progress_read(
        context,
        crew_id=crew_id,
        work_date=work_date,
        shift_type=shift_type,
    )


__all__ = [
    "load_shift_daily_progress",
    "ToolPermissionError",
]
