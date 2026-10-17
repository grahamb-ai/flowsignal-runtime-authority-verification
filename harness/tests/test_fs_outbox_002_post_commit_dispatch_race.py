"""FS-OUTBOX-002 failure-first: revocation after local commitment before dispatch.

This demonstrates the gap between local CONSEQUENCE_FORMED representation and
an external actuator call. A deliberately paused reference worker is released
only after revocation is effective. No network or payment provider is involved.
"""
from pathlib import Path

from harness.runner import load_scenario
from app.engines.runtime_authority_payment import (
    prepare_payment_execution, final_bind_payment, mint_rai_bound_execution_permit,
)
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.authority_store import advance_authority_state_version
from app.engines.institutional_authority import (
    advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)

SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def _authorised_outbox_item():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    assert final_bind_payment(
        req, prepared, bind_at=req.requested_execution_time,
    ).status == "PERMITTED"
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time,
    )
    assert permit is not None
    attempt = ExecutionAttempt(
        actor_id=req.actor_id, principal_id=req.principal_id,
        action=req.action, target=req.target, amount=req.amount,
        currency=req.currency, source_account=req.source_account,
        beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose, mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time,
    )
    h = action_binding_hash(attempt)
    assert h == permit.action_binding_hash
    return permit, h


def _revocation(kind, permit):
    if kind == "global":
        advance_authority_state_version()
    else:
        advance_authority_fence(
            transition_capability=issue_authority_fence_transition_capability_for_test(
                permit.authority_fence_scope_key,
            ),
            authority_fence_scope_key=permit.authority_fence_scope_key,
        )


def _worker_with_post_commit_pause(kind):
    permit, h = _authorised_outbox_item()
    actuator_calls = []
    local_outcome = execute_protected_consequence(permit, h)
    assert local_outcome == "CONSEQUENCE_FORMED", (
        "Local commit never succeeded; test inconclusive", local_outcome
    )

    # Deterministic paused-worker boundary: authority changes AFTER local
    # commitment but BEFORE the worker calls the external actuator.
    _revocation(kind, permit)

    # Existing FS-OUTBOX-001 reference worker: local formation alone is
    # sufficient to dispatch. Deliberately do not add a check in this challenge.
    if local_outcome == "CONSEQUENCE_FORMED":
        actuator_calls.append(h)

    assert actuator_calls == [], (
        f"FS-OUTBOX-002 FIRST RED: {kind} authority revoked after local "
        f"commit but external actuator received dispatch"
    )


def test_fs_outbox_002_global_revocation_after_commit_must_block_dispatch():
    _worker_with_post_commit_pause("global")


def test_fs_outbox_002_institutional_revocation_after_commit_must_block_dispatch():
    _worker_with_post_commit_pause("institutional")
