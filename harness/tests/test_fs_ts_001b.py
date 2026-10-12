from pathlib import Path

from harness.runner import load_scenario
from app.engines.runtime_authority_payment import (
    prepare_payment_execution,
    mint_rai_bound_execution_permit,
)
from app.engines.institutional_authority import (
    advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test

SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def test_fs_ts_001b_issued_permit_cannot_survive_authority_change():
    reset_authority_usage_reference_state_for_test()
    req = load_scenario(SCENARIO, rebase_to_now=False)

    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )

    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None, "Valid initial permit was not issued"

    attempted_hash = action_binding_hash(
        ExecutionAttempt(
            actor_id=req.actor_id,
            principal_id=req.principal_id,
            action=req.action,
            target=req.target,
            amount=req.amount,
            currency=req.currency,
            source_account=req.source_account,
            beneficiary=req.beneficiary,
            beneficiary_account_reference=req.beneficiary_account_reference,
            purpose=req.purpose,
            mandate_id=req.mandate_id,
            attempted_at=req.requested_execution_time,
        )
    )

    advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            "institution-001:MANDATE-TREASURY-001"
        )
    )

    outcome = execute_protected_consequence(permit, attempted_hash)
    print(f"FS-TS-001B EXECUTOR OUTCOME: {outcome}")

    assert outcome != "CONSEQUENCE_FORMED", (
        "FS-TS-001B RED: stale authority formed a consequence"
    )
    assert outcome in {
        "DENIED_AUTHORITY_SNAPSHOT_STALE",
        "DENIED_AUTHORITY_FENCE_STALE",
    }, f"Unexpected executor rejection: {outcome}"
