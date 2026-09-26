from pathlib import Path

from app.engines.institutional_authority import (
    advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)
from app.engines.runtime_authority_payment import final_bind_payment, prepare_payment_execution
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


import pytest
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test


@pytest.fixture(autouse=True)
def _isolate_authority_usage_reference_state():
    # Independent tests must not inherit process-local aggregate reservations.
    # Multiple exercises inside one test still share the same state.
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()


def test_integrated_payment_path_reaches_final_bind_with_exact_lineage():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time
    )
    result = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert result.status == "PERMITTED"
    assert result.authority_exercise_id == prepared.determination.authority_exercise_id
    assert result.execution_attempt_id == prepared.determination.execution_attempt_id


def test_integrated_path_blocks_when_authority_changes_before_bind():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time
    )
    advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            "institution-001:MANDATE-TREASURY-001"
        ),
    )
    result = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert result.status == "BLOCKED"
    assert result.reason_code == "AUTHORITY_CONTEXT_CHANGED"


def test_integrated_path_blocks_operation_substitution_before_bind():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req, route_id="R1", executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time
    )
    req.beneficiary = "SUBSTITUTED-BENEFICIARY"
    result = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    assert result.status == "BLOCKED"
    assert result.reason_code == "PROTECTED_OPERATION_CHANGED"
