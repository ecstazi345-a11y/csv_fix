"""
Constructor Human Confirm Contract V1 — pure contract tests.

No runtime wiring. No persistence. No UI. No LLM. No product writes.
"""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    build_candidate_package,
)
from agents.monthly_plan_constructor.human_confirm_contracts import (
    ACTOR_TYPE_HUMAN,
    CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
    HumanConfirmContractError,
    HumanConfirmDecision,
    HumanConfirmEvent,
    assert_no_handoff_or_commitment_semantics,
    build_human_confirm_event,
    human_confirm_event_as_dict,
    normalize_human_confirm_events,
    project_effective_human_confirm,
    validate_human_confirm_event_against_package,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    HumanReviewDecision,
    build_human_review_event,
)
from agents.monthly_plan_constructor.mission_scope import (
    build_constructor_mission_scope,
)
from agents.monthly_plan_constructor.reviewed_candidate_package import (
    ReviewedDisposition,
    build_reviewed_candidate_package,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY = "16160-17"
DISCIPLINE = "Автоматизация"
MISSION_ID = "mission-hc-1"
RUN_ID = "run-hc-1"
CAND_A = "CAND-A"
CAND_B = "CAND-B"
STAMP = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
CREATED = datetime(2026, 10, 8, 13, 0, 0, tzinfo=timezone.utc)
CONFIRMED_AT = datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc)


def _mission():
    return build_constructor_mission_scope(project_code=PROJECT, month_key=MONTH)


def _candidate(
    candidate_id: str = CAND_A,
    *,
    labor_norm_status: str = LABOR_VALIDATED,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY,
        "discipline": DISCIPLINE,
        "system": "SYS-1",
        "iwp": "IWP-1",
        "queue": "",
        "boq_code": "BOQ-001" if candidate_id == CAND_A else "BOQ-002",
        "boq_name": "Кабель",
        "unit": "м",
        "remaining_qty": 90.0,
        "already_planned_qty": 0.0,
        "available_to_add_qty": 90.0,
        "availability_status": "AVAILABLE",
        "labor_norm_status": labor_norm_status,
    }


def _candidate_package(*, candidates: list[dict[str, object]] | None = None):
    items = candidates if candidates is not None else [_candidate()]
    return build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items),
        run_id=RUN_ID,
        snapshot_id="snap-hc-1",
    )


def _review_event(
    package,
    *,
    review_event_id: str = "rev-1",
    candidate_id: str = CAND_A,
    decision: object = HumanReviewDecision.ADD,
):
    return build_human_review_event(
        review_event_id=review_event_id,
        run_id=RUN_ID,
        mission_id=MISSION_ID,
        package_id=package.package_id,
        candidate_id=candidate_id,
        decision=decision,
        actor_id="operator-1",
        reviewed_at=STAMP,
    )


def _confirmable_reviewed(
    *,
    candidates: list[dict[str, object]] | None = None,
    reviews: list | None = None,
):
    package = _candidate_package(candidates=candidates)
    events = reviews if reviews is not None else [_review_event(package)]
    return build_reviewed_candidate_package(
        package, events, (), created_at=CREATED
    )


def _confirm_event(
    reviewed,
    *,
    confirm_event_id: str = "confirm-1",
    reviewed_package_id: str | None = None,
    source_candidate_package_id: str | None = None,
    run_id: str = RUN_ID,
    mission_id: str = MISSION_ID,
    decision: object = HumanConfirmDecision.CONFIRM,
    actor_id: str = "operator-1",
    actor_type: str = ACTOR_TYPE_HUMAN,
    confirmed_at: datetime = CONFIRMED_AT,
):
    return build_human_confirm_event(
        confirm_event_id=confirm_event_id,
        reviewed_package_id=reviewed_package_id or reviewed.reviewed_package_id,
        source_candidate_package_id=(
            source_candidate_package_id or reviewed.source_candidate_package_id
        ),
        run_id=run_id,
        mission_id=mission_id,
        decision=decision,
        actor_id=actor_id,
        actor_type=actor_type,
        confirmed_at=confirmed_at,
    )


class HumanConfirmEligibilityTests(unittest.TestCase):
    def test_01_unresolved_zero_confirm_accepted(self) -> None:
        reviewed = _confirmable_reviewed()
        self.assertEqual(reviewed.unresolved_count, 0)
        event = _confirm_event(reviewed)
        validated = validate_human_confirm_event_against_package(event, reviewed)
        self.assertEqual(validated.decision, HumanConfirmDecision.CONFIRM)

    def test_02_unresolved_gt_zero_fail_closed(self) -> None:
        package = _candidate_package(
            candidates=[_candidate(labor_norm_status=LABOR_UNRESOLVED)]
        )
        reviewed = build_reviewed_candidate_package(
            package, (), (), created_at=CREATED
        )
        self.assertGreater(reviewed.unresolved_count, 0)
        event = _confirm_event(reviewed)
        with self.assertRaises(HumanConfirmContractError) as raised:
            validate_human_confirm_event_against_package(event, reviewed)
        self.assertEqual(raised.exception.code, CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER)
        self.assertIn("unresolved_count", str(raised.exception))

    def test_03_all_excluded_confirm_allowed(self) -> None:
        package = _candidate_package()
        reviewed = build_reviewed_candidate_package(
            package,
            [_review_event(package, decision=HumanReviewDecision.REMOVE)],
            (),
            created_at=CREATED,
        )
        self.assertEqual(reviewed.included_count, 0)
        self.assertEqual(reviewed.excluded_count, 1)
        self.assertEqual(reviewed.unresolved_count, 0)
        self.assertEqual(
            reviewed.reviewed_records[0].disposition, ReviewedDisposition.EXCLUDED
        )
        validated = validate_human_confirm_event_against_package(
            _confirm_event(reviewed), reviewed
        )
        self.assertEqual(validated.decision, HumanConfirmDecision.CONFIRM)

    def test_04_provisional_included_confirm_allowed(self) -> None:
        package = _candidate_package(
            candidates=[_candidate(labor_norm_status=LABOR_PROVISIONAL)]
        )
        reviewed = build_reviewed_candidate_package(
            package, [_review_event(package)], (), created_at=CREATED
        )
        self.assertEqual(
            reviewed.reviewed_records[0].disposition, ReviewedDisposition.INCLUDED
        )
        self.assertEqual(
            reviewed.reviewed_records[0].source_candidate.labor_norm_status,
            LABOR_PROVISIONAL,
        )
        validated = validate_human_confirm_event_against_package(
            _confirm_event(reviewed), reviewed
        )
        self.assertEqual(validated.decision, HumanConfirmDecision.CONFIRM)


class HumanConfirmBindingTests(unittest.TestCase):
    def test_05_wrong_reviewed_package_id_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(reviewed, reviewed_package_id="other-reviewed-id")
        with self.assertRaises(HumanConfirmContractError) as raised:
            validate_human_confirm_event_against_package(event, reviewed)
        self.assertIn("reviewed_package_id", str(raised.exception))

    def test_06_wrong_source_candidate_package_id_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(
            reviewed, source_candidate_package_id="other-source-pkg"
        )
        with self.assertRaises(HumanConfirmContractError) as raised:
            validate_human_confirm_event_against_package(event, reviewed)
        self.assertIn("source_candidate_package_id", str(raised.exception))

    def test_07_wrong_run_id_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(reviewed, run_id="other-run")
        with self.assertRaises(HumanConfirmContractError) as raised:
            validate_human_confirm_event_against_package(event, reviewed)
        self.assertIn("run_id", str(raised.exception))

    def test_08_wrong_mission_id_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(reviewed, mission_id="other-mission")
        with self.assertRaises(HumanConfirmContractError) as raised:
            validate_human_confirm_event_against_package(event, reviewed)
        self.assertIn("mission_id", str(raised.exception))

    def test_09_blank_confirm_event_id_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        with self.assertRaises(HumanConfirmContractError) as raised:
            _confirm_event(reviewed, confirm_event_id="  ")
        self.assertIn("confirm_event_id", str(raised.exception))

    def test_10_blank_actor_id_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        with self.assertRaises(HumanConfirmContractError) as raised:
            _confirm_event(reviewed, actor_id="")
        self.assertIn("actor_id", str(raised.exception))

    def test_11_invalid_actor_type_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        with self.assertRaises(HumanConfirmContractError) as raised:
            _confirm_event(reviewed, actor_type="AGENT")
        self.assertIn("actor_type", str(raised.exception))

    def test_12_invalid_decision_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        with self.assertRaises(HumanConfirmContractError) as raised:
            _confirm_event(reviewed, decision="REJECT")
        self.assertIn("invalid human confirm decision", str(raised.exception))


class HumanConfirmImmutabilityTests(unittest.TestCase):
    def test_13_14_reviewed_package_unchanged(self) -> None:
        reviewed = _confirmable_reviewed()
        before = copy.deepcopy(reviewed)
        event = _confirm_event(reviewed)
        validate_human_confirm_event_against_package(event, reviewed)
        project_effective_human_confirm([event], reviewed)
        self.assertEqual(reviewed, before)
        self.assertEqual(reviewed.included_count, before.included_count)
        self.assertEqual(reviewed.excluded_count, before.excluded_count)
        self.assertEqual(reviewed.unresolved_count, before.unresolved_count)
        self.assertEqual(reviewed.reviewed_package_id, before.reviewed_package_id)
        self.assertEqual(
            reviewed.review_projection_fingerprint,
            before.review_projection_fingerprint,
        )
        self.assertEqual(
            reviewed.exception_fingerprint, before.exception_fingerprint
        )
        self.assertEqual(reviewed.reviewed_records, before.reviewed_records)

    def test_21_confirm_event_immutable(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(reviewed)
        with self.assertRaises(Exception):
            event.actor_id = "mutated"  # type: ignore[misc]

    def test_22_confirmed_at_does_not_mutate_package(self) -> None:
        reviewed = _confirmable_reviewed()
        created_before = reviewed.created_at
        validate_human_confirm_event_against_package(
            _confirm_event(
                reviewed,
                confirmed_at=datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc),
            ),
            reviewed,
        )
        self.assertEqual(reviewed.created_at, created_before)


class HumanConfirmIdempotencyTests(unittest.TestCase):
    def test_15_identical_replay_idempotent(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(reviewed)
        normalized = normalize_human_confirm_events([event, event], reviewed)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].confirm_event_id, event.confirm_event_id)

    def test_16_same_id_different_payload_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        a = _confirm_event(reviewed, actor_id="operator-1")
        b = _confirm_event(reviewed, actor_id="operator-2")
        with self.assertRaises(HumanConfirmContractError) as raised:
            normalize_human_confirm_events([a, b], reviewed)
        self.assertIn("conflicting replay", str(raised.exception))

    def test_17_second_distinct_confirm_same_package_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        a = _confirm_event(reviewed, confirm_event_id="confirm-1")
        b = _confirm_event(reviewed, confirm_event_id="confirm-2")
        with self.assertRaises(HumanConfirmContractError) as raised:
            normalize_human_confirm_events([a, b], reviewed)
        self.assertIn("one distinct confirm_event_id", str(raised.exception))


class HumanConfirmProjectionTests(unittest.TestCase):
    def test_18_zero_confirms_not_confirmed(self) -> None:
        reviewed = _confirmable_reviewed()
        effective = project_effective_human_confirm((), reviewed)
        self.assertIsNone(effective)

    def test_19_one_valid_event_effective_confirm(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(reviewed)
        effective = project_effective_human_confirm([event], reviewed)
        self.assertIsNotNone(effective)
        assert effective is not None
        self.assertEqual(effective.confirm_event_id, event.confirm_event_id)

    def test_20_identical_replay_same_effective_confirm(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(reviewed)
        a = project_effective_human_confirm([event], reviewed)
        b = project_effective_human_confirm([event, event], reviewed)
        self.assertEqual(a, b)
        self.assertEqual(a.confirm_event_id if a else None, event.confirm_event_id)


class HumanConfirmSemanticsIsolationTests(unittest.TestCase):
    def test_23_24_no_handoff_or_hitl_objects(self) -> None:
        reviewed = _confirmable_reviewed()
        event = _confirm_event(reviewed)
        assert_no_handoff_or_commitment_semantics(event)
        payload = human_confirm_event_as_dict(event)
        for forbidden in (
            "handoff_id",
            "handoff_ready",
            "interrupt_id",
            "CLARIFY_SCOPE",
            "ABORT_RUN",
            "monthly_commitment",
            "executability_accepted",
        ):
            self.assertNotIn(forbidden, payload)
            self.assertNotIn(forbidden, payload.values())

    def test_25_26_no_persistence_or_commitment_fields(self) -> None:
        from dataclasses import fields

        names = {f.name for f in fields(HumanConfirmEvent)}
        forbidden = {
            "persisted",
            "durable",
            "sqlite",
            "supabase",
            "monthly_commitment",
            "approved_month",
            "handoff_id",
        }
        self.assertFalse(names & forbidden)

    def test_module_isolation(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/human_confirm_contracts.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "import streamlit",
            "from streamlit",
            "import langgraph",
            "from langgraph",
            "supabase",
            "subprocess",
            "uuid.uuid4",
            "datetime.now(",
            "sqlite3",
            "hitl_resume",
            "handoff_contracts",
            "langgraph_runtime",
            "shadow_hitl",
        ):
            self.assertNotIn(forbidden, source)

    def test_naive_confirmed_at_fail_closed(self) -> None:
        reviewed = _confirmable_reviewed()
        with self.assertRaises(HumanConfirmContractError) as raised:
            _confirm_event(
                reviewed,
                confirmed_at=datetime(2026, 10, 8, 14, 0, 0),
            )
        self.assertIn("timezone-aware UTC", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
