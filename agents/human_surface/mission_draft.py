"""
Deterministic mission and follow-up command drafts.

Understands a narrow assignment vocabulary. Does not launch Constructor,
invent missing fields, or treat natural language as authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from agents.human_surface.workforce import (
    CONSTRUCTOR_AGENT_CODE,
    MONTHLY_CONTOUR_CODE,
    contour_code_for_employee,
    contour_title,
    employee_title,
)


CURRENT_CONSTRUCTOR_RUN_ID = "run-76ae10af-69f7-4588-91f5-5b0f5d28052a"

MISSION_COMMAND_PORT_REQUIRED_RU = (
    "Формирование новой миссии из свободного поручения ещё требует Mission Command Port."
)
HITL_COMMAND_PORT_REQUIRED_RU = (
    "Для фиксации решения требуется подключение безопасного HITL Command Port."
)
CONFIRM_COMMAND_PORT_REQUIRED_RU = (
    "Подтверждение итогового пакета требует подключения безопасного Human Confirm Command Port."
)
HANDOFF_COMMAND_PORT_REQUIRED_RU = (
    "Передача будет доступна после подключения профессионального Handoff Command Port."
)
COMMAND_EXECUTION_REQUIRED_RU = (
    "Исполнение команды требует подключения соответствующего Command Port."
)
VOICE_RECEIVED_RU = (
    "Запись получена. Автоматическое распознавание речи в этом инкременте ещё не подключено."
)
GLOBAL_VOICE_RECORDED_RU = (
    "Запись получена. Автоматическое распознавание речи пока не подключено."
)
SEPARATE_ASSIGNMENT_RU = (
    "Новое поручение и текущий запуск — разные состояния. "
    "Ниже показан существующий запуск, не результат этого поручения."
)

_DISCIPLINES = {
    "вентиляция": "Вентиляция",
    "электрика": "Электрика",
    "отопление": "Отопление",
    "водоснабжение": "Водоснабжение",
    "канализация": "Канализация",
}


def discipline_label(value: str) -> str:
    text = str(value or "").strip()
    return _DISCIPLINES.get(text.casefold().replace("ё", "е"), text)

_MONTHS = {
    "январь": "январь",
    "января": "январь",
    "февраль": "февраль",
    "февраля": "февраль",
    "март": "март",
    "марта": "март",
    "апрель": "апрель",
    "апреля": "апрель",
    "май": "май",
    "мая": "май",
    "июнь": "июнь",
    "июня": "июнь",
    "июль": "июль",
    "июля": "июль",
    "август": "август",
    "августа": "август",
    "сентябрь": "сентябрь",
    "сентября": "сентябрь",
    "октябрь": "октябрь",
    "октября": "октябрь",
    "ноябрь": "ноябрь",
    "ноября": "ноябрь",
    "декабрь": "декабрь",
    "декабря": "декабрь",
}

_REQUIRED_FIELDS = (
    "project",
    "queue",
    "titles",
    "discipline",
    "systems",
    "planning_month",
)


class VoiceRecognitionUnavailable(RuntimeError):
    """Speech-to-text is not connected. Never invent a transcript."""


class VoiceInputAdapter(Protocol):
    """Future speech boundary. V0.1 has no implementation."""

    def transcribe(self, payload: bytes) -> str:
        """Return recognized text. Must fail closed when recognition is absent."""


@dataclass(frozen=True)
class MissionDraft:
    agent_code: str
    project: Optional[str]
    queue: Optional[str]
    titles: tuple[str, ...]
    discipline: Optional[str]
    systems: tuple[str, ...]
    planning_month: Optional[str]
    unresolved_fields: tuple[str, ...]
    source_text: str


@dataclass(frozen=True)
class CommandIntent:
    action: str
    count: Optional[int]
    target_agent: Optional[str]
    target_month: Optional[str]
    work_ids: tuple[str, ...]


@dataclass(frozen=True)
class CommandDraft:
    intents: tuple[CommandIntent, ...]
    unresolved_fields: tuple[str, ...]
    source_text: str


def parse_mission_text(
    text: str,
    *,
    agent_code: str = CONSTRUCTOR_AGENT_CODE,
) -> MissionDraft:
    """Parse one assignment. Unrecognized required fields stay unresolved."""
    source = str(text or "").strip()
    project = _labeled_project(source)
    queue = _queue(source)
    titles = _titles(source)
    discipline = _discipline(source)
    systems = _labeled_systems(source)
    month = _month(source)
    for segment in _segments(source):
        if project is None:
            project = _bare_project(segment)
        if queue is None:
            queue = _queue(segment)
        if not titles:
            titles = _titles(segment)
        if discipline is None:
            discipline = _discipline(segment)
        if not systems:
            systems = _system_segment(segment)
        if month is None:
            month = _month(segment)
    values = {
        "project": project,
        "queue": queue,
        "titles": titles,
        "discipline": discipline,
        "systems": systems,
        "planning_month": month,
    }
    unresolved = tuple(name for name in _REQUIRED_FIELDS if not values[name])
    return MissionDraft(
        agent_code=agent_code,
        project=project,
        queue=queue,
        titles=titles,
        discipline=discipline,
        systems=systems,
        planning_month=month,
        unresolved_fields=unresolved,
        source_text=source,
    )


def parse_command_text(text: str) -> CommandDraft:
    """Parse a follow-up command into formal intents. Do not invent a missing count."""
    source = str(text or "").strip()
    folded = source.casefold().replace("ё", "е")
    intents: list[CommandIntent] = []
    unresolved: list[str] = []
    if "переда" in folded or "агенту допуска" in folded:
        intents.append(
            CommandIntent(
                action="HANDOFF",
                count=_first_count(folded),
                target_agent="MONTHLY_PLAN_ADMISSION_AGENT",
                target_month=None,
                work_ids=_boq_codes(source),
            )
        )
        if _first_count(folded) is None:
            unresolved.append("handoff_count")
    if "перенес" in folded:
        intents.append(
            CommandIntent(
                action="DEFER",
                count=None if "остальн" in folded else _last_count(folded),
                target_agent=None,
                target_month=_month(source),
                work_ids=(),
            )
        )
        if "остальн" in folded:
            unresolved.append("defer_count")
        if _month(source) is None:
            unresolved.append("defer_month")
    if not intents and ("подтверд" in folded or "соглас" in folded):
        intents.append(
            CommandIntent(
                action="APPROVE",
                count=_first_count(folded),
                target_agent=None,
                target_month=None,
                work_ids=_boq_codes(source),
            )
        )
    if not intents:
        unresolved.append("action")
    return CommandDraft(
        intents=tuple(intents),
        unresolved_fields=tuple(dict.fromkeys(unresolved)),
        source_text=source,
    )


def mission_draft_lines(draft: MissionDraft) -> tuple[tuple[str, str], ...]:
    return (
        ("Проект", draft.project or "—"),
        ("Очередь", draft.queue or "—"),
        ("Титулы", ", ".join(draft.titles) if draft.titles else "—"),
        ("Дисциплина", draft.discipline or "—"),
        ("Системы", ", ".join(draft.systems) if draft.systems else "—"),
        ("Горизонт", draft.planning_month or "—"),
    )


def command_draft_lines(draft: CommandDraft) -> tuple[str, ...]:
    lines: list[str] = []
    for intent in draft.intents:
        if intent.action == "HANDOFF":
            subject = f"{intent.count} работ" if intent.count is not None else "работы без указанного числа"
            lines.append(f"{subject} → передать Агенту допуска")
        elif intent.action == "DEFER":
            subject = f"{intent.count} работ" if intent.count is not None else "остальные"
            month = intent.target_month or "неопределённый месяц"
            lines.append(f"{subject} → перенести на {month}")
        elif intent.action == "APPROVE":
            subject = f"{intent.count} работ" if intent.count is not None else "работы"
            lines.append(f"{subject} → согласовать")
    return tuple(lines)


def _segments(text: str) -> tuple[str, ...]:
    if "/" not in text:
        return ()
    return tuple(part.strip(" «»\"',.") for part in text.split("/") if part.strip())


def _labeled_project(text: str) -> Optional[str]:
    folded = text.casefold()
    marker = "проект"
    start = folded.find(marker)
    if start < 0:
        return None
    tail = text[start + len(marker):].lstrip(" уеа:")
    token = tail.split()[0].strip(" ,.;") if tail.split() else ""
    if token and _is_project_token(token):
        return token
    return None


def _bare_project(segment: str) -> Optional[str]:
    token = segment.strip()
    if " " in token or not _is_project_token(token):
        return None
    if token.casefold() in _DISCIPLINES or _system_tokens(token):
        return None
    return token


def _is_project_token(token: str) -> bool:
    if not token or not token[0].isalpha():
        return False
    return all(char.isalnum() or char in "_-" for char in token)


_ORDINAL_PREFIXES = (
    ("одиннадцат", "11"),
    ("двенадцат", "12"),
    ("тринадцат", "13"),
    ("четырнадцат", "14"),
    ("пятнадцат", "15"),
    ("перв", "1"),
    ("втор", "2"),
    ("трет", "3"),
    ("четвер", "4"),
    ("пят", "5"),
    ("шест", "6"),
    ("седьм", "7"),
    ("восьм", "8"),
    ("девят", "9"),
    ("десят", "10"),
)


def _ordinal_number(word: str) -> Optional[str]:
    for prefix, number in _ORDINAL_PREFIXES:
        if word.startswith(prefix):
            return number
    return None


def _queue(text: str) -> Optional[str]:
    folded = text.casefold().replace("ё", "е")
    words = folded.replace(",", " ").split()
    for index, word in enumerate(words):
        if not word.startswith("очеред"):
            continue
        for distance in (1, 2, 3):
            neighbors = []
            if index - distance >= 0:
                neighbors.append(words[index - distance])
            if index + distance < len(words):
                neighbors.append(words[index + distance])
            for neighbor in neighbors:
                ordinal = _ordinal_number(neighbor)
                if ordinal is not None:
                    return ordinal
                if neighbor.isdigit() and len(neighbor) <= 2:
                    return neighbor
    return None


def _titles(text: str) -> tuple[str, ...]:
    folded = text.casefold()
    marker = "титул"
    start = folded.find(marker)
    if start < 0:
        return ()
    tail = text[start:]
    end = len(tail)
    folded_tail = tail.casefold().replace("ё", "е")
    stoppers = ["дисциплин", "систем", " /", " на ", ". ", *_DISCIPLINES]
    for stopper in stoppers:
        found = folded_tail.find(stopper)
        if found > 0:
            end = min(end, found)
    words: list[str] = []
    for word in tail[:end].replace(",", " ").split():
        cleaned = word.strip(" .;")
        if _is_system_code(cleaned):
            break
        words.append(cleaned)
    chunk = " ".join(words)
    numbers = []
    current = ""
    for char in chunk:
        if char.isdigit():
            current += char
        elif current:
            numbers.append(current)
            current = ""
    if current:
        numbers.append(current)
    return tuple(dict.fromkeys(numbers))


def _discipline(text: str) -> Optional[str]:
    folded = text.casefold().replace("ё", "е")
    for key, label in _DISCIPLINES.items():
        if key in folded:
            return label
    return None


def _labeled_systems(text: str) -> tuple[str, ...]:
    folded = text.casefold()
    marker = "систем"
    start = folded.find(marker)
    if start < 0:
        return ()
    tail = text[start:]
    end = len(tail)
    for stopper in (", на ", " /", ", дисциплин"):
        found = tail.casefold().find(stopper)
        if found > 0:
            end = min(end, found)
    return _system_tokens(tail[:end])


def _system_segment(segment: str) -> tuple[str, ...]:
    tokens = segment.split()
    if not tokens:
        return ()
    codes = _system_tokens(segment)
    if len(codes) == len(tokens):
        return codes
    return ()


def _system_tokens(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for raw in text.replace(",", " ").split():
        token = raw.strip(" .;")
        if _is_system_code(token):
            found.append(token.upper() if token.isascii() else token)
    return tuple(dict.fromkeys(found))


def _is_system_code(token: str) -> bool:
    if "-" in token:
        head, _, tail = token.partition("-")
        return head.isalpha() and tail.isdigit() and 1 <= len(head) <= 6
    digits = ""
    letters = ""
    for char in token:
        if char.isdigit():
            digits += char
        elif char.isalpha():
            if digits:
                return False
            letters += char
        else:
            return False
    return bool(letters and digits) and len(letters) <= 6


def _month(text: str) -> Optional[str]:
    words = text.casefold().replace("ё", "е").replace(",", " ").split()
    for index, word in enumerate(words):
        name = _MONTHS.get(word.strip("."))
        if name is None:
            continue
        for neighbor in words[index + 1:index + 3]:
            year = neighbor.strip(".")
            if len(year) == 4 and year.isdigit() and year.startswith("20"):
                return f"{name} {year}"
    return None


def _first_count(folded: str) -> Optional[int]:
    for word in folded.replace(",", " ").split():
        if word.isdigit():
            return int(word)
    return None


def _last_count(folded: str) -> Optional[int]:
    found: Optional[int] = None
    for word in folded.replace(",", " ").split():
        if word.isdigit():
            found = int(word)
    return found


_MONTH_GENITIVE = {
    "январь": "января",
    "февраль": "февраля",
    "март": "марта",
    "апрель": "апреля",
    "май": "мая",
    "июнь": "июня",
    "июль": "июля",
    "август": "августа",
    "сентябрь": "сентября",
    "октябрь": "октября",
    "ноябрь": "ноября",
    "декабрь": "декабря",
}

_CONTEXT_INTENT = "Сформировать кандидатный состав месячного плана."


@dataclass(frozen=True)
class WorkAction:
    position: int
    action: str
    target_month: Optional[str] = None


@dataclass(frozen=True)
class GlobalCommandDraft:
    """Parsed global command. Not authority and not a runtime write."""

    kind: str
    project: Optional[str]
    planning_month: Optional[str]
    queue: Optional[str]
    titles: tuple[str, ...]
    discipline: Optional[str]
    agent_code: Optional[str]
    included_systems: tuple[str, ...]
    excluded_scope_rule: Optional[str]
    intent: Optional[str]
    work_actions: tuple[WorkAction, ...]
    next_agent: Optional[str]
    unresolved_fields: tuple[str, ...]
    source_text: str = ""
    contour_code: Optional[str] = None


@dataclass(frozen=True)
class WorkingContext:
    """Formal fields shared by the manual surface and the global command."""

    project: Optional[str] = None
    planning_month: Optional[str] = None
    queue: Optional[str] = None
    titles: tuple[str, ...] = ()
    discipline: Optional[str] = None
    systems: tuple[str, ...] = ()
    packages: Optional[str] = None
    agent_code: Optional[str] = None
    excluded_scope_rule: Optional[str] = None
    intent: Optional[str] = None
    contour_code: Optional[str] = None


def empty_working_context() -> WorkingContext:
    return WorkingContext(
        agent_code=CONSTRUCTOR_AGENT_CODE,
        contour_code=MONTHLY_CONTOUR_CODE,
    )


@dataclass(frozen=True)
class ContextOptionSets:
    """Selectable values already known. Empty means the control stays disabled."""

    projects: tuple[str, ...] = ()
    months: tuple[str, ...] = ()
    queues: tuple[str, ...] = ()
    titles: tuple[str, ...] = ()
    disciplines: tuple[str, ...] = ()
    systems: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()


def merge_context_options(observed: ContextOptionSets, context: WorkingContext) -> ContextOptionSets:
    """Union of stored facts and the current formal context. Nothing else is added."""
    return ContextOptionSets(
        projects=_option_values(observed.projects, context.project),
        months=_option_values(observed.months, context.planning_month),
        queues=_option_values(observed.queues, context.queue),
        titles=_option_values(observed.titles, context.titles),
        disciplines=_option_values(observed.disciplines, context.discipline),
        systems=_option_values(observed.systems, context.systems),
        packages=_option_values(observed.packages, context.packages),
    )


def _option_values(*groups: object) -> tuple[str, ...]:
    found: list[str] = []
    for group in groups:
        if group is None:
            continue
        items = group if isinstance(group, (tuple, list)) else (group,)
        for item in items:
            text = str(item or "").strip()
            if not text or text in {"—", "-"} or text in found:
                continue
            found.append(text)
    return tuple(found)


def parse_global_command(
    text: str,
    *,
    horizon_year: Optional[str] = None,
) -> GlobalCommandDraft:
    """Parse one global text command. Missing pieces stay unresolved."""
    source = str(text or "").strip()
    folded = source.casefold().replace("ё", "е")
    if _is_work_command(folded):
        return _parse_work_command(source, folded, horizon_year=horizon_year)
    return _parse_context_command(source, folded)


def apply_global_command(current: WorkingContext, draft: GlobalCommandDraft) -> WorkingContext:
    """Copy recognized context fields. Work commands do not change the context."""
    if draft.kind != "context":
        return current
    return WorkingContext(
        project=draft.project or current.project,
        planning_month=draft.planning_month or current.planning_month,
        queue=draft.queue or current.queue,
        titles=draft.titles or current.titles,
        discipline=draft.discipline or current.discipline,
        systems=draft.included_systems or current.systems,
        packages=current.packages,
        agent_code=draft.agent_code or current.agent_code,
        excluded_scope_rule=draft.excluded_scope_rule or current.excluded_scope_rule,
        intent=draft.intent or current.intent,
        contour_code=draft.contour_code or current.contour_code,
    )


_LAUNCH_REQUIRED_FIELDS = (
    "project",
    "planning_month",
)


def mission_from_context(context: WorkingContext, source_text: str = "") -> MissionDraft:
    """Formal workspace draft. Empty scope filters stay empty and mean unrestricted."""
    values = {
        "project": context.project,
        "planning_month": context.planning_month,
    }
    unresolved = tuple(name for name in _LAUNCH_REQUIRED_FIELDS if not values[name])
    return MissionDraft(
        agent_code=context.agent_code or CONSTRUCTOR_AGENT_CODE,
        project=context.project,
        queue=context.queue,
        titles=context.titles,
        discipline=context.discipline,
        systems=context.systems,
        planning_month=context.planning_month,
        unresolved_fields=unresolved,
        source_text=source_text,
    )


def global_command_preview_lines(draft: GlobalCommandDraft) -> tuple[str, ...]:
    if draft.kind == "work":
        return _work_preview_lines(draft)
    agent = employee_title(draft.agent_code) if draft.agent_code else "—"
    month_name = (draft.planning_month or "").split(" ")[0] or "этот месяц"
    lines = [
        f"Контур: {contour_title(draft.contour_code) if draft.contour_code else '—'}",
        f"Цифровой сотрудник: {agent}",
        f"Проект: {draft.project or '—'}",
        f"Месяц: {draft.planning_month or '—'}",
        f"Очередь: {draft.queue or '—'}",
        f"Титулы: {', '.join(draft.titles) if draft.titles else '—'}",
        f"Дисциплина: {draft.discipline or '—'}",
        f"Системы: {', '.join(draft.included_systems) if draft.included_systems else '—'}",
    ]
    if draft.excluded_scope_rule:
        lines.append(f"Правило: остальные системы в {month_name} не включать.")
    if draft.intent:
        lines.append(f"Поручение: {draft.intent[:1].lower() + draft.intent[1:]}")
    return tuple(lines)


def _parse_context_command(source: str, folded: str) -> GlobalCommandDraft:
    project = _labeled_project(source) or _leading_project(source)
    month = _month(source)
    queue = _queue(source)
    titles = _titles(source)
    discipline = _discipline(source)
    systems = _included_systems(source)
    agent = _recognized_agent(folded)
    contour = _recognized_contour(folded) or contour_code_for_employee(agent)
    excluded = _excluded_scope_rule(folded, month)
    intent = _CONTEXT_INTENT if ("сформир" in folded and "план" in folded) else None
    values = {
        "project": project,
        "planning_month": month,
        "queue": queue,
        "titles": titles,
        "discipline": discipline,
        "included_systems": systems,
        "agent": agent,
    }
    unresolved = tuple(name for name, value in values.items() if not value)
    if "остальн" in folded and "систем" in folded and excluded is None:
        unresolved = unresolved + ("excluded_scope",)
    return GlobalCommandDraft(
        kind="context",
        project=project,
        planning_month=month,
        queue=queue,
        titles=titles,
        discipline=discipline,
        agent_code=agent,
        included_systems=systems,
        excluded_scope_rule=excluded,
        intent=intent,
        work_actions=(),
        next_agent=None,
        unresolved_fields=unresolved,
        source_text=source,
        contour_code=contour,
    )


def _parse_work_command(
    source: str,
    folded: str,
    *,
    horizon_year: Optional[str],
) -> GlobalCommandDraft:
    actions: list[WorkAction] = []
    unresolved: list[str] = []
    for sentence in _sentences(source):
        ordinals = _ordinals_in(sentence)
        if not ordinals:
            continue
        action = _clause_action(sentence)
        if action is None:
            unresolved.append("work_action")
            continue
        target_month = None
        if action == "DEFER":
            target_month = _month(sentence) or _bare_month(sentence, horizon_year)
            if target_month is None:
                unresolved.append("defer_month")
        for position in ordinals:
            actions.append(WorkAction(position=int(position), action=action, target_month=target_month))
    next_agent = "ADMISSION" if ("допуск" in folded and "переда" in folded) else None
    if not actions:
        unresolved.append("work_action")
    return GlobalCommandDraft(
        kind="work",
        project=None,
        planning_month=None,
        queue=None,
        titles=(),
        discipline=None,
        agent_code=None,
        included_systems=(),
        excluded_scope_rule=None,
        intent=None,
        work_actions=tuple(actions),
        next_agent=next_agent,
        unresolved_fields=tuple(dict.fromkeys(unresolved)),
        source_text=source,
    )


def _is_work_command(folded: str) -> bool:
    words = folded.replace(",", " ").split()
    has_position = False
    for index, word in enumerate(words):
        if _ordinal_number(word.strip(".")) is None:
            continue
        window = words[max(0, index - 2):index + 3]
        if any(item.startswith("очеред") for item in window):
            continue
        has_position = True
        break
    if not has_position:
        return False
    return any(token in folded for token in ("соглас", "не включ", "перенес", "исключ", "позиц"))


def _sentences(text: str) -> tuple[str, ...]:
    parts = []
    current = []
    for char in text:
        current.append(char)
        if char in ".!;":
            piece = "".join(current).strip()
            if piece:
                parts.append(piece)
            current = []
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return tuple(parts)


def _ordinals_in(text: str) -> tuple[str, ...]:
    folded = text.casefold().replace("ё", "е")
    found = []
    for word in folded.replace(",", " ").split():
        number = _ordinal_number(word.strip("."))
        if number is not None:
            found.append(number)
    return tuple(dict.fromkeys(found))


def _clause_action(sentence: str) -> Optional[str]:
    folded = sentence.casefold().replace("ё", "е")
    if "не включ" in folded or "исключ" in folded:
        return "REJECT"
    if "перенес" in folded:
        return "DEFER"
    if "соглас" in folded:
        return "APPROVE"
    return None


def _bare_month(text: str, horizon_year: Optional[str]) -> Optional[str]:
    if not horizon_year or not str(horizon_year).isdigit():
        return None
    folded = text.casefold().replace("ё", "е")
    for word in folded.replace(",", " ").split():
        name = _MONTHS.get(word.strip("."))
        if name is not None:
            return f"{name} {horizon_year}"
    return None


def _included_systems(text: str) -> tuple[str, ...]:
    folded = text.casefold().replace("ё", "е")
    stop = folded.find("остальн")
    head = text if stop < 0 else text[:stop]
    labeled = _labeled_systems(head)
    if labeled:
        return labeled
    return _system_tokens(head)


def _recognized_agent(folded: str) -> Optional[str]:
    if "constructor" in folded or "конструктор" in folded:
        return CONSTRUCTOR_AGENT_CODE
    if "формирован" in folded and "месячн" in folded:
        return CONSTRUCTOR_AGENT_CODE
    return None


def _recognized_contour(folded: str) -> Optional[str]:
    if "месячн" in folded and "обязательств" in folded:
        return MONTHLY_CONTOUR_CODE
    return None


def _leading_project(text: str) -> Optional[str]:
    stripped = text.strip()
    if not stripped:
        return None
    token = stripped.split()[0].strip(" ,.;")
    if token.casefold() == "проект" or not _bare_project(token):
        return None
    letters = [char for char in token if char.isalpha()]
    if not letters or not all(char.isupper() for char in letters):
        return None
    return token


def _excluded_scope_rule(folded: str, month: Optional[str]) -> Optional[str]:
    if "остальн" not in folded or "систем" not in folded:
        return None
    if "не включ" not in folded:
        return None
    if not month or " " not in month:
        return None
    name, year = month.split(" ", 1)
    genitive = _MONTH_GENITIVE.get(name)
    if genitive is None:
        return None
    return f"Остальные системы не входят в плановый scope {genitive} {year}."


def _work_preview_lines(draft: GlobalCommandDraft) -> tuple[str, ...]:
    lines: list[str] = []
    for action, label in (
        ("APPROVE", "согласовать"),
        ("REJECT", "не включать"),
    ):
        count = sum(1 for item in draft.work_actions if item.action == action)
        if count:
            lines.append(f"{_ru_works(count)} → {label}")
    defer_months: dict[str, int] = {}
    for item in draft.work_actions:
        if item.action == "DEFER":
            key = item.target_month or "неопределённый месяц"
            defer_months[key] = defer_months.get(key, 0) + 1
    for month, count in defer_months.items():
        lines.append(f"{_ru_works(count)} → перенести на {month}")
    if draft.next_agent == "ADMISSION":
        lines.append("согласованные → подготовить к передаче Агенту допуска")
    return tuple(lines)


def _ru_works(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} работа"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} работы"
    return f"{count} работ"


def _boq_codes(text: str) -> tuple[str, ...]:
    codes = []
    for token in text.replace(",", " ").split():
        cleaned = token.strip(" .;")
        parts = cleaned.split("-")
        if len(parts) >= 3 and all(part.isdigit() for part in parts):
            codes.append(cleaned)
    return tuple(dict.fromkeys(codes))
