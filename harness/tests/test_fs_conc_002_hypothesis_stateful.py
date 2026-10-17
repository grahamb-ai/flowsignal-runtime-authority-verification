"""FS-CONC-002: Hypothesis state-machine exploration of authority/commit sequences.

This models sequential transitions and same-thread injected changes. It is not
exhaustive thread interleaving enumeration or distributed atomic CAS proof.
"""
from pathlib import Path
from threading import Event, Thread

from hypothesis import HealthCheck, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

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


def _make_permit():
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


class AuthorityCommitMachine(RuleBasedStateMachine):
    @initialize()
    def setup(self):
        self.permit, self.action_hash = _make_permit()
        self.changed = False
        self.formed = False
        self.attempted = False

    @rule(kind=st.sampled_from(["global", "institutional"]))
    def change_authority(self, kind):
        if kind == "global":
            advance_authority_state_version()
        else:
            advance_authority_fence(
                transition_capability=issue_authority_fence_transition_capability_for_test(
                    self.permit.authority_fence_scope_key,
                ),
                authority_fence_scope_key=self.permit.authority_fence_scope_key,
            )
        self.changed = True

    @rule()
    def attempt_execution(self):
        outcome = execute_protected_consequence(self.permit, self.action_hash)
        self.attempted = True
        if self.changed:
            assert outcome != "CONSEQUENCE_FORMED", (
                "Consequence formed after effective authority change", outcome
            )
        if outcome == "CONSEQUENCE_FORMED":
            assert not self.formed, "Duplicate consequence formation"
            self.formed = True

    @rule(kind=st.sampled_from(["global", "institutional", "both"]))
    def inject_change_during_commit(self, kind):
        called = []

        def inject():
            if kind in ("global", "both"):
                advance_authority_state_version()
            if kind in ("institutional", "both"):
                advance_authority_fence(
                    transition_capability=issue_authority_fence_transition_capability_for_test(
                        self.permit.authority_fence_scope_key,
                    ),
                    authority_fence_scope_key=self.permit.authority_fence_scope_key,
                )
            called.append(kind)

        outcome = execute_protected_consequence(
            self.permit, self.action_hash, before_formation_hook=inject,
        )
        if called:
            assert outcome != "CONSEQUENCE_FORMED", (
                "Consequence formed after injected authority change", kind, outcome
            )
            self.changed = True
        if outcome == "CONSEQUENCE_FORMED":
            assert not self.formed
            self.formed = True

    @invariant()
    def no_duplicate_formation(self):
        assert isinstance(self.formed, bool)


TestAuthorityCommitMachine = AuthorityCommitMachine.TestCase
TestAuthorityCommitMachine.settings = settings(
    max_examples=30,
    stateful_step_count=8,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    print_blob=True,
)
