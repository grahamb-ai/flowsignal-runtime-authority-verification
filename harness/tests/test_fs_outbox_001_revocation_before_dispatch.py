"""FS-OUTBOX-001 — revocation after enqueue, before external dispatch.

Bounded reference simulation: an outbox item is not an execution permit. The
worker must use the exact genuine permit and current authority at dispatch.
No real network, provider acceptance, or distributed transaction is modelled.
"""
from pathlib import Path
from dataclasses import dataclass

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


@dataclass(frozen=True)
class OutboxItem:
    permit: object
    action_hash: str


class ExternalActuatorSpy:
    def __init__(self):
        self.dispatches = []

    def dispatch(self, item):
        self.dispatches.append(item.action_hash)


def _enqueue_authorised_action():
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
    assert permit.action_binding_hash == h
    return OutboxItem(permit, h)


def _worker_dispatch(item, actuator):
    # The outbox entry is merely a queued proposal. Dispatch requires fresh
    # authority at the protected consequence boundary.
    outcome = execute_protected_consequence(item.permit, item.action_hash)
    if outcome == "CONSEQUENCE_FORMED":
        actuator.dispatch(item)
    return outcome


def test_fs_outbox_001_global_revocation_before_dispatch_blocks_actuator():
    item = _enqueue_authorised_action()
    actuator = ExternalActuatorSpy()
    advance_authority_state_version()
    outcome = _worker_dispatch(item, actuator)
    assert outcome != "CONSEQUENCE_FORMED", outcome
    assert actuator.dispatches == [], "External actuator received revoked action"


def test_fs_outbox_001_institutional_revocation_before_dispatch_blocks_actuator():
    item = _enqueue_authorised_action()
    actuator = ExternalActuatorSpy()
    advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            item.permit.authority_fence_scope_key,
        ),
        authority_fence_scope_key=item.permit.authority_fence_scope_key,
    )
    outcome = _worker_dispatch(item, actuator)
    assert outcome != "CONSEQUENCE_FORMED", outcome
    assert actuator.dispatches == [], "External actuator received revoked action"


def test_fs_outbox_001_unchanged_authority_dispatches_once():
    item = _enqueue_authorised_action()
    actuator = ExternalActuatorSpy()
    first = _worker_dispatch(item, actuator)
    second = _worker_dispatch(item, actuator)
    assert first == "CONSEQUENCE_FORMED", first
    assert second != "CONSEQUENCE_FORMED", second
    assert actuator.dispatches == [item.action_hash], actuator.dispatches
