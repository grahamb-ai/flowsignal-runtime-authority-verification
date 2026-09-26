from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.engines.approval_authority import (
    ApprovalGrant,
    ApprovalRule,
    register_approval_grant,
    register_approval_rule,
    resolve_approval,
)


NOW = datetime(2026, 9, 24, 11, 30, tzinfo=timezone.utc)


def _req():
    return SimpleNamespace(
        principal_id="institution-001", mandate_id="MANDATE-TREASURY-001",
        action="payment.release", target="TREASURY_PAYMENT_GATEWAY",
        source_account="TREASURY-001", beneficiary="SUPPLIER-X",
        amount=Decimal("750000.00"), currency="GBP", purpose="supplier payment",
        approval_required=False,
    )


def _rule():
    return ApprovalRule(
        approval_rule_id="TEST:approval:2of2",
        operation_class="treasury.payment.test-r3",
        required=True, quorum=2,
        eligible_role_ids=("TREASURY_APPROVER", "RISK_APPROVER"),
        require_distinct_authority_subjects=True,
        required_role_ids=("TREASURY_APPROVER", "RISK_APPROVER"),
        survival_rule_id="TEST:approval-survival",
    )


def _grant(grant_id, subject, role, approval_rule_id, **changes):
    values = dict(
        approval_grant_id=grant_id, approval_rule_id=approval_rule_id, authority_subject_id=subject, role_id=role,
        principal_id="institution-001", mandate_id="MANDATE-TREASURY-001",
        action="payment.release", target="TREASURY_PAYMENT_GATEWAY",
        source_account="TREASURY-001", beneficiary_id="SUPPLIER-X",
        currency="GBP", max_amount_text="1000000.00", purpose="supplier payment",
        approved_at=NOW-timedelta(minutes=5), valid_until=NOW+timedelta(minutes=5),
        standing_version="1",
    )
    values.update(changes)
    return ApprovalGrant(**values)


def test_request_boolean_does_not_create_approval():
    rule = _rule()
    register_approval_rule(rule)
    req = _req()
    req.approval_required = False
    with pytest.raises(ValueError, match="quorum"):
        resolve_approval(req, operation_class=rule.operation_class, resolved_at=NOW)


def test_two_artifacts_from_same_subject_do_not_satisfy_distinct_quorum():
    rule = replace(_rule(), operation_class="treasury.payment.test-r3-alias", approval_rule_id="TEST:approval:2of2:alias")
    register_approval_rule(rule)
    register_approval_grant(_grant("G-A1", "PERSON-A", "TREASURY_APPROVER", rule.approval_rule_id))
    register_approval_grant(_grant("G-A2", "PERSON-A", "RISK_APPROVER", rule.approval_rule_id))
    with pytest.raises(ValueError, match="distinct"):
        resolve_approval(_req(), operation_class=rule.operation_class, resolved_at=NOW)


def test_correct_cardinality_without_required_role_composition_fails():
    rule = replace(_rule(), operation_class="treasury.payment.test-r3-composition", approval_rule_id="TEST:approval:2of2:composition")
    register_approval_rule(rule)
    register_approval_grant(_grant("G-C1", "PERSON-C1", "TREASURY_APPROVER", rule.approval_rule_id))
    register_approval_grant(_grant("G-C2", "PERSON-C2", "TREASURY_APPROVER", rule.approval_rule_id))
    with pytest.raises(ValueError, match="composition"):
        resolve_approval(_req(), operation_class=rule.operation_class, resolved_at=NOW)


def test_approval_is_bound_to_exact_operation_scope():
    rule = replace(_rule(), operation_class="treasury.payment.test-r3-scope", approval_rule_id="TEST:approval:2of2:scope")
    register_approval_rule(rule)
    register_approval_grant(_grant("G-S1", "PERSON-S1", "TREASURY_APPROVER", rule.approval_rule_id))
    register_approval_grant(_grant("G-S2", "PERSON-S2", "RISK_APPROVER", rule.approval_rule_id))
    ok = resolve_approval(_req(), operation_class=rule.operation_class, resolved_at=NOW)
    assert len(ok.grant_ids) == 2

    changed = _req()
    changed.beneficiary = "OTHER-SUPPLIER"
    with pytest.raises(ValueError, match="quorum"):
        resolve_approval(changed, operation_class=rule.operation_class, resolved_at=NOW)


def test_expired_approval_does_not_survive_without_governing_rule_support():
    rule = replace(_rule(), operation_class="treasury.payment.test-r3-expiry", approval_rule_id="TEST:approval:2of2:expiry")
    register_approval_rule(rule)
    expired = NOW-timedelta(seconds=1)
    register_approval_grant(_grant("G-E1", "PERSON-E1", "TREASURY_APPROVER", rule.approval_rule_id, valid_until=expired))
    register_approval_grant(_grant("G-E2", "PERSON-E2", "RISK_APPROVER", rule.approval_rule_id, valid_until=expired))
    with pytest.raises(ValueError, match="quorum"):
        resolve_approval(_req(), operation_class=rule.operation_class, resolved_at=NOW)
