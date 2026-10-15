"""
Page 53 live-truth binding: production Query Port reads Constructor shadow stores.

Skips when the authoritative October live shadow run is absent.
Does not mutate stores, launch runs, or invent fallbacks.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from agents.control_room.dtos import ProfessionalResultAvailability
from agents.control_room.factory import (
    AGENT_OBSERVABILITY_DB_PATH_ENV,
    build_agent_control_room_query_port,
    resolve_observability_db_path,
)
from agents.human_surface.result_view import (
    MODULE5_MODE_INCREMENTAL_RU,
    build_module5_result_summary,
    module5_kpi_tiles,
)
from agents.observability.contracts import OperationalStatus

LIVE_RUN_ID = "run-a0c70277-486b-439d-a6be-7599411ffc37"
LIVE_MISSION_ID = "mission-hs-64b62cbcb56220fb604625d3"
LIVE_PACKAGE_ID = "3ef26b0e-1f5c-41ef-a06e-e39758749273"
REPO_ROOT = Path(__file__).resolve().parents[1]
SHADOW_OBS = (
    REPO_ROOT / ".runtime" / "shadow" / "constructor" / "observability.sqlite"
)


def _close_port(port) -> None:
    store = getattr(port, "_store", None)
    close = getattr(store, "close", None)
    if callable(close):
        close()


@unittest.skipUnless(SHADOW_OBS.is_file(), "constructor shadow observability.sqlite absent")
class HumanSurfaceLiveTruthBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.get(AGENT_OBSERVABILITY_DB_PATH_ENV)
        os.environ[AGENT_OBSERVABILITY_DB_PATH_ENV] = str(SHADOW_OBS.resolve())
        self.port = build_agent_control_room_query_port()

    def tearDown(self) -> None:
        _close_port(self.port)
        if self._env is None:
            os.environ.pop(AGENT_OBSERVABILITY_DB_PATH_ENV, None)
        else:
            os.environ[AGENT_OBSERVABILITY_DB_PATH_ENV] = self._env

    def test_factory_resolves_same_shadow_store_without_env(self) -> None:
        os.environ.pop(AGENT_OBSERVABILITY_DB_PATH_ENV, None)
        resolved = resolve_observability_db_path()
        self.assertEqual(resolved, SHADOW_OBS.resolve())

    def test_production_query_port_returns_professional_result_for_live_october_run(self) -> None:
        snapshot = self.port.get_run_snapshot(LIVE_RUN_ID)
        self.assertEqual(snapshot.run.run_id, LIVE_RUN_ID)
        self.assertEqual(snapshot.run.mission_id, LIVE_MISSION_ID)

        result = self.port.get_constructor_professional_result(LIVE_RUN_ID)
        self.assertEqual(result.availability, ProfessionalResultAvailability.AVAILABLE)
        self.assertEqual(result.run_id, LIVE_RUN_ID)
        self.assertEqual(result.mission_id, LIVE_MISSION_ID)
        self.assertEqual(result.source_candidate_package_id, LIVE_PACKAGE_ID)
        self.assertEqual(result.professional_status, "WAITING_FOR_HUMAN_REVIEW")

        registry = self.port.get_constructor_decision_registry(LIVE_RUN_ID)
        self.assertEqual(registry.availability, ProfessionalResultAvailability.AVAILABLE)
        self.assertEqual(registry.total_count, 530)
        self.assertEqual(registry.professional.run_id, LIVE_RUN_ID)

        summary = build_module5_result_summary(registry)
        self.assertEqual(summary.mode_badge, MODULE5_MODE_INCREMENTAL_RU)
        tiles = dict(module5_kpi_tiles(summary))
        self.assertEqual(tiles["Изучено"], "530")
        self.assertEqual(tiles["Предложено к рассмотрению"], "26")
        self.assertEqual(tiles["Контрольные отклонения"], "206")
        self.assertEqual(tiles["Не требуют действия"], "298")
        self.assertEqual(26 + 206 + 298, 530)

        # Historical live run may still project RUNNING until HUMAN_WAIT_STARTED
        # is present; professional lifecycle truth is WAITING_FOR_HUMAN_REVIEW.
        self.assertIn(
            snapshot.run.operational_status,
            {
                OperationalStatus.RUNNING.value,
                OperationalStatus.WAITING_FOR_HUMAN.value,
            },
        )


if __name__ == "__main__":
    unittest.main()
