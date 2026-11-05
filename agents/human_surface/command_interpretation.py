"""Agent-neutral interpretation of one received human command.

The result is a typed draft for a person to confirm. It is not a bound mission
and it does not launch an agent. Identifiers are taken only from the existing
work-context catalog and checked with ConstructorMissionScope.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from agents.human_surface.mission_draft import (
    WorkingContext,
    parse_global_command,
)
from agents.human_surface.work_context import (
    QUEUE_SOURCE_CANONICAL_TITLE_RELATION,
    WorkContextCatalog,
    align_working_context,
    selector_options,
    unique_queue_for_project_title,
)
from agents.human_surface.workforce import CONSTRUCTOR_AGENT_CODE
from agents.monthly_plan_constructor.mission_scope import (
    MissionScopeError,
    build_constructor_mission_scope,
)
from utils.month_key import format_month_key_ru, normalize_month_key

INTENT_FORM_CANDIDATE_PACKAGE = "FORM_CANDIDATE_PACKAGE"
INTENT_FORM_MONTHLY_COMMITMENT = "FORM_MONTHLY_COMMITMENT"
STATE_NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
STATE_NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
STATE_REJECTED = "REJECTED"
RESOLUTION_INTERPRETED = "INTERPRETED"
_MONTHLY_COMMITMENT_STAGE_NOTE = (
    "Цель понята: месячное обязательство. Scope полностью определён. "
    "Доступный первый этап: Constructor / формирование кандидатного состава. "
    "Месячное обязательство ещё не сформировано. "
    "Ожидается подтверждение начала первого этапа."
)
_MONTHLY_COMMITMENT_INCOMPLETE_NOTE = (
    "Цель: месячное обязательство. Доступный первый этап: Constructor / "
    "формирование кандидатного состава. Месячное обязательство ещё не сформировано."
)

_CONSTRUCTOR_DISPLAY = "Constructor"
_MONTH_NAME = (
    r"январ[а-яё]*|феврал[а-яё]*|март[а-яё]*|апрел[а-яё]*|ма[йя]|июн[а-яё]*|"
    r"июл[а-яё]*|август[а-яё]*|сентябр[а-яё]*|октябр[а-яё]*|ноябр[а-яё]*|декабр[а-яё]*"
)
_DISCIPLINE_STEMS = {
    "автоматика": "автоматизация",
    "автоматизация": "автоматизация",
    "вентиляция": "вентиляция",
    "электрика": "электрика",
    "отопление": "отопление",
    "водоснабжение": "водоснабжение",
    "канализация": "канализация",
    "кондиционирование": "кондиционирование",
}
_REQUIRED = ("project", "period", "queue", "title", "discipline")


@dataclass(frozen=True)
class CommandInterpretation:
    interpretation_id: str
    command_id: str
    target_agent: str
    intent: str
    extracted_scope: dict[str, object]
    resolved_scope: dict[str, str]
    unresolved_fields: tuple[str, ...]
    ambiguities: tuple[str, ...]
    resolution_status: str
    processing_state: str
    created_at: str
    mission_created: bool
    preview: tuple[tuple[str, str], ...]
    headline: str
    status_label: str

    def as_dict(self) -> dict[str, object]:
        return {
            "interpretation_id": self.interpretation_id,
            "command_id": self.command_id,
            "target_agent": self.target_agent,
            "intent": self.intent,
            "extracted_scope": self.extracted_scope,
            "resolved_scope": self.resolved_scope,
            "unresolved_fields": list(self.unresolved_fields),
            "ambiguities": list(self.ambiguities),
            "resolution_status": self.resolution_status,
            "processing_state": self.processing_state,
            "created_at": self.created_at,
            "mission_created": False,
            "preview": [list(item) for item in self.preview],
            "headline": self.headline,
            "status_label": self.status_label,
        }


def interpret_command(
    *,
    command_id: str,
    raw_text: str,
    catalog: WorkContextCatalog,
    forced_intent: Optional[str] = None,
) -> CommandInterpretation:
    """Resolve one command against the catalog. Untrusted text is data only."""
    source = str(raw_text or "").strip()
    prepared = _prepare_month_hyphen(source)
    folded = prepared.casefold().replace("ё", "е")
    intent = _select_intent(folded, forced_intent)
    if intent is None and not _looks_like_assignment(folded):
        return _finish(
            command_id=command_id,
            target_agent="",
            intent="",
            extracted={},
            resolved={},
            unresolved=(),
            ambiguities=(),
            state=STATE_REJECTED,
            resolution="REJECTED",
            headline="Черновик миссии не создан",
            status_label="Отклонено",
        )
    if intent is None:
        return _finish(
            command_id=command_id,
            target_agent="",
            intent="",
            extracted={"text": source},
            resolved={},
            unresolved=("intent",),
            ambiguities=(),
            state=STATE_NEEDS_CLARIFICATION,
            resolution="INCOMPLETE",
            headline="Нужно уточнение",
            status_label="Нужно уточнение",
        )

    parsed = parse_global_command(prepared)
    project_token, project = _resolve_project(prepared, catalog)
    month_token = parsed.planning_month or ""
    month_key, planning_month = _resolve_month(month_token, catalog)
    queue_token = parsed.queue or _queue_extra(prepared)
    queue = _resolve_queue(queue_token, catalog, project[0] if project else "")
    spoken_titles = _spoken_titles(prepared, parsed.titles)
    title, title_ambiguity, title_missing = _resolve_title(
        catalog,
        project_label=project[0] if project else "",
        queue=queue,
        spoken=spoken_titles,
    )
    queue_source = ""
    if not queue and title and project is not None and not title_ambiguity:
        inferred = unique_queue_for_project_title(
            catalog,
            title=title,
            project_label=project[0],
            project_code=project[1],
        )
        if inferred:
            queue = inferred
            queue_source = QUEUE_SOURCE_CANONICAL_TITLE_RELATION
    discipline_token, discipline, discipline_ambiguity = _resolve_discipline(
        folded,
        catalog,
        project_label=project[0] if project else "",
        queue=queue,
        title=title,
    )
    extracted = {
        "project_token": project_token,
        "month_token": month_token,
        "queue_token": queue_token,
        "title_tokens": list(spoken_titles),
        "discipline_token": discipline_token,
    }
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    ambiguities: list[str] = []
    if project is None:
        unresolved.append("project")
    else:
        resolved["project_code"] = project[1]
        resolved["project_label"] = project[0]
    if not month_key:
        unresolved.append("period")
    else:
        resolved["month_key"] = month_key
        resolved["planning_month"] = planning_month
    if not queue:
        unresolved.append("queue")
    else:
        resolved["queue"] = queue
        if queue_source:
            resolved["queue_source"] = queue_source
    if title_ambiguity:
        ambiguities.append(title_ambiguity)
    elif not title:
        unresolved.append("title")
    else:
        resolved["facility"] = title
    if discipline_ambiguity:
        ambiguities.append(discipline_ambiguity)
    elif not discipline:
        unresolved.append("discipline")
    else:
        resolved["discipline"] = discipline
    if title_missing:
        unresolved.append("title")

    if intent == INTENT_FORM_MONTHLY_COMMITMENT:
        return _finish_monthly_commitment(
            command_id=command_id,
            extracted=extracted,
            resolved=resolved,
            unresolved=unresolved,
            ambiguities=ambiguities,
            title_ambiguity=title_ambiguity,
            discipline_ambiguity=discipline_ambiguity,
        )

    if not unresolved and not ambiguities:
        try:
            scope = build_constructor_mission_scope(
                project_code=resolved["project_code"],
                month_key=resolved["month_key"],
                facility_scope=(resolved["facility"],),
                discipline_scope=(resolved["discipline"],),
                queue_scope=(resolved["queue"],),
            )
        except MissionScopeError:
            unresolved.append("scope")
        else:
            resolved["project_code"] = scope.project_code
            resolved["month_key"] = format_month_key_ru(scope.month_key_canonical) or resolved["month_key"]
            preview = (
                ("Агент", _CONSTRUCTOR_DISPLAY),
                ("Проект", f"{resolved['project_code']} / {resolved['project_label']}"),
                ("Период", resolved["planning_month"]),
                ("Очередь", resolved["queue"]),
                ("Титул", resolved["facility"]),
                ("Дисциплина", resolved["discipline"]),
                ("Статус", "Ожидается подтверждение"),
            )
            return _finish(
                command_id=command_id,
                target_agent=CONSTRUCTOR_AGENT_CODE,
                intent=intent,
                extracted=extracted,
                resolved=resolved,
                unresolved=(),
                ambiguities=(),
                state=STATE_NEEDS_CONFIRMATION,
                resolution=RESOLUTION_INTERPRETED,
                headline="Поручение понято",
                status_label="Ожидается подтверждение",
                preview=preview,
            )
    return _finish(
        command_id=command_id,
        target_agent=CONSTRUCTOR_AGENT_CODE,
        intent=intent,
        extracted=extracted,
        resolved=resolved,
        unresolved=tuple(dict.fromkeys(unresolved)),
        ambiguities=tuple(dict.fromkeys(ambiguities)),
        state=STATE_NEEDS_CLARIFICATION,
        resolution="AMBIGUOUS" if ambiguities else "INCOMPLETE",
        headline="Нужно уточнение",
        status_label="Нужно уточнение",
        preview=_partial_preview(resolved),
    )


def _finish(
    *,
    command_id: str,
    target_agent: str,
    intent: str,
    extracted: dict[str, object],
    resolved: dict[str, str],
    unresolved: tuple[str, ...],
    ambiguities: tuple[str, ...],
    state: str,
    resolution: str,
    headline: str,
    status_label: str,
    preview: tuple[tuple[str, str], ...] = (),
) -> CommandInterpretation:
    return CommandInterpretation(
        interpretation_id=str(uuid4()),
        command_id=command_id,
        target_agent=target_agent,
        intent=intent,
        extracted_scope=extracted,
        resolved_scope=resolved,
        unresolved_fields=unresolved,
        ambiguities=ambiguities,
        resolution_status=resolution,
        processing_state=state,
        created_at=datetime.now(timezone.utc).isoformat(),
        mission_created=False,
        preview=preview,
        headline=headline,
        status_label=status_label,
    )


def _finish_monthly_commitment(
    *,
    command_id: str,
    extracted: dict[str, object],
    resolved: dict[str, str],
    unresolved: list[str],
    ambiguities: list[str],
    title_ambiguity: str,
    discipline_ambiguity: str,
) -> CommandInterpretation:
    """Monthly Commitment goal is not Candidate Package and is never auto-formed."""
    open_scope = bool(unresolved) or bool(title_ambiguity) or bool(discipline_ambiguity)
    if not open_scope:
        try:
            scope = build_constructor_mission_scope(
                project_code=resolved["project_code"],
                month_key=resolved["month_key"],
                facility_scope=(resolved["facility"],),
                discipline_scope=(resolved["discipline"],),
                queue_scope=(resolved["queue"],),
            )
        except MissionScopeError:
            unresolved.append("scope")
            open_scope = True
        else:
            resolved["project_code"] = scope.project_code
            resolved["month_key"] = (
                format_month_key_ru(scope.month_key_canonical) or resolved["month_key"]
            )
            return _finish(
                command_id=command_id,
                target_agent=CONSTRUCTOR_AGENT_CODE,
                intent=INTENT_FORM_MONTHLY_COMMITMENT,
                extracted=extracted,
                resolved=resolved,
                unresolved=(),
                ambiguities=(),
                state=STATE_NEEDS_CONFIRMATION,
                resolution=RESOLUTION_INTERPRETED,
                headline="Цель понята: месячное обязательство",
                status_label="Ожидается подтверждение начала первого этапа",
                preview=_monthly_ready_preview(resolved),
            )
    notes = list(ambiguities)
    notes.append(_MONTHLY_COMMITMENT_INCOMPLETE_NOTE)
    return _finish(
        command_id=command_id,
        target_agent=CONSTRUCTOR_AGENT_CODE,
        intent=INTENT_FORM_MONTHLY_COMMITMENT,
        extracted=extracted,
        resolved=resolved,
        unresolved=tuple(dict.fromkeys(unresolved)),
        ambiguities=tuple(dict.fromkeys(notes)),
        state=STATE_NEEDS_CLARIFICATION,
        resolution="AMBIGUOUS" if title_ambiguity or discipline_ambiguity else "INCOMPLETE",
        headline="Цель: месячное обязательство",
        status_label="Нужно уточнение",
        preview=_partial_preview(resolved, monthly_commitment=True),
    )


def _monthly_ready_preview(resolved: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return (
        ("Цель", "Месячное обязательство"),
        ("Scope", "Полностью определён"),
        ("Первый этап", "Constructor / формирование кандидатного состава"),
        ("Агент", _CONSTRUCTOR_DISPLAY),
        ("Проект", f"{resolved['project_code']} / {resolved['project_label']}"),
        ("Период", resolved["planning_month"]),
        ("Очередь", resolved["queue"]),
        ("Титул", resolved["facility"]),
        ("Дисциплина", resolved["discipline"]),
        ("Закон", "Месячное обязательство ещё не сформировано"),
        ("Статус", "Ожидается подтверждение начала первого этапа"),
    )


def _partial_preview(
    resolved: dict[str, str],
    *,
    monthly_commitment: bool = False,
) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = [("Агент", _CONSTRUCTOR_DISPLAY)]
    if monthly_commitment:
        rows.append(("Цель", "Месячное обязательство"))
        rows.append(("Первый этап", "Constructor / формирование кандидатного состава"))
    if resolved.get("project_code"):
        rows.append(("Проект", f"{resolved['project_code']} / {resolved['project_label']}"))
    if resolved.get("planning_month"):
        rows.append(("Период", resolved["planning_month"]))
    if resolved.get("queue"):
        rows.append(("Очередь", resolved["queue"]))
    if resolved.get("facility"):
        rows.append(("Титул", resolved["facility"]))
    if resolved.get("discipline"):
        rows.append(("Дисциплина", resolved["discipline"]))
    rows.append(("Статус", "Нужно уточнение"))
    return tuple(rows)


def _select_intent(folded: str, forced_intent: Optional[str]) -> Optional[str]:
    if forced_intent is not None:
        text = str(forced_intent or "").strip()
        if text in {INTENT_FORM_CANDIDATE_PACKAGE, INTENT_FORM_MONTHLY_COMMITMENT}:
            return text
        if text == "":
            return None
        return None
    return _constructor_intent(folded)


def _constructor_intent(folded: str) -> Optional[str]:
    form = any(stem in folded for stem in ("сформир", "собер", "подготов"))
    if form and "обязательств" in folded:
        return INTENT_FORM_MONTHLY_COMMITMENT
    if form and "кандидат" in folded:
        return INTENT_FORM_CANDIDATE_PACKAGE
    if form and ("месячн" in folded or "месяц" in folded) and "план" in folded:
        return INTENT_FORM_CANDIDATE_PACKAGE
    if "конструктор" in folded or "constructor" in folded:
        return INTENT_FORM_CANDIDATE_PACKAGE
    return None


def _looks_like_assignment(folded: str) -> bool:
    markers = ("сформир", "собер", "подготов", "проект", "титул", "очеред", "дисциплин")
    return any(marker in folded for marker in markers)


def _prepare_month_hyphen(text: str) -> str:
    return re.sub(
        rf"({_MONTH_NAME})\s*-\s*(20\d{{2}})",
        r"\1 \2",
        text,
        flags=re.IGNORECASE,
    )


def _tokens(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for raw in text.replace(",", " ").replace(";", " ").split():
        token = raw.strip(" .;:\"'«»()[]")
        if token:
            found.append(token)
    return tuple(found)


def _resolve_project(
    text: str,
    catalog: WorkContextCatalog,
) -> tuple[str, Optional[tuple[str, str]]]:
    by_label: dict[str, set[tuple[str, str]]] = {}
    for fact in catalog.facts:
        label = str(fact.project_label or "").strip()
        code = str(fact.project_code or "").strip()
        if not label or not code:
            continue
        by_label.setdefault(label.casefold(), set()).add((label, code))
    explicit = _explicit_project_token(text)
    tokens = list(_tokens(text))
    if explicit and explicit not in tokens:
        tokens.append(explicit)
    matched: list[tuple[str, str]] = []
    unknown = ""
    for token in tokens:
        pairs = by_label.get(token.casefold())
        if pairs is None:
            if explicit and token.casefold() == explicit.casefold():
                unknown = token
            continue
        matched.extend(pairs)
    unique = tuple(dict.fromkeys(matched))
    if unknown or len(unique) != 1:
        return unknown or explicit, None
    return unique[0][0], unique[0]


def _explicit_project_token(text: str) -> str:
    found = re.search(
        r"проект[а-яё]*\s+([0-9A-Za-zА-Яа-яЁё_-]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not found:
        return ""
    return found.group(1).strip(" .;,")


def _resolve_month(token: str, catalog: WorkContextCatalog) -> tuple[str, str]:
    text = str(token or "").strip()
    if not text:
        return "", ""
    normalized = text.replace("-", " ")
    if normalized not in catalog.months:
        return "", ""
    canonical = normalize_month_key(normalized.replace(" ", "-"))
    stored = format_month_key_ru(canonical) if canonical else None
    if not stored:
        return "", ""
    return stored, normalized


def _queue_extra(text: str) -> str:
    folded = text.casefold().replace("ё", "е")
    found = re.search(r"(?<!\d)([12])\s*[-–]?\s*[яй]?(?=\s*очеред)", folded)
    if found:
        return found.group(1)
    return ""


def _resolve_queue(token: str, catalog: WorkContextCatalog, project_label: str) -> str:
    text = str(token or "").strip()
    if not text or not project_label:
        return ""
    options = selector_options(catalog, project=project_label).queues
    if text in options:
        return text
    return ""


def _spoken_titles(text: str, parsed: tuple[str, ...]) -> tuple[str, ...]:
    codes = tuple(dict.fromkeys(re.findall(r"(?<!\d)(\d{4,6}-\d{2,3})(?!\d)", text)))
    if codes:
        return codes
    return tuple(parsed)


def _resolve_title(
    catalog: WorkContextCatalog,
    *,
    project_label: str,
    queue: str,
    spoken: tuple[str, ...],
) -> tuple[str, str, bool]:
    if not spoken or not project_label:
        return "", "", bool(spoken)
    context = WorkingContext(project=project_label, queue=queue or None, titles=spoken)
    alignment = align_working_context(context, catalog)
    if alignment.messages:
        return "", alignment.messages[0], False
    chosen = alignment.context.titles
    if len(chosen) == 1:
        return chosen[0], "", False
    if len(chosen) > 1:
        return "", "Названо несколько титулов. Нужен один титул.", False
    return "", "", True


def _resolve_discipline(
    folded: str,
    catalog: WorkContextCatalog,
    *,
    project_label: str,
    queue: str,
    title: str,
) -> tuple[str, str, str]:
    stems: list[str] = []
    spoken = ""
    for alias, stem in sorted(_DISCIPLINE_STEMS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", folded):
            stems.append(stem)
            spoken = spoken or alias
    unique_stems = tuple(dict.fromkeys(stems))
    if len(unique_stems) > 1:
        return spoken, "", "В команде названо несколько дисциплин."
    if not unique_stems or not project_label or not title:
        return spoken, "", ""
    options = selector_options(
        catalog,
        project=project_label,
        queue=queue or None,
        titles=(title,),
    ).disciplines
    matches = [item for item in options if item.casefold().replace("ё", "е") == unique_stems[0]]
    if len(matches) == 1:
        return spoken, matches[0], ""
    if len(matches) > 1:
        return spoken, "", "Дисциплина совпадает с несколькими значениями справочника."
    return spoken, "", ""
