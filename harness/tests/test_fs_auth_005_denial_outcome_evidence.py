"""FS-AUTH-005: denial must preserve unresolved outcome and quarantined usage.

Run in an isolated process. No remediation here. A first RED must be preserved.
"""
from pathlib import Path

from harness.runner import load_scenario
from app.engines.runtime_authority_payment import (
    prepare_payment_execution, final_bind_payment, mint_rai_bound_execution_permit,
)
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.consequence_outcome_store import get_consequence_outcome
from app.engines.authority_usage import get_usage_reservation
from app.engines.authority_domain import AuthorityUsageState
from app.engines.authority_store import advance_authority_state_version, get_authority_state_version
from app.engines.institutional_authority import (
    get_authority_snapshot, advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)

SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def test_fs_auth_005_denial_records_remain_consistent():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert final.status == "PERMITTED", f"Baseline final bind not green: {final}"
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time,
    )
    assert permit is not None, "No genuine RAI-bound permit: inconclusive"
    attempt = ExecutionAttempt(
        actor_id=req.actor_id, principal_id=req.principal_id,
        action=req.action, target=req.target, amount=req.amount,
        currency=req.currency, source_account=req.source_account,
        beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose, mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time,
    )
    exact_hash = action_binding_hash(attempt)
    assert permit.action_binding_hash == exact_hash
    transitions = []

    def revoke_inside_commit():
        before = get_authority_state_version()
        after = advance_authority_state_version()
        assert after > before
        transitions.append((before, after))

    outcome = execute_protected_consequence(
        permit, exact_hash, before_formation_hook=revoke_inside_commit,
    )
    assert len(transitions) == 1, (
        f"Injection not reached; outcome={outcome!r}; inconclusive"
    )
    assert outcome == "DENIED_AUTHORITY_STATE_CHANGED_DURING_COMMIT", outcome
    record = get_consequence_outcome(permit.signature, exact_hash)
    assert record is not None, "Consumed permit has no durable outcome record"
    assert record.outcome == "CONSEQUENCE_OUTCOME_UNRESOLVED", record.outcome
    reservation = get_usage_reservation(prepared.usage_reservation_id)
    assert reservation is not None
    assert reservation.state == AuthorityUsageState.QUARANTINED, reservation.state
    replay = execute_protected_consequence(permit, exact_hash)
    assert replay == "DENIED_EXECUTION_PERMIT_REPLAY", replay
    assert get_consequence_outcome(permit.signature, exact_hash).outcome == "CONSEQUENCE_OUTCOME_UNRESOLVED"
