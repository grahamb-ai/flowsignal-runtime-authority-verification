"""FS-CCA-001: authority revocation at the consequential boundary.

Frozen proposition:
    If authority is revoked before final bind, an attempted continuation using
    the prior authority must be refused, no execution permit may issue, and no
    protected consequence may form.

The post-mint case is recorded separately because it exercises a different
race: authority changes after final bind but before consequence formation.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from app.engines import institutional_authority as authority_state
from app.engines.authority_domain import AuthorityUsageState
from app.engines.authority_usage import (
    _FORMED_INSTITUTIONAL_OPERATIONS,
    get_usage_reservation,
    reset_authority_usage_reference_state_for_test,
)
from app.engines.consequence_outcome_store import get_consequence_outcome
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.institutional_authority import (
    advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.runtime_authority_payment import (
    final_bind_payment,
    mint_rai_bound_execution_permit,
    prepare_payment_execution,
)
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"
AUTHORITY_SCOPE_KEY = "institution-001:MANDATE-TREASURY-001"


@pytest.fixture(autouse=True)
def _isolated_reference_state(tmp_path, monkeypatch):
    reset_authority_usage_reference_state_for_test()
    # Record the current monotonic reference fence so this bounded test artifact
    # cannot change the starting authority state seen by neighbouring tests.
    monkeypatch.setattr(authority_state, "_FENCE", authority_state._FENCE)
    monkeypatch.setenv(
        "FLOWSIGNAL_PERMIT_CONSUMPTION_STORE",
        str(tmp_path / "permit-consumption.sqlite3"),
    )
    monkeypatch.setenv(
        "FLOWSIGNAL_CONSEQUENCE_OUTCOME_STORE",
        str(tmp_path / "consequence-outcomes.sqlite3"),
    )
    monkeypatch.setenv(
        "FLOWSIGNAL_ROLLBACK_ANCHOR_STORE",
        str(tmp_path / "rollback-anchor.sqlite3"),
    )
    yield
    reset_authority_usage_reference_state_for_test()


def _request(case_id: str):
    original = load_scenario(SCENARIO, rebase_to_now=False)
    return replace(
        original,
        institutional_operation_id=f"FS-CCA-001:{case_id}",
    )


def _prepare(req):
    return prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )


def _binding(req) -> str:
    return action_binding_hash(
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


def _revoke_current_authority() -> None:
    advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            AUTHORITY_SCOPE_KEY
        )
    )


def _assert_no_protected_consequence(prepared) -> None:
    reservation = get_usage_reservation(prepared.usage_reservation_id)
    assert reservation is not None
    assert reservation.state == AuthorityUsageState.RESERVED
    assert (
        prepared.operation.institutional_operation_id
        not in _FORMED_INSTITUTIONAL_OPERATIONS
    )


def test_case_01_current_authority_allows_one_bound_consequence():
    req = _request("CURRENT-AUTHORITY")
    prepared = _prepare(req)

    permit = mint_rai_bound_execution_permit(
        req,
        prepared,
        bind_at=req.requested_execution_time,
    )

    assert permit is not None
    assert execute_protected_consequence(permit, _binding(req)) == "CONSEQUENCE_FORMED"
    reservation = get_usage_reservation(prepared.usage_reservation_id)
    assert reservation is not None
    assert reservation.state == AuthorityUsageState.CONSUMED
    assert (
        prepared.operation.institutional_operation_id
        in _FORMED_INSTITUTIONAL_OPERATIONS
    )


def test_case_02_revocation_before_final_bind_refuses_without_permit_or_consequence():
    req = _request("REVOKED-BEFORE-BIND")
    prepared = _prepare(req)
    _revoke_current_authority()

    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    permit = mint_rai_bound_execution_permit(
        req,
        prepared,
        bind_at=req.requested_execution_time,
    )

    assert final.status == "BLOCKED"
    assert final.reason_code == "AUTHORITY_CONTEXT_CHANGED"
    assert permit is None
    assert execute_protected_consequence(permit, _binding(req)) == "DENIED_NO_EXECUTION_PERMIT"
    _assert_no_protected_consequence(prepared)


def test_case_03_stale_prepared_authority_remains_refused_on_replay():
    req = _request("STALE-PREPARED-REPLAY")
    prepared = _prepare(req)
    _revoke_current_authority()

    first = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    second = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)

    assert (first.status, first.reason_code) == ("BLOCKED", "AUTHORITY_CONTEXT_CHANGED")
    assert (second.status, second.reason_code) == ("BLOCKED", "AUTHORITY_CONTEXT_CHANGED")
    assert mint_rai_bound_execution_permit(
        req,
        prepared,
        bind_at=req.requested_execution_time,
    ) is None
    _assert_no_protected_consequence(prepared)


def test_case_04_operation_mutation_is_not_misreported_as_authority_revocation():
    req = _request("OPERATION-MUTATION")
    prepared = _prepare(req)
    mutated = replace(req, beneficiary="ATTACKER-BENEFICIARY")

    final = final_bind_payment(mutated, prepared, bind_at=req.requested_execution_time)

    assert final.status == "BLOCKED"
    assert final.reason_code == "PROTECTED_OPERATION_CHANGED"
    assert mint_rai_bound_execution_permit(
        mutated,
        prepared,
        bind_at=req.requested_execution_time,
    ) is None
    _assert_no_protected_consequence(prepared)


def test_case_05_revocation_after_permit_mint_blocks_before_consequence_formation():
    req = _request("REVOKED-AFTER-MINT")
    prepared = _prepare(req)
    permit = mint_rai_bound_execution_permit(
        req,
        prepared,
        bind_at=req.requested_execution_time,
    )
    assert permit is not None
    _revoke_current_authority()

    binding = _binding(req)
    outcome = execute_protected_consequence(permit, binding)

    assert outcome == "DENIED_AUTHORITY_SNAPSHOT_STALE"
    recorded = get_consequence_outcome(permit.signature, binding)
    assert recorded is not None
    assert recorded.outcome == "CONSEQUENCE_OUTCOME_UNRESOLVED"
    assert (
        execute_protected_consequence(permit, binding)
        == "DENIED_EXECUTION_PERMIT_REPLAY"
    )
    _assert_no_protected_consequence(prepared)
