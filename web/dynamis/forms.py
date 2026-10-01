"""Django forms for LND Human Surface — UX only; service remains authority."""
from __future__ import annotations

from django import forms

from services.labor_norm_decisions import (
    DECISION_MANUAL_PROVISIONAL,
    DECISION_REJECTED,
)


class LaborNormDecisionForm(forms.Form):
    project_code = forms.CharField(
        label="Проект",
        max_length=200,
        initial="PRJ_001_БХК",
    )
    facility_building = forms.CharField(
        label="Титул / объект",
        max_length=200,
    )
    construction_discipline = forms.CharField(
        label="Дисциплина",
        max_length=200,
    )
    boq_code = forms.CharField(
        label="BOQ",
        max_length=200,
    )
    unit_of_measure = forms.CharField(
        label="Ед. измерения",
        max_length=200,
    )
    boq_name = forms.CharField(
        label="Наименование BOQ",
        max_length=500,
        required=False,
    )
    decision = forms.ChoiceField(
        label="Решение",
        choices=(
            (DECISION_MANUAL_PROVISIONAL, "Задать временную норму вручную"),
            (DECISION_REJECTED, "Отклонить"),
        ),
        widget=forms.RadioSelect,
        initial=DECISION_MANUAL_PROVISIONAL,
    )
    approved_norm = forms.CharField(
        label="Временная норма (чел·ч / ед.)",
        required=False,
        help_text="Обязательна для ручной временной нормы. Только число > 0.",
    )
    comment = forms.CharField(
        label="Комментарий",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    approved_by = forms.CharField(
        label="Кто утверждает",
        max_length=200,
        help_text=(
            "Операторская метка (ФИО/идентификатор). "
            "Криптографическая идентификация в R1 не реализована."
        ),
    )

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get("decision")
        norm_raw = (cleaned.get("approved_norm") or "").strip()
        if decision == DECISION_MANUAL_PROVISIONAL:
            if not norm_raw:
                self.add_error(
                    "approved_norm",
                    "Укажите временную норму > 0 для ручного решения.",
                )
            else:
                try:
                    value = float(norm_raw.replace(",", "."))
                except ValueError:
                    self.add_error("approved_norm", "Норма должна быть числом.")
                else:
                    if value <= 0:
                        self.add_error("approved_norm", "Норма должна быть > 0.")
                    else:
                        cleaned["approved_norm_value"] = value
        else:
            cleaned["approved_norm_value"] = None
        return cleaned
