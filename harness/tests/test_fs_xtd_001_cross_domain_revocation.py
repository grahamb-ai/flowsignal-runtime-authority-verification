"""FS-XTD-001 frozen failure-first cross-domain revocation challenge.

This test intentionally stays outside the current reference implementation's
declared local authority-state boundary.  It asks whether Domain D can consume
an independently authentic, fresh revocation from Domain A before consequence
formation.  A RED result demonstrates a missing cross-domain trust/revocation
seam; it does not prove that the existing local-boundary controls are broken.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.runtime_authority_payment import (
    mint_rai_bound_execution_permit,
    prepare_payment_execution,
)
from app.engines.cross_domain_authority import (
    CrossDomainAuthorityObservation,
    _TRUST_ADMIN_CAPABILITY,
    enroll_external_authority_for_test,
    ingest_authority_observation,
    register_trust_anchor_for_test,
    reset_cross_domain_authority_for_test,
    sign_observation_for_test,
)
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"
DOMAIN_A_REFERENCE_KEY = b"FS-XTD-001-DOMAIN-A-REFERENCE-KEY"


def _attempt(req, *, attempted_at: datetime) -> ExecutionAttempt:
    return ExecutionAttempt(
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
        attempted_at=attempted_at,
    )


@pytest.fixture(autouse=True)
def _isolate_reference_state(monkeypatch, tmp_path):
    reset_authority_usage_reference_state_for_test()
    reset_cross_domain_authority_for_test()
    monkeypatch.setenv(
        "FLOWSIGNAL_PERMIT_CONSUMPTION_STORE", str(tmp_path / "permit.sqlite3")
    )
    monkeypatch.setenv(
        "FLOWSIGNAL_CONSEQUENCE_OUTCOME_STORE", str(tmp_path / "outcome.sqlite3")
    )
    monkeypatch.setenv(
        "FLOWSIGNAL_ROLLBACK_ANCHOR_STORE", str(tmp_path / "anchor.sqlite3")
    )
    yield
    reset_authority_usage_reference_state_for_test()
    reset_cross_domain_authority_for_test()


def _observation(*, req, status: str, epoch: int, at: datetime):
    return sign_observation_for_test(
        CrossDomainAuthorityObservation(
            issuer_domain="DOMAIN-A-AUTHORITY-ISSUER",
            authority_id=req.mandate_id,
            authority_subject=req.principal_id,
            status=status,
            authority_epoch=epoch,
            effective_at=at.isoformat(),
            observed_at=at.isoformat(),
            valid_until=(at + timedelta(minutes=5)).isoformat(),
            permitted_actions=(req.action,),
            permitted_resources=(req.target,),
            parent_permitted_actions=(req.action,),
            parent_permitted_resources=(req.target,),
            root_authority_id="DOMAIN-A:ROOT:001",
            parent_authority_id="DOMAIN-A:PARENT:001",
            policy_id="DOMAIN-B:POLICY:001",
            evidence_digest="DOMAIN-C:EVIDENCE:SHA256:001",
        ),
        reference_key=DOMAIN_A_REFERENCE_KEY,
    )


def _request(*, operation_suffix: str):
    now = datetime.now(timezone.utc)
    req = load_scenario(SCENARIO, rebase_to_now=False)
    return now, replace(
        req,
        amount=Decimal("100000.00"),
        requested_execution_time=now,
        screening_captured_at=now,
        mandate_valid_until=now + timedelta(hours=1),
        institutional_operation_id=f"FS-XTD-001:RESOURCE:{operation_suffix}",
    )


def _enroll(req):
    register_trust_anchor_for_test(
        issuer_domain="DOMAIN-A-AUTHORITY-ISSUER",
        reference_key=DOMAIN_A_REFERENCE_KEY,
        capability=_TRUST_ADMIN_CAPABILITY,
    )
    enroll_external_authority_for_test(
        authority_id=req.mandate_id,
        authority_subject=req.principal_id,
        issuer_domain="DOMAIN-A-AUTHORITY-ISSUER",
        capability=_TRUST_ADMIN_CAPABILITY,
    )


def test_confirmed_fresh_cross_domain_revocation_must_prevent_consequence():
    """Confirmed revocation is REFUSE, never an inherited historic ALLOW.

    Domains are deliberately separated:
      A issues/revokes authority; B supplies policy; C witnesses evidence;
      D is the represented FlowSignal execution boundary.

    The original permit binds the exact actor, action, resource, policy/evidence
    resolution and then-current local authority state.  Domain A subsequently
    emits an independently verifiable, current revocation for that authority.
    Domain D must consume that fact before executing the old permit.
    """
    now, req = _request(operation_suffix="INV-78431")
    _enroll(req)
    active_at = now - timedelta(seconds=5)
    ingest_authority_observation(
        _observation(req=req, status="ACTIVE", epoch=1, at=active_at),
        verified_at=now,
    )

    prepared = prepare_payment_execution(
        req,
        route_id="DOMAIN-D-ROUTE-1",
        executor_id="DOMAIN-D-EXECUTOR-1",
        resolved_at=now,
    )
    permit = mint_rai_bound_execution_permit(req, prepared, bind_at=now)
    assert permit is not None, "SETUP FAILURE: baseline authority did not mint a permit"

    revocation_at = now - timedelta(seconds=1)
    execution_time = now
    ingest_authority_observation(
        _observation(
            req=req,
            status="REVOKED",
            epoch=2,
            at=revocation_at,
        ),
        verified_at=execution_time,
    )

    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=action_binding_hash(
            _attempt(req, attempted_at=execution_time)
        ),
    )

    assert outcome == "DENIED_CROSS_DOMAIN_AUTHORITY_REVOKED"


def test_forged_revocation_is_not_accepted_as_authoritative_state():
    now, req = _request(operation_suffix="FORGED")
    _enroll(req)
    forged = replace(
        _observation(req=req, status="REVOKED", epoch=2, at=now),
        signature="attacker-forged-signature",
    )
    with pytest.raises(ValueError, match="authenticity invalid"):
        ingest_authority_observation(forged, verified_at=now)


def test_enrolled_but_unresolved_external_authority_never_mints_execution_permit():
    now, req = _request(operation_suffix="UNRESOLVED")
    _enroll(req)
    prepared = prepare_payment_execution(
        req,
        route_id="DOMAIN-D-ROUTE-1",
        executor_id="DOMAIN-D-EXECUTOR-1",
        resolved_at=now,
    )
    assert mint_rai_bound_execution_permit(req, prepared, bind_at=now) is None


def test_downstream_delegation_cannot_expand_parent_scope():
    now, req = _request(operation_suffix="EXPANSION")
    _enroll(req)
    expanded = replace(
        _observation(req=req, status="ACTIVE", epoch=1, at=now),
        permitted_actions=(req.action, "payment.redirect"),
    )
    expanded = sign_observation_for_test(expanded, reference_key=DOMAIN_A_REFERENCE_KEY)
    with pytest.raises(ValueError, match="expands parent action authority"):
        ingest_authority_observation(expanded, verified_at=now)


def test_unenrolled_domain_cannot_transfer_authority_implicitly():
    now, req = _request(operation_suffix="DOMAIN-TRANSFER")
    _enroll(req)
    other_key = b"FS-XTD-001-DOMAIN-X-REFERENCE-KEY"
    register_trust_anchor_for_test(
        issuer_domain="DOMAIN-X-UNRELATED",
        reference_key=other_key,
        capability=_TRUST_ADMIN_CAPABILITY,
    )
    transferred = replace(
        _observation(req=req, status="ACTIVE", epoch=1, at=now),
        issuer_domain="DOMAIN-X-UNRELATED",
    )
    transferred = sign_observation_for_test(transferred, reference_key=other_key)
    with pytest.raises(ValueError, match="implicit cross-domain authority transfer"):
        ingest_authority_observation(transferred, verified_at=now)


def test_superseded_external_authority_cannot_resurrect_old_permit():
    now, req = _request(operation_suffix="SUPERSEDED")
    _enroll(req)
    ingest_authority_observation(
        _observation(
            req=req,
            status="ACTIVE",
            epoch=1,
            at=now - timedelta(seconds=5),
        ),
        verified_at=now,
    )
    prepared = prepare_payment_execution(
        req,
        route_id="DOMAIN-D-ROUTE-1",
        executor_id="DOMAIN-D-EXECUTOR-1",
        resolved_at=now,
    )
    permit = mint_rai_bound_execution_permit(req, prepared, bind_at=now)
    assert permit is not None

    ingest_authority_observation(
        _observation(
            req=req,
            status="ACTIVE",
            epoch=2,
            at=now - timedelta(seconds=1),
        ),
        verified_at=now,
    )
    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=action_binding_hash(
            _attempt(req, attempted_at=now)
        ),
    )
    assert outcome == "DENIED_CROSS_DOMAIN_AUTHORITY_STATE_CHANGED"


def test_cross_domain_authority_epoch_cannot_move_backwards_or_replay():
    now, req = _request(operation_suffix="ROLLBACK")
    _enroll(req)
    ingest_authority_observation(
        _observation(req=req, status="ACTIVE", epoch=2, at=now),
        verified_at=now,
    )
    replay = _observation(req=req, status="ACTIVE", epoch=1, at=now)
    with pytest.raises(ValueError, match="rollback or replay"):
        ingest_authority_observation(replay, verified_at=now)

