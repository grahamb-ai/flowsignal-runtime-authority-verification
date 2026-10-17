"""FS-CONC-001: deterministic two-thread authority/commit schedules.

These are controlled, replayable schedules, NOT exhaustive interleaving
exploration, Hypothesis stateful testing, or TLA+ model checking.
"""
from pathlib import Path
from threading import Event, Thread
from dataclasses import dataclass

import pytest
from harness.runner import load_scenario
from app.engines.runtime_authority_payment import (
    prepare_payment_execution, final_bind_payment, mint_rai_bound_execution_permit,
)
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.institutional_authority import (
    advance_authority_fence, get_authority_snapshot,
    issue_authority_fence_transition_capability_for_test,
)
from app.engines.authority_store import (
    advance_authority_state_version, get_authority_state_version,
)

SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def _permit():
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
    return req, permit, h


def _transition(kind, permit):
    if kind == "global":
        return advance_authority_state_version()
    return advance_authority_fence(
        transition_capability=issue_authority_fence_transition_capability_for_test(
            permit.authority_fence_scope_key,
        ),
        authority_fence_scope_key=permit.authority_fence_scope_key,
    )


@pytest.mark.parametrize("kind", ["global", "institutional"])
def test_effective_transition_before_execution_refuses(kind):
    req, permit, h = _permit()
    _transition(kind, permit)
    outcome = execute_protected_consequence(permit, h)
    assert outcome != "CONSEQUENCE_FORMED", (kind, outcome)


@pytest.mark.parametrize("kind", ["global", "institutional"])
def test_transition_waits_during_commit_then_completes(kind):
    req, permit, h = _permit()
    started, finished = Event(), Event()
    errors = []
    threads = []

    def transition():
        started.set()
        try:
            _transition(kind, permit)
        except BaseException as exc:
            errors.append(repr(exc))
        finally:
            finished.set()

    def hook():
        t = Thread(target=transition, daemon=True)
        threads.append(t)
        t.start()
        assert started.wait(2), "Transition thread did not start"
        assert not finished.wait(0.15), (
            "Authority transition completed inside commitment guard"
        )

    outcome = execute_protected_consequence(
        permit, h, before_formation_hook=hook,
    )
    assert len(threads) == 1, "Commit injection was not reached"
    threads[0].join(3)
    assert not threads[0].is_alive(), "Possible deadlock: transition thread still alive"
    assert finished.is_set() and not errors, errors
    assert outcome == "CONSEQUENCE_FORMED", outcome
    if kind == "global":
        assert get_authority_state_version() > permit.authority_state_version
    else:
        snap = get_authority_snapshot(req.mandate_id)
        assert snap is not None and snap.authority_fence > permit.authority_fence
