"""
Increment 10.7 — Control Room presentation helper tests.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from agents.control_room.dtos import DerivationState
from agents.control_room.presentation import (
    DERIVATION_STAGE_INCONSISTENT_RU,
    DERIVATION_STAGE_INCOMPLETE_RU,
    derivation_stage_warning,
    format_timestamp_moscow,
    operational_status_ru,
    short_run_id,
    stage_display_state_ru,
    status_visual_category,
)
from agents.observability.contracts import OperationalStatus


class ControlRoomPresentationTests(unittest.TestCase):
    def test_operational_status_ru_mapping(self) -> None:
        self.assertEqual(operational_status_ru(OperationalStatus.REQUESTED.value), "Запрошен")
        self.assertEqual(operational_status_ru(OperationalStatus.AUTHORIZING.value), "Проверка допуска")
        self.assertEqual(
            operational_status_ru(OperationalStatus.AUTHORIZATION_DENIED.value),
            "Допуск отклонён",
        )
        self.assertEqual(operational_status_ru(OperationalStatus.STARTING.value), "Запуск")
        self.assertEqual(operational_status_ru(OperationalStatus.RUNNING.value), "Выполняется")
        self.assertEqual(
            operational_status_ru(OperationalStatus.WAITING_FOR_HUMAN.value),
            "Ожидает решения человека",
        )
        self.assertEqual(operational_status_ru(OperationalStatus.RETRYING.value), "Повторная попытка")
        self.assertEqual(operational_status_ru(OperationalStatus.COMPLETED.value), "Завершён")
        self.assertEqual(operational_status_ru(OperationalStatus.FAILED.value), "Ошибка")
        self.assertEqual(operational_status_ru(OperationalStatus.ABORTED.value), "Остановлен решением")

    def test_unknown_operational_status_fallback(self) -> None:
        self.assertEqual(operational_status_ru("CUSTOM_STATUS"), "CUSTOM_STATUS")

    def test_stage_display_state_ru_mapping(self) -> None:
        self.assertEqual(stage_display_state_ru("RUNNING"), "Выполняется")
        self.assertEqual(stage_display_state_ru("COMPLETED"), "Завершена")
        self.assertEqual(stage_display_state_ru("FAILED"), "Ошибка")
        self.assertEqual(stage_display_state_ru("UNKNOWN_STAGE"), "UNKNOWN_STAGE")

    def test_format_timestamp_moscow(self) -> None:
        utc = datetime(2026, 9, 2, 9, 30, tzinfo=timezone.utc)
        self.assertEqual(format_timestamp_moscow(utc), "02.09.2026 12:30")
        self.assertEqual(format_timestamp_moscow(None), "—")

    def test_short_run_id(self) -> None:
        self.assertEqual(short_run_id("abcd1234"), "abcd1234")
        self.assertEqual(short_run_id("run-0123456789abcdef"), "…89abcdef")

    def test_status_visual_category(self) -> None:
        self.assertEqual(status_visual_category(OperationalStatus.REQUESTED.value), "neutral")
        self.assertEqual(status_visual_category(OperationalStatus.RUNNING.value), "active")
        self.assertEqual(status_visual_category(OperationalStatus.WAITING_FOR_HUMAN.value), "waiting")
        self.assertEqual(status_visual_category(OperationalStatus.COMPLETED.value), "success")
        self.assertEqual(status_visual_category(OperationalStatus.FAILED.value), "failure")
        self.assertEqual(status_visual_category(OperationalStatus.ABORTED.value), "aborted")
        self.assertEqual(status_visual_category("UNKNOWN"), "neutral")

    def test_derivation_stage_warning(self) -> None:
        self.assertEqual(derivation_stage_warning(DerivationState.INCOMPLETE), DERIVATION_STAGE_INCOMPLETE_RU)
        self.assertEqual(
            derivation_stage_warning(DerivationState.INCONSISTENT),
            DERIVATION_STAGE_INCONSISTENT_RU,
        )
        self.assertIsNone(derivation_stage_warning(DerivationState.OK))


if __name__ == "__main__":
    unittest.main()
