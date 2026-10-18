"""FS-AUTH-002 concurrent authority-transition linearisation challenge.

Reference-only: a transition requested during the guarded commitment interval
must wait until the consequence has formed. This does NOT prove that a
revocation requested but not yet committed prevents that consequence.
Run in isolation because the reference stores are process-global.
"""
from pathlib import Path
from threading import Event, Thread

from harness.runner import load_scenario
from app.engines.runtime_authority_payment import (
    prepare_payment_execution, final_bind_payment, mint_rai_bound_execution_permit,
)
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.institutional_authority import (
    get_authority_snapshot, advance_authority_fence,
    issue_authority_fence_transition_capability_for_test,
)

SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


def test_fs_auth_002_concurrent_transition_serialises_with_commit():
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
    started, finished = Event(), Event()
    errors = []
    threads = []

    def transition():
        started.set()
        try:
            advance_authority_fence(
                transition_capability=issue_authority_fence_transition_capability_for_test(
                    permit.authority_fence_scope_key,
                ),
                authority_fence_scope_key=permit.authority_fence_scope_key,
            )
        except BaseException as exc:
            errors.append(repr(exc))
        finally:
            finished.set()

    def inside_commit():
        t = Thread(target=transition, name="authority-transition", daemon=True)
        threads.append(t)
        t.start()
        assert started.wait(2), "Revocation thread did not start"
        assert not finished.wait(0.15), (
            "Authority transition completed inside guarded commitment interval"
        )

    outcome = execute_protected_consequence(
        permit, exact_hash, before_formation_hook=inside_commit,
    )
    assert len(threads) == 1, f"Hook not reached; outcome={outcome}"
    threads[0].join(timeout=3)
    assert not threads[0].is_alive(), "Deadlock: transition did not finish after commit"
    assert finished.is_set() and not errors, f"Transition failed: {errors}"
    assert outcome == "CONSEQUENCE_FORMED", (
        f"Expected commit-before-transition linearisation; outcome={outcome}"
    )
    snapshot = get_authority_snapshot(req.mandate_id)
    assert snapshot is not None
    assert snapshot.authority_fence > permit.authority_fence
