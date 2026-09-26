from decimal import Decimal
from uuid import uuid4

import pytest

from app.engines.authority_domain import AuthorityUsageMode, AuthorityUsagePolicy
from app.engines.authority_usage import (
    _POLICY_REGISTRATION_CAPABILITY,
    consume_authority_usage,
    get_usage_reservation,
    quarantine_authority_usage,
    register_usage_policy,
    release_authority_usage,
    reserve_authority_usage,
)


def _id(prefix):
    return f"{prefix}-{uuid4()}"


def test_single_use_authority_cannot_multiply_across_attempts():
    policy = AuthorityUsagePolicy(
        usage_policy_id=_id("POL"), authority_scope_id="SCOPE-1",
        mode=AuthorityUsageMode.SINGLE, scope_key=_id("SINGLE"),
        capacity=1, window_id=None, disposition_rule_id="RULE-SINGLE"
    )
    register_usage_policy(policy, registration_capability=_POLICY_REGISTRATION_CAPABILITY)
    reserve_authority_usage(
        reservation_id=_id("RES"), usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-1", execution_attempt_id="ATT-1", amount_or_units=1
    )
    with pytest.raises(ValueError, match="single-use"):
        reserve_authority_usage(
            reservation_id=_id("RES"), usage_policy_id=policy.usage_policy_id,
            authority_exercise_id="EX-1", execution_attempt_id="ATT-2", amount_or_units=1
        )


def test_aggregate_reservations_cannot_oversubscribe_capacity():
    scope_key = _id("AGG")
    policy = AuthorityUsagePolicy(
        usage_policy_id=_id("POL"), authority_scope_id="SCOPE-AGG",
        mode=AuthorityUsageMode.AGGREGATE, scope_key=scope_key,
        capacity=Decimal("1000000.00"), window_id="DAY-1",
        disposition_rule_id="RULE-AGG"
    )
    register_usage_policy(policy, registration_capability=_POLICY_REGISTRATION_CAPABILITY)
    reserve_authority_usage(
        reservation_id=_id("RES"), usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-A", execution_attempt_id="ATT-A",
        amount_or_units=Decimal("750000.00")
    )
    with pytest.raises(ValueError, match="capacity exceeded"):
        reserve_authority_usage(
            reservation_id=_id("RES"), usage_policy_id=policy.usage_policy_id,
            authority_exercise_id="EX-B", execution_attempt_id="ATT-B",
            amount_or_units=Decimal("750000.00")
        )


def test_unresolved_outcome_quarantines_and_does_not_refund_authority():
    scope_key = _id("UNRES")
    policy = AuthorityUsagePolicy(
        usage_policy_id=_id("POL"), authority_scope_id="SCOPE-U",
        mode=AuthorityUsageMode.SINGLE, scope_key=scope_key,
        capacity=1, window_id=None, disposition_rule_id="RULE-U"
    )
    register_usage_policy(policy, registration_capability=_POLICY_REGISTRATION_CAPABILITY)
    rid = _id("RES")
    reserve_authority_usage(
        reservation_id=rid, usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-U1", execution_attempt_id="ATT-U1", amount_or_units=1
    )
    quarantine_authority_usage(rid, evidence_ids=("EXECUTION-UNRESOLVED-1",))
    assert get_usage_reservation(rid).state.value == "quarantined"
    with pytest.raises(ValueError, match="single-use"):
        reserve_authority_usage(
            reservation_id=_id("RES"), usage_policy_id=policy.usage_policy_id,
            authority_exercise_id="EX-U2", execution_attempt_id="ATT-U2", amount_or_units=1
        )


def test_release_requires_positive_nonformation_evidence():
    policy = AuthorityUsagePolicy(
        usage_policy_id=_id("POL"), authority_scope_id="SCOPE-R",
        mode=AuthorityUsageMode.SINGLE, scope_key=_id("REL"),
        capacity=1, window_id=None, disposition_rule_id="RULE-R"
    )
    register_usage_policy(policy, registration_capability=_POLICY_REGISTRATION_CAPABILITY)
    rid = _id("RES")
    reserve_authority_usage(
        reservation_id=rid, usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-R", execution_attempt_id="ATT-R", amount_or_units=1
    )
    with pytest.raises(ValueError, match="non-formation evidence"):
        release_authority_usage(rid, evidence_ids=())


def test_demonstrable_nonformation_can_release_then_allow_new_reservation():
    scope_key = _id("REL2")
    policy = AuthorityUsagePolicy(
        usage_policy_id=_id("POL"), authority_scope_id="SCOPE-R2",
        mode=AuthorityUsageMode.SINGLE, scope_key=scope_key,
        capacity=1, window_id=None, disposition_rule_id="RULE-R2"
    )
    register_usage_policy(policy, registration_capability=_POLICY_REGISTRATION_CAPABILITY)
    first = _id("RES")
    reserve_authority_usage(
        reservation_id=first, usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-R1", execution_attempt_id="ATT-R1", amount_or_units=1
    )
    release_authority_usage(first, evidence_ids=("COMPETENT-NONFORMATION-1",))
    second = reserve_authority_usage(
        reservation_id=_id("RES"), usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-R2", execution_attempt_id="ATT-R2", amount_or_units=1
    )
    assert second.state.value == "reserved"


def test_formed_commitment_consumes_authority():
    policy = AuthorityUsagePolicy(
        usage_policy_id=_id("POL"), authority_scope_id="SCOPE-C",
        mode=AuthorityUsageMode.SINGLE, scope_key=_id("CONSUME"),
        capacity=1, window_id=None, disposition_rule_id="RULE-C"
    )
    register_usage_policy(policy, registration_capability=_POLICY_REGISTRATION_CAPABILITY)
    rid = _id("RES")
    reserve_authority_usage(
        reservation_id=rid, usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-C", execution_attempt_id="ATT-C", amount_or_units=1
    )
    consume_authority_usage(rid, evidence_ids=("COMMITMENT-EVIDENCE-1",))
    assert get_usage_reservation(rid).state.value == "consumed"


def test_quarantined_aggregate_usage_remains_capacity_consuming_until_resolved():
    """Failure-first: unresolved aggregate usage must not silently refund capacity."""
    scope_key = _id("AGG-UNRES")
    policy = AuthorityUsagePolicy(
        usage_policy_id=_id("POL"), authority_scope_id="SCOPE-AGG-U",
        mode=AuthorityUsageMode.AGGREGATE, scope_key=scope_key,
        capacity=Decimal("1000000.00"), window_id="DAY-U",
        disposition_rule_id="RULE-AGG-U"
    )
    register_usage_policy(policy, registration_capability=_POLICY_REGISTRATION_CAPABILITY)
    first = _id("RES")
    reserve_authority_usage(
        reservation_id=first, usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-AGG-U1", execution_attempt_id="ATT-AGG-U1",
        amount_or_units=Decimal("750000.00")
    )
    quarantine_authority_usage(first, evidence_ids=("OUTCOME-UNRESOLVED-AGG-1",))
    assert get_usage_reservation(first).state.value == "quarantined"

    with pytest.raises(ValueError, match="capacity exceeded"):
        reserve_authority_usage(
            reservation_id=_id("RES"), usage_policy_id=policy.usage_policy_id,
            authority_exercise_id="EX-AGG-U2", execution_attempt_id="ATT-AGG-U2",
            amount_or_units=Decimal("300000.00")
        )
