from pathlib import Path

from harness.runner import load_scenario
from app.engines.runtime_authority_payment import (
    prepare_payment_execution,
    final_bind_payment,
    mint_rai_bound_execution_permit,
)
from app.engines.institutional_authority import (
    advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)

SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def test_fs_ts_001_authoritative_change_prevents_permit_issuance():
    req = load_scenario(SCENARIO, rebase_to_now=False)

    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )

    original_operation_id = prepared.operation.operation_id

    advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            "institution-001:MANDATE-TREASURY-001"
        )
    )

    final = final_bind_payment(
        req, prepared, bind_at=req.requested_execution_time
    )

    assert prepared.operation.operation_id == original_operation_id
    assert final.status == "BLOCKED"
    assert final.reason_code == "AUTHORITY_CONTEXT_CHANGED"
    assert final.causal_grant_id is None

    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )

    assert permit is None, (
        "FS-TS-001 RED: permit issued after authoritative state changed"
    )
