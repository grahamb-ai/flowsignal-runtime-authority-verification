"""TCS-001: Terry Snyder's bounded 10/6/6 coupled-capacity challenge."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest

from app.engines.authority_usage import (
    _POLICIES,
    _RESERVATIONS,
    _active_amount,
    get_usage_reservation,
    reset_authority_usage_reference_state_for_test,
)
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.institutional_authority import _MANDATES
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.authority_resolution import AuthorityResolutionError
from app.engines.runtime_authority_payment import (
    mint_rai_bound_execution_permit,
    prepare_payment_execution,
)
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"
MANDATE_ID = "MANDATE-TREASURY-001"


@pytest.fixture(autouse=True)
def _bounded_capacity_10(monkeypatch):
    """Use the frozen challenge values without changing implementation logic."""
    reset_authority_usage_reference_state_for_test()
    monkeypatch.setitem(
        _MANDATES,
        MANDATE_ID,
        replace(_MANDATES[MANDATE_ID], max_amount=Decimal("10")),
    )
    yield
    reset_authority_usage_reference_state_for_test()


def _request(label: str, amount: str):
    original = load_scenario(SCENARIO, rebase_to_now=False)
    return replace(
        original,
        amount=Decimal(amount),
        institutional_operation_id=f"TCS-001-{label}",
    )


def _binding(req) -> str:
    attempt = ExecutionAttempt(
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
    return action_binding_hash(attempt)


def _prepare(req):
    return prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )


def test_tcs001_sequential_second_movement_is_refused_before_formation():
    movement_a = _request("SEQUENTIAL-A", "6")
    movement_b = _request("SEQUENTIAL-B", "6")

    prepared_a = _prepare(movement_a)
    permit_a = mint_rai_bound_execution_permit(
        movement_a,
        prepared_a,
        bind_at=movement_a.requested_execution_time,
    )
    assert permit_a is not None
    assert execute_protected_consequence(
        permit=permit_a,
        attempted_action_binding_hash=_binding(movement_a),
    ) == "CONSEQUENCE_FORMED"

    with pytest.raises(ValueError, match="aggregate authority capacity exceeded") as refused:
        _prepare(movement_b)

    reservation_a = get_usage_reservation(prepared_a.usage_reservation_id)
    assert reservation_a is not None
    assert reservation_a.state.value == "consumed"
    scope_key = _POLICIES[prepared_a.usage_policy_id].scope_key
    assert _active_amount(scope_key) == Decimal("6")
    print(
        "TCS-001 sequential: A=CONSEQUENCE_FORMED; "
        f"B=REFUSED ({refused.value}); active_burden=6; capacity=10"
    )


def test_tcs001_concurrent_movements_cannot_both_reserve_capacity():
    barrier = Barrier(2)

    def attempt(label: str):
        req = _request(label, "6")
        barrier.wait()
        try:
            return (label, "RESERVED", _prepare(req))
        except ValueError as exc:
            return (label, "REFUSED", str(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("CONCURRENT-A", "CONCURRENT-B")))

    states = sorted(result[1] for result in results)
    assert states == ["REFUSED", "RESERVED"]
    assert any(
        result[1] == "REFUSED" and result[2] == "aggregate authority capacity exceeded"
        for result in results
    )
    prepared = next(result[2] for result in results if result[1] == "RESERVED")
    scope_key = _POLICIES[prepared.usage_policy_id].scope_key
    assert _active_amount(scope_key) == Decimal("6")
    print(f"TCS-001 concurrent: {[(r[0], r[1]) for r in results]}; active_burden=6; capacity=10")


def test_tcs001_combined_burden_12_is_refused():
    combined = _request("COMBINED", "12")

    with pytest.raises(AuthorityResolutionError, match="amount outside effective mandate") as refused:
        _prepare(combined)

    assert _RESERVATIONS == {}
    print(f"TCS-001 combined: burden=12; REFUSED ({refused.value}); active_burden=0; capacity=10")
