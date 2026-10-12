"""Read-only work-context catalog for the Constructor workspace.

Reuses the monthly planning scope view and the same queue rule as the
manual constructor. Does not write, seed, or invent missing values.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from agents.human_surface.mission_draft import (
    ContextOptionSets,
    WorkingContext,
    discipline_label,
)


PLANNING_MONTHS_2026: tuple[str, ...] = (
    "январь 2026",
    "февраль 2026",
    "март 2026",
    "апрель 2026",
    "май 2026",
    "июнь 2026",
    "июль 2026",
    "август 2026",
    "сентябрь 2026",
    "октябрь 2026",
    "ноябрь 2026",
    "декабрь 2026",
)

SCOPE_SOURCE = "monthly_scope_picker_view"
MONTH_SOURCE = "planning_month_options_2026"
QUEUE_SOURCE = "derive_construction_queue_from_facility"

PACKAGES_UNAVAILABLE_RU = "Структурированные пакеты пока недоступны."
SYSTEMS_UNAVAILABLE_RU = "Структурированные системы пока недоступны."
PROJECTS_UNAVAILABLE_RU = "Структурированные проекты пока недоступны."
QUEUES_UNAVAILABLE_RU = "Структурированные очереди пока недоступны."
TITLES_UNAVAILABLE_RU = "Структурированные титулы пока недоступны."
DISCIPLINES_UNAVAILABLE_RU = "Структурированные дисциплины пока недоступны."

_CACHE_SECONDS = 60.0
_CACHE: dict[str, object] = {}


@dataclass(frozen=True)
class ScopeFact:
    project_label: str
    project_code: str
    queue: str
    facility: str
    title: str
    discipline: str
    systems: tuple[str, ...]
    packages: tuple[str, ...]


@dataclass(frozen=True)
class WorkContextCatalog:
    source: str
    error: str
    months: tuple[str, ...]
    facts: tuple[ScopeFact, ...]

    @property
    def projects_available(self) -> bool:
        return any(item.project_label for item in self.facts)

    @property
    def queues_available(self) -> bool:
        return any(item.queue for item in self.facts)

    @property
    def titles_available(self) -> bool:
        return any(item.title for item in self.facts)

    @property
    def disciplines_available(self) -> bool:
        return any(item.discipline for item in self.facts)

    @property
    def systems_available(self) -> bool:
        return any(item.systems for item in self.facts)

    @property
    def packages_available(self) -> bool:
        return any(item.packages for item in self.facts)


def queue_from_facility(facility: str) -> str:
    """Same facility rule as the manual constructor. Unknown facilities stay blank."""
    text = str(facility or "")
    if "16160-13" in text or "16160-17" in text:
        return "1"
    if "26160-13" in text or "26160-17" in text:
        return "2"
    return ""


def project_label(project_code: str) -> str:
    text = str(project_code or "").strip()
    if text.casefold() in {"бхк", "bhk"}:
        return ""
    prefix = "PRJ_001_"
    if text.startswith(prefix) and text[len(prefix):].strip():
        return text[len(prefix):].strip()
    return text


def catalog_from_frame(frame: pd.DataFrame, *, error: str = "") -> WorkContextCatalog:
    facts = _facts_from_frame(frame)
    return WorkContextCatalog(
        source=SCOPE_SOURCE,
        error=str(error or ""),
        months=PLANNING_MONTHS_2026,
        facts=facts,
    )


def load_work_context_catalog() -> WorkContextCatalog:
    """Live READ of the scope view. Empty facts on failure, never demo rows."""
    now = time.monotonic()
    cached = _CACHE.get("catalog")
    cached_at = float(_CACHE.get("at") or 0)
    if isinstance(cached, WorkContextCatalog) and now - cached_at < _CACHE_SECONDS:
        return cached
    frame = pd.DataFrame()
    error = ""
    try:
        from services.monthly_plan_constructor_read_service import load_constructor_scope

        frame, meta = load_constructor_scope()
        error = str((meta or {}).get("error") or "")
    except Exception as exc:  # noqa: BLE001
        error = type(exc).__name__
        frame = pd.DataFrame()
    catalog = catalog_from_frame(frame, error=error)
    if not error:
        _CACHE["catalog"] = catalog
        _CACHE["at"] = now
    return catalog


def selector_options(
    catalog: WorkContextCatalog,
    *,
    project: Optional[str] = None,
    queue: Optional[str] = None,
    titles: tuple[str, ...] = (),
    discipline: Optional[str] = None,
) -> ContextOptionSets:
    """Cascade only along columns that already sit on the same scope row."""
    project_facts = [
        item for item in catalog.facts if not project or item.project_label == project
    ]
    queue_facts = [item for item in project_facts if not queue or item.queue == queue]
    title_facts = [
        item for item in queue_facts if not titles or item.title in titles
    ]
    discipline_facts = [
        item
        for item in title_facts
        if not discipline or item.discipline == discipline
    ]
    return ContextOptionSets(
        projects=_unique(item.project_label for item in catalog.facts),
        months=catalog.months,
        queues=_unique(item.queue for item in project_facts),
        titles=_unique(item.title for item in queue_facts),
        disciplines=_unique(item.discipline for item in title_facts),
        systems=_unique(system for item in discipline_facts for system in item.systems),
        packages=_unique(package for item in discipline_facts for package in item.packages),
    )


@dataclass(frozen=True)
class ContextAlignment:
    context: WorkingContext
    messages: tuple[str, ...] = ()


def align_working_context(context: WorkingContext, catalog: WorkContextCatalog) -> ContextAlignment:
    """Keep command values that exist in the catalog. Do not add the rest as options."""
    messages: list[str] = []
    projects = selector_options(catalog).projects
    project = _match_text(context.project, projects) if projects else context.project
    queues = selector_options(catalog, project=project).queues
    queue = _match_text(context.queue, queues) if queues else context.queue
    titles = selector_options(catalog, project=project, queue=queue).titles
    chosen_titles, ambiguous = _match_titles(context.titles, titles) if titles else (context.titles, ())
    if ambiguous:
        chosen_titles = ()
        shown = " и ".join(ambiguous)
        messages.append(f"Для титулов {shown} необходимо определить очередь.")
    disciplines = selector_options(
        catalog, project=project, queue=queue, titles=chosen_titles
    ).disciplines
    discipline = _match_text(context.discipline, disciplines) if disciplines else context.discipline
    systems = selector_options(
        catalog,
        project=project,
        queue=queue,
        titles=chosen_titles,
        discipline=discipline,
    ).systems
    chosen_systems = tuple(item for item in context.systems if item in systems) if systems else context.systems
    return ContextAlignment(
        context=WorkingContext(
            project=project,
            planning_month=_match_month(context.planning_month, catalog.months),
            queue=queue,
            titles=chosen_titles,
            discipline=discipline,
            systems=chosen_systems,
            packages=context.packages if not catalog.packages_available else _match_packages(context.packages, selector_options(
                catalog,
                project=project,
                queue=queue,
                titles=chosen_titles,
                discipline=discipline,
            ).packages),
            agent_code=context.agent_code,
            excluded_scope_rule=context.excluded_scope_rule,
            intent=context.intent,
            contour_code=context.contour_code,
        ),
        messages=tuple(messages),
    )


def _facts_from_frame(frame: pd.DataFrame) -> tuple[ScopeFact, ...]:
    if frame is None or frame.empty:
        return ()
    raw_rows: list[dict[str, str]] = []
    for record in frame.to_dict(orient="records"):
        facility = _first(record, ("facility", "facility_building"))
        queue = queue_from_facility(facility)
        raw_rows.append(
            {
                "project_code": _first(record, ("project_code",)),
                "facility": facility,
                "queue": queue,
                "discipline": discipline_label(_first(record, ("discipline", "construction_discipline"))),
                "system": _first(record, ("system", "system_label")),
                "package": _first(record, ("iwp", "iwp_id")),
            }
        )
    facts: list[ScopeFact] = []
    for row in raw_rows:
        label = project_label(row["project_code"])
        facility = str(row["facility"] or "").strip()
        if not label and not facility:
            continue
        facts.append(
            ScopeFact(
                project_label=label,
                project_code=row["project_code"],
                queue=row["queue"],
                facility=facility,
                title=facility,
                discipline=row["discipline"],
                systems=_tokens(row["system"]),
                packages=_tokens(row["package"]),
            )
        )
    return tuple(facts)


def _match_titles(
    spoken: tuple[str, ...],
    options: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    chosen: list[str] = []
    ambiguous: list[str] = []
    for title in spoken:
        if title in options:
            chosen.append(title)
            continue
        matches = [item for item in options if _facility_alias(item, title)]
        if len(matches) == 1:
            chosen.append(matches[0])
        elif len(matches) > 1:
            ambiguous.append(title)
    return tuple(dict.fromkeys(chosen)), tuple(dict.fromkeys(ambiguous))


def _facility_alias(facility: str, alias: str) -> bool:
    """Match a spoken title number to one full facility id. Does not shorten the id."""
    if not str(alias or "").isdigit():
        return False
    head, separator, tail = str(facility or "").rpartition("-")
    return bool(separator) and tail == alias and head.isdigit()


def _match_text(value: Optional[str], options: tuple[str, ...]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    for option in options:
        if option == text or option.casefold() == text.casefold():
            return option
    return None


def _match_month(value: Optional[str], options: tuple[str, ...]) -> Optional[str]:
    text = str(value or "").strip().replace("-", " ")
    return _match_text(text, options)


def _match_packages(value: Optional[str], options: tuple[str, ...]) -> Optional[str]:
    if not options:
        return None
    wanted = _tokens(str(value or ""))
    found = [item for item in wanted if item in options]
    if found:
        return ", ".join(found)
    return None


def _tokens(value: str) -> tuple[str, ...]:
    found: list[str] = []
    for part in str(value or "").replace(";", ",").replace("/", ",").split(","):
        text = part.strip()
        if text and text not in {"—", "-"} and text not in found:
            found.append(text)
    return tuple(found)


def _unique(values: object) -> tuple[str, ...]:
    found: list[str] = []
    for value in values:  # type: ignore[union-attr]
        text = str(value or "").strip()
        if text and text not in found:
            found.append(text)
    return tuple(found)


def _first(record: dict, names: tuple[str, ...]) -> str:
    for name in names:
        value = record.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "<na>"}:
            return text
    return ""
