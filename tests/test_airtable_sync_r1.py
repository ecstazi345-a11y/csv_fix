"""
R1 automatic sync reliability tests. No live Airtable/Supabase writes.

Run:
  python -m unittest tests.test_airtable_sync_r1 -v
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import airtable_http as http


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {"records": []}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Error",
                response=self,
            )


class AirtableRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logs: list[str] = []
        self.sleeps: list[float] = []

    def _log(self, msg: str) -> None:
        self.logs.append(str(msg))

    def _sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))

    def _session(self, side_effect):
        session = MagicMock()
        session.get.side_effect = side_effect
        session.close = MagicMock()
        return session

    def test_ssl_then_success(self) -> None:
        session = self._session(
            [
                requests.exceptions.SSLError("boom"),
                _FakeResponse(200),
            ]
        )
        resp = http.airtable_get(
            "https://api.airtable.com/v0/x/y",
            headers={"Authorization": "Bearer secret-token"},
            session=session,
            sleep=self._sleep,
            log=self._log,
            max_attempts=4,
            backoff_seconds=(2, 5, 10),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(self.sleeps, [2.0])
        self.assertTrue(any("attempt 1/4" in line for line in self.logs))
        self.assertTrue(any("RETRY IN 2" in line for line in self.logs))
        self.assertTrue(any(line == "SUCCESS" for line in self.logs))
        joined = "\n".join(self.logs)
        self.assertNotIn("secret-token", joined)
        self.assertNotIn("Bearer", joined)

    def test_repeated_ssl_fails_closed(self) -> None:
        session = self._session(
            [requests.exceptions.SSLError("self-signed certificate")] * 4
        )
        with self.assertRaises(requests.exceptions.SSLError):
            http.airtable_get(
                "https://api.airtable.com/v0/x/y",
                headers={"Authorization": "Bearer secret-token"},
                session=session,
                sleep=self._sleep,
                log=self._log,
                max_attempts=4,
                backoff_seconds=(2, 5, 10),
            )
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(self.sleeps, [2.0, 5.0, 10.0])

    def test_timeout_retries(self) -> None:
        session = self._session(
            [
                requests.exceptions.ReadTimeout("read timed out"),
                _FakeResponse(200),
            ]
        )
        http.airtable_get(
            "https://api.airtable.com/v0/x/y",
            headers={},
            session=session,
            sleep=self._sleep,
            log=self._log,
        )
        self.assertEqual(session.get.call_count, 2)

    def test_connection_error_retries(self) -> None:
        session = self._session(
            [
                requests.exceptions.ConnectionError("reset"),
                _FakeResponse(200),
            ]
        )
        http.airtable_get(
            "https://api.airtable.com/v0/x/y",
            headers={},
            session=session,
            sleep=self._sleep,
            log=self._log,
        )
        self.assertEqual(session.get.call_count, 2)

    def test_http_429_retries(self) -> None:
        session = self._session([_FakeResponse(429), _FakeResponse(200)])
        http.airtable_get(
            "https://api.airtable.com/v0/x/y",
            headers={},
            session=session,
            sleep=self._sleep,
            log=self._log,
        )
        self.assertEqual(session.get.call_count, 2)

    def test_http_503_retries(self) -> None:
        session = self._session([_FakeResponse(503), _FakeResponse(200)])
        http.airtable_get(
            "https://api.airtable.com/v0/x/y",
            headers={},
            session=session,
            sleep=self._sleep,
            log=self._log,
        )
        self.assertEqual(session.get.call_count, 2)

    def test_http_401_no_retry(self) -> None:
        session = self._session([_FakeResponse(401)])
        with self.assertRaises(requests.exceptions.HTTPError):
            http.airtable_get(
                "https://api.airtable.com/v0/x/y",
                headers={},
                session=session,
                sleep=self._sleep,
                log=self._log,
            )
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual(self.sleeps, [])

    def test_http_403_no_retry(self) -> None:
        session = self._session([_FakeResponse(403)])
        with self.assertRaises(requests.exceptions.HTTPError):
            http.airtable_get(
                "https://api.airtable.com/v0/x/y",
                headers={},
                session=session,
                sleep=self._sleep,
                log=self._log,
            )
        self.assertEqual(session.get.call_count, 1)

    def test_http_404_no_retry(self) -> None:
        session = self._session([_FakeResponse(404)])
        with self.assertRaises(requests.exceptions.HTTPError):
            http.airtable_get(
                "https://api.airtable.com/v0/x/y",
                headers={},
                session=session,
                sleep=self._sleep,
                log=self._log,
            )
        self.assertEqual(session.get.call_count, 1)

    def test_session_uses_trust_env_false(self) -> None:
        sess = http.make_airtable_session()
        self.assertIs(sess.trust_env, False)

    def test_no_verify_false_in_helper_source(self) -> None:
        source = Path(http.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"verify\s*=\s*False")
        self.assertNotIn("disable_warnings", source)


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Reload module so HEALTH paths can be patched cleanly.
        import update_all_sync as orch

        self.orch = importlib.reload(orch)

    def test_all_success_exit_0(self) -> None:
        health = Path(self.tmp.name) / "last_sync_status.json"
        with patch.object(self.orch, "HEALTH_DIR", Path(self.tmp.name)), patch.object(
            self.orch, "HEALTH_PATH", health
        ), patch.object(self.orch, "run_script", return_value=0):
            code = self.orch.main()
        self.assertEqual(code, 0)
        payload = json.loads(health.read_text(encoding="utf-8"))
        self.assertEqual(payload["overall_status"], "SUCCESS")
        self.assertEqual(payload["completed"], 4)
        self.assertEqual(payload["total"], 4)
        self.assertIsNone(payload["failed_sync"])
        self.assertEqual(
            [row["status"] for row in payload["results"]],
            ["SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS"],
        )
        blob = health.read_text(encoding="utf-8")
        self.assertNotIn("Bearer", blob)
        self.assertNotIn("AIRTABLE_TOKEN", blob)
        self.assertNotIn("SUPABASE", blob)

    def test_first_fail_skips_rest(self) -> None:
        health = Path(self.tmp.name) / "last_sync_status.json"
        codes = [1, 0, 0, 0]

        def _run(_script: str) -> int:
            return codes.pop(0)

        with patch.object(self.orch, "HEALTH_DIR", Path(self.tmp.name)), patch.object(
            self.orch, "HEALTH_PATH", health
        ), patch.object(self.orch, "run_script", side_effect=_run) as mocked:
            code = self.orch.main()
        self.assertEqual(code, 1)
        self.assertEqual(mocked.call_count, 1)
        payload = json.loads(health.read_text(encoding="utf-8"))
        self.assertEqual(payload["overall_status"], "FAILED")
        self.assertEqual(payload["completed"], 0)
        self.assertEqual(payload["failed_sync"], "daily_progress")
        self.assertEqual(
            [row["status"] for row in payload["results"]],
            ["FAILED", "SKIPPED", "SKIPPED", "SKIPPED"],
        )

    def test_mid_fail_summary(self) -> None:
        health = Path(self.tmp.name) / "last_sync_status.json"
        sequence = iter([0, 0, 1, 0])

        def _run(_script: str) -> int:
            return next(sequence)

        with patch.object(self.orch, "HEALTH_DIR", Path(self.tmp.name)), patch.object(
            self.orch, "HEALTH_PATH", health
        ), patch.object(self.orch, "run_script", side_effect=_run) as mocked:
            code = self.orch.main()
        self.assertEqual(code, 1)
        self.assertEqual(mocked.call_count, 3)
        payload = json.loads(health.read_text(encoding="utf-8"))
        self.assertEqual(payload["completed"], 2)
        self.assertEqual(payload["failed_sync"], "monthly_passport")
        self.assertEqual(
            [row["status"] for row in payload["results"]],
            ["SUCCESS", "SUCCESS", "FAILED", "SKIPPED"],
        )


class SecuritySourceTests(unittest.TestCase):
    def test_sync_scripts_have_no_verify_false(self) -> None:
        paths = [
            ROOT / "services" / "airtable_http.py",
            ROOT / "update_all_sync.py",
            ROOT / "daily_progress_sync_upsert.py",
            ROOT / "boq_sync_upsert.py",
            ROOT / "monthly_passport_sync_airtable.py",
            ROOT / "monthly_labor_summary_sync_upsert.py",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"verify\s*=\s*False", msg=str(path))
            self.assertNotIn("disable_warnings", text, msg=str(path))


if __name__ == "__main__":
    unittest.main()
