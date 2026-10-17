"""FS-PI-001: mid-session untrusted instruction must not authorise new consequences.

This bounded test models the *result* of a prompt injection, not an LLM
interpreting malicious content. A legitimate permit is minted for an approved
payment. An untrusted instruction attempts to substitute a new recipient,
target and purpose using that same permit. Only the original exact action may
form a represented consequence.
"""
from dataclasses import replace
from pathlib import Path

from harness.runner import load_scenario
from app.engines.runtime_authority_payment import (
    prepare_payment_execution, final_bind_payment, mint_rai_bound_execution_permit,
)
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.protected_consequence import execute_protected_consequence

SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def _attempt(req):
    return ExecutionAttempt(
        actor_id=req.actor_id, principal_id=req.principal_id,
        action=req.action, target=req.target, amount=req.amount,
        currency=req.currency, source_account=req.source_account,
        beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose, mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time,
    )


def test_fs_pi_001_injected_recipient_and_purpose_cannot_use_valid_session_permit():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert final.status == "PERMITTED", f"Initial authorised action not permitted: {final}"
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time,
    )
    assert permit is not None, "Could not mint genuine bound permit"

    original = _attempt(req)
    original_hash = action_binding_hash(original)
    assert original_hash == permit.action_binding_hash

    # Model a malicious lower-trust document changing the requested consequence
    # after the session was legitimately authorised.
    injected = replace(
        original,
        beneficiary="UNAUTHORISED-EXTERNAL-RECIPIENT",
        beneficiary_account_reference="EXTERNAL-ACCOUNT-PI-001",
        purpose="EXFILTRATE-CONFIDENTIAL-RECORDS",
    )
    injected_hash = action_binding_hash(injected)
    assert injected_hash != original_hash

    outcome = execute_protected_consequence(permit, injected_hash)
    assert outcome == "DENIED_ACTION_BINDING_MISMATCH", outcome

    # Verify denial has not consumed the legitimate permit: an unchanged,
    # separately authorised exact consequence can still be represented.
    original_outcome = execute_protected_consequence(permit, original_hash)
    assert original_outcome == "CONSEQUENCE_FORMED", original_outcome


def test_fs_pi_001_route_or_target_substitution_must_not_reuse_permit():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert final.status == "PERMITTED"
    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time,
    )
    assert permit is not None

    original = _attempt(req)
    substituted = replace(
        original,
        target="UNAUTHORISED-PRODUCTION-TARGET",
        purpose="PROMPT-INJECTION-ROUTE-SUBSTITUTION",
    )
    outcome = execute_protected_consequence(
        permit, action_binding_hash(substituted),
    )
    assert outcome == "DENIED_ACTION_BINDING_MISMATCH", outcome
