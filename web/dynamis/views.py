"""DYNAMIS Human Surface views — service layer only, zero network on GET."""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from services.labor_norm_decisions import (
    APPROVED_BY_OPERATOR_LABEL_NOTE,
    DECISION_MANUAL_PROVISIONAL,
    DECISION_REJECTED,
    LaborNormDecisionDraft,
    get_active_decision,
    save_decision,
)

from .forms import LaborNormDecisionForm

SOURCE_PAGE_DJANGO = "DJANGO_LABOR_NORM_DECISION"


def home(request):
    return render(request, "dynamis/home.html")


def architecture(request):
    """Static architecture map — zero network calls."""
    return render(request, "dynamis/architecture.html")


@require_http_methods(["GET", "POST"])
def labor_norm_decision(request):
    """
    Initial GET: no Supabase calls.
    POST save: one service write.
    POST readback (?action=readback): one explicit get_active_decision.
    """
    form = LaborNormDecisionForm()
    save_result = None
    active_record = None
    readback_error = None

    if request.method == "POST":
        action = (request.POST.get("action") or "save").strip()
        if action == "readback":
            project = (request.POST.get("project_code") or "").strip()
            facility = (request.POST.get("facility_building") or "").strip()
            discipline = (request.POST.get("construction_discipline") or "").strip()
            boq = (request.POST.get("boq_code") or "").strip()
            form = LaborNormDecisionForm(
                initial={
                    "project_code": project,
                    "facility_building": facility,
                    "construction_discipline": discipline,
                    "boq_code": boq,
                    "unit_of_measure": request.POST.get("unit_of_measure") or "",
                    "boq_name": request.POST.get("boq_name") or "",
                    "decision": request.POST.get("decision")
                    or DECISION_MANUAL_PROVISIONAL,
                    "approved_by": request.POST.get("approved_by") or "",
                    "comment": request.POST.get("comment") or "",
                }
            )
            try:
                active_record = get_active_decision(
                    project_code=project,
                    facility_building=facility,
                    construction_discipline=discipline,
                    boq_code=boq,
                )
                if active_record is None:
                    messages.info(request, "Активное решение по этому grain не найдено.")
            except Exception as exc:  # noqa: BLE001
                readback_error = str(exc)
                messages.warning(
                    request,
                    "Не удалось прочитать сохранённое решение (сеть/доступ). "
                    "Страница остаётся доступной.",
                )
        else:
            form = LaborNormDecisionForm(request.POST)
            if form.is_valid():
                cleaned = form.cleaned_data
                draft = LaborNormDecisionDraft(
                    project_code=cleaned["project_code"],
                    facility_building=cleaned["facility_building"],
                    construction_discipline=cleaned["construction_discipline"],
                    boq_code=cleaned["boq_code"],
                    unit_of_measure=cleaned["unit_of_measure"],
                    decision=cleaned["decision"],
                    approved_by=cleaned["approved_by"],
                    comment=cleaned["comment"],
                    approved_norm=cleaned.get("approved_norm_value"),
                    boq_name=cleaned.get("boq_name") or "",
                    source_page=SOURCE_PAGE_DJANGO,
                    expected_unit=cleaned["unit_of_measure"],
                )
                result = save_decision(draft)
                if result.get("ok"):
                    save_result = result.get("data") or {}
                    messages.success(request, "Решение сохранено.")
                else:
                    messages.error(
                        request,
                        result.get("error") or "Не удалось сохранить решение.",
                    )

    return render(
        request,
        "dynamis/labor_norm_decision.html",
        {
            "form": form,
            "save_result": save_result,
            "active_record": active_record,
            "readback_error": readback_error,
            "operator_note": APPROVED_BY_OPERATOR_LABEL_NOTE,
            "decision_manual": DECISION_MANUAL_PROVISIONAL,
            "decision_rejected": DECISION_REJECTED,
        },
    )
