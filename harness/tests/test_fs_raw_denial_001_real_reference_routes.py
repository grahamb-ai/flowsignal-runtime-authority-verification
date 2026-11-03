"""FS-RAW-DENIAL-001: two existing reference routes, one real protected
consequence component and SQLite outcome witness.

This does NOT use third-party payment rails, another application executor,
or an autonomous agent. It tests actual repository functions without test
doubles for permit mint, receipt verification, or protected execution.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash, validate_execution
from app.engines.financial_runtime import evaluate_financial
from app.engines.runtime_authority_payment import (
    prepare_payment_execution, mint_rai_bound_execution_permit,
)
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.consequence_outcome_store import get_consequence_outcome
from harness.runner import load_scenario

SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


@pytest.fixture(autouse=True)
def isolate_test_stores(tmp_path, monkeypatch):
    reset_authority_usage_reference_state_for_test()
    monkeypatch.setenv("FLOWSIGNAL_PERMIT_CONSUMPTION_STORE", str(tmp_path / "permits.sqlite3"))
    monkeypatch.setenv("FLOWSIGNAL_CONSEQUENCE_OUTCOME_STORE", str(tmp_path / "outcomes.sqlite3"))
    monkeypatch.setenv("FLOWSIGNAL_ROLLBACK_ANCHOR_STORE", str(tmp_path / "anchor.sqlite3"))
    yield
    reset_authority_usage_reference_state_for_test()


def req_now():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    now = datetime.now(timezone.utc)
    return replace(req, requested_execution_time=now,
        screening_captured_at=now,
        mandate_valid_until=now + timedelta(hours=1))


def attempt(req):
    return ExecutionAttempt(
        actor_id=req.actor_id, principal_id=req.principal_id,
        action=req.action, target=req.target, amount=req.amount,
        currency=req.currency, source_account=req.source_account,
        beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose, mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time)


def test_legacy_gateway_allow_cannot_form_rai_protected_consequence():
    """Actual legacy financial receipt path must not bypass mandatory RAI."""
    req = req_now()
    response, receipt = evaluate_financial(req, sealed_at=req.requested_execution_time)
    assert response.decision == "ALLOW"
    gw = validate_execution(receipt, attempt(req))
    assert gw.status == "PERMITTED"
    assert gw.execution_permit is not None
    assert gw.execution_permit.rai_determination_id is None
    result = execute_protected_consequence(
        gw.execution_permit, action_binding_hash(attempt(req)))
    assert result == "DENIED_RAI_EXECUTION_BINDING_REQUIRED"
    assert get_consequence_outcome(gw.execution_permit.signature,
        gw.execution_permit.action_binding_hash) is None


def test_actual_rai_route_forms_and_witnesses_one_reference_consequence():
    """Actual RAI final-bind permit path forms one represented consequence."""
    req = req_now()
    prepared = prepare_payment_execution(req, route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    permit = mint_rai_bound_execution_permit(req, prepared,
        bind_at=req.requested_execution_time)
    assert permit is not None
    binding = action_binding_hash(attempt(req))
    result = execute_protected_consequence(permit, binding)
    assert result == "CONSEQUENCE_FORMED"
    witnessed = get_consequence_outcome(permit.signature, binding)
    assert witnessed is not None and witnessed.outcome == "CONSEQUENCE_FORMED"
    again = execute_protected_consequence(permit, binding)
    assert again == "DENIED_EXECUTION_PERMIT_REPLAY"
    assert get_consequence_outcome(permit.signature, binding).outcome == "CONSEQUENCE_FORMED"


def test_raifinalbind_rejects_changed_effect_before_permit_and_outcome():
    """Changed target resource after preparation yields no valid capability."""
    req = req_now()
    prepared = prepare_payment_execution(req, route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1", resolved_at=req.requested_execution_time)
    changed = replace(req, beneficiary_account_reference="DIFFERENT-ACCOUNT")
    permit = mint_rai_bound_execution_permit(changed, prepared,
        bind_at=req.requested_execution_time)
    assert permit is None
    result = execute_protected_consequence(permit, action_binding_hash(attempt(changed)))
    assert result == "DENIED_NO_EXECUTION_PERMIT"


def test_second_route_attempt_without_permit_cannot_form_reference_consequence():
    """Alternate transport without minting cannot drive protected executor."""
    req = req_now()
    result = execute_protected_consequence(None, action_binding_hash(attempt(req)))
    assert result == "DENIED_NO_EXECUTION_PERMIT"
