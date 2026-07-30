"""
August passport dry-run (NO writes).

Shows what replace would do for PRJ_001_БХК / август-2026
with expected test BOQs — without calling RPC.

Run: python _tmp_august_passport_dry_run.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from services import monthly_passport_service as mps
from services.supabase_client import supabase

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

PROJECT = "PRJ_001_БХК"
MONTH = "август-2026"
EXPECTED_BOQS = [
    "1800-01-02-01",
    "2041-01-27-02",
    "1500-04-01-01",
    "1500-05-02-07",
]


def main() -> None:
    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY"),
    )

    existing = (
        client.table("monthly_plan_passports")
        .select("passport_id,passport_status,rows_count,approved_at,created_at")
        .eq("project_code", PROJECT)
        .eq("month_key", MONTH)
        .execute()
        .data
        or []
    )
    active = [p for p in existing if p.get("passport_status") not in ("SUPERSEDED", "CANCELLED")]
    passport_id = active[0]["passport_id"] if len(active) == 1 else None
    previous_rows = 0
    previous_boqs: list[str] = []
    if passport_id:
        lines = (
            client.table("monthly_plan_passport_lines")
            .select("line_id,boq_code,admission_status")
            .eq("passport_id", passport_id)
            .execute()
            .data
            or []
        )
        previous_rows = len(lines)
        previous_boqs = [str(x.get("boq_code")) for x in lines]

    source_rows, src_errors, source_kind = mps.load_passport_source_rows(
        supabase, PROJECT, MONTH
    )
    line_ids = [str(r.get("line_id")) for r in source_rows if r.get("line_id")]
    constraints = mps._fetch_constraints_for_lines(line_ids)

    eligible: list[dict] = []
    skip: list[dict] = []
    for row in source_rows:
        lid = str(row.get("line_id") or "")
        counts = mps._count_constraints(constraints.get(lid, []))
        override = mps._read_override_from_queue(row)
        admission = mps._resolve_admission_status(counts, override["management_override"])
        item = {
            "boq_code": row.get("boq_code"),
            "line_id": lid,
            "admission_plain": admission,
            "counts": counts,
            "needs_override_for_keep": admission in ("WAITING_CHECKS", "BLOCKED", "NO_CHECKS"),
        }
        if admission in mps.INCLUDED_STATUSES:
            eligible.append(item)
        else:
            skip.append(item)

    # Simulate War Room: INCLUDE + override for all expected BOQs present in source
    simulated_with_override: list[dict] = []
    for row in source_rows:
        boq = str(row.get("boq_code") or "")
        if boq not in EXPECTED_BOQS:
            continue
        lid = str(row.get("line_id") or "")
        counts = mps._count_constraints(constraints.get(lid, []))
        admission = mps._resolve_admission_status(counts, True)
        if admission in ("BLOCKED", "WAITING_CHECKS"):
            admission = "APPROVED_BY_OVERRIDE"
        if admission in mps.INCLUDED_STATUSES:
            payload = mps._line_payload_for_rpc(
                mps._build_passport_line(
                    passport_id=mps.PLACEHOLDER_PASSPORT_ID,
                    source_row=row,
                    counts=counts,
                    admission_status=admission,
                    override={
                        "management_override": True,
                        "override_by": "dry-run",
                        "override_at": None,
                        "override_reason": "dry-run",
                        "override_risk_comment": "dry-run",
                        "override_basis": "dry-run",
                    },
                )
            )
            simulated_with_override.append(payload)

    validation = mps.validate_passport_line_payloads(
        PROJECT, MONTH, simulated_with_override
    )

    expected_status = "rebuilt" if passport_id else "created"
    report = {
        "project_code": PROJECT,
        "month_key": MONTH,
        "existing_passports": existing,
        "active_passport_id": passport_id,
        "active_passport_count": len(active),
        "previous_rows": previous_rows,
        "previous_boqs": previous_boqs,
        "source_kind": source_kind,
        "source_errors": src_errors,
        "source_row_count": len(source_rows),
        "source_boqs": [r.get("boq_code") for r in source_rows],
        "eligible_without_war_room_override": eligible,
        "skipped_without_override": skip,
        "expected_test_boqs": EXPECTED_BOQS,
        "expected_boqs_in_source": [
            b for b in EXPECTED_BOQS if b in {str(r.get("boq_code")) for r in source_rows}
        ],
        "composition_count_simulated_include_all_expected": len(simulated_with_override),
        "generated_line_count": len(simulated_with_override),
        "coverage_gaps": [
            b
            for b in EXPECTED_BOQS
            if b not in {str(x.get("boq_code")) for x in simulated_with_override}
        ],
        "override_errors_validation": validation,
        "expected_rpc_status": expected_status,
        "product_write": False,
        "note": (
            "Without War Room inclusion+override patches, plain create_monthly_passport "
            "would skip WAITING/BLOCKED lines. Dry-run simulates INCLUDE+override for "
            "the four expected BOQs. Apply SQL migration before real rebuild."
        ),
    }
    out = ROOT / "_tmp_august_passport_dry_run.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
