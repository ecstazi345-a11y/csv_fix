"""Professional contours and the digital employees a person can assign.

The orchestrator is an internal coordination mechanism and is not listed here.
Disconnected contours and employees stay visible and cannot be selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


CONSTRUCTOR_AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"
ADMISSION_AGENT_CODE = "ADMISSION_AGENT"
RELEASE_AGENT_CODE = "MONTHLY_COMMITMENT_RELEASE_AGENT"

MONTHLY_CONTOUR_CODE = "MONTHLY_PRODUCTION_COMMITMENT"
EXECUTION_CONTOUR_CODE = "EXECUTION"
RECOGNITION_CONTOUR_CODE = "RECOGNITION"
CAUSALITY_CONTOUR_CODE = "CAUSALITY_ESCALATION"

NOT_CONNECTED_RU = "ещё не подключён"
CONTOUR_NOT_CONNECTED_RU = "ещё не подключено"


@dataclass(frozen=True)
class DigitalEmployee:
    code: str
    title: str
    connected: bool


@dataclass(frozen=True)
class ProfessionalContour:
    code: str
    title: str
    connected: bool
    employees: tuple[DigitalEmployee, ...] = ()


CONTOURS: tuple[ProfessionalContour, ...] = (
    ProfessionalContour(
        MONTHLY_CONTOUR_CODE,
        "Месячное производственное обязательство",
        True,
        (
            DigitalEmployee(
                CONSTRUCTOR_AGENT_CODE,
                "Инженер формирования месячного плана",
                True,
            ),
            DigitalEmployee(
                ADMISSION_AGENT_CODE,
                "Инженер производственной готовности и допуска",
                False,
            ),
            DigitalEmployee(
                RELEASE_AGENT_CODE,
                "Координатор выпуска месячного производственного обязательства",
                False,
            ),
        ),
    ),
    ProfessionalContour(EXECUTION_CONTOUR_CODE, "Исполнение", False),
    ProfessionalContour(RECOGNITION_CONTOUR_CODE, "Признание", False),
    ProfessionalContour(CAUSALITY_CONTOUR_CODE, "Причинность и эскалация", False),
)


def connected_contours() -> tuple[ProfessionalContour, ...]:
    return tuple(item for item in CONTOURS if item.connected)


def contour_by_code(code: Optional[str]) -> Optional[ProfessionalContour]:
    for item in CONTOURS:
        if item.code == code:
            return item
    return None


def contour_title(code: Optional[str]) -> str:
    item = contour_by_code(code)
    return item.title if item is not None else "—"


def contour_option_label(item: ProfessionalContour) -> str:
    """User-facing dropdown label. The internal code stays on the contour."""
    if item.connected:
        return item.title
    return f"{item.title} — {CONTOUR_NOT_CONNECTED_RU}"


def employee_option_label(item: DigitalEmployee) -> str:
    if item.connected:
        return item.title
    return f"{item.title} — {NOT_CONNECTED_RU}"


def contour_from_option_label(label: Optional[str]) -> Optional[ProfessionalContour]:
    for item in CONTOURS:
        if contour_option_label(item) == label:
            return item
    return None


def employee_from_option_label(
    label: Optional[str],
    contour_code: Optional[str],
) -> Optional[DigitalEmployee]:
    for item in employees_of(contour_code):
        if employee_option_label(item) == label:
            return item
    return None


def employees_of(contour_code: Optional[str]) -> tuple[DigitalEmployee, ...]:
    item = contour_by_code(contour_code)
    if item is None:
        return ()
    return item.employees


def employee_by_code(code: Optional[str]) -> Optional[DigitalEmployee]:
    for contour in CONTOURS:
        for employee in contour.employees:
            if employee.code == code:
                return employee
    return None


def employee_title(code: Optional[str]) -> str:
    item = employee_by_code(code)
    return item.title if item is not None else "—"


def contour_code_for_employee(agent_code: Optional[str]) -> Optional[str]:
    for contour in CONTOURS:
        for employee in contour.employees:
            if employee.code == agent_code:
                return contour.code
    return None


def compact_work_context(
    *,
    project: Optional[str],
    planning_month: Optional[str],
    queue: Optional[str],
    titles: tuple[str, ...],
    discipline: Optional[str],
    systems: tuple[str, ...],
) -> str:
    chunks: list[str] = []
    if project:
        chunks.append(project)
    if planning_month:
        chunks.append(planning_month)
    if queue:
        chunks.append(f"очередь {queue}")
    if titles:
        chunks.append("титулы " + ",".join(titles))
    if discipline:
        chunks.append(discipline.casefold())
    if systems:
        chunks.append(" ".join(systems))
    return " · ".join(chunks)
