"""FS-XTD-001 frozen failure-first cross-domain revocation challenge.

This test intentionally stays outside the current reference implementation's
declared local authority-state boundary.  It asks whether Domain D can consume
an independently authentic, fresh revocation from Domain A before consequence
formation.  A RED result demonstrates a missing cross-domain trust/revocation
seam; it does not prove that the existing local-boundary controls are broken.
"""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash
from app.engines.protected_consequence import execute_protected_consequence
from app.engines.runtime_authority_payment import (
    mint_rai_bound_execution_permit,
    prepare_payment_execution,
)
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"
DOMAIN_A_REFERENCE_KEY = b"FS-XTD-001-DOMAIN-A-REFERENCE-KEY"


@dataclass(frozen=True)
class CrossDomainRevocation:
    issuer_domain: str
    authority_id: str
    authority_subject: str
    status: str
    authority_epoch: int
    effective_at: str
    observed_at: str
    valid_until: str
    signature: str = ""


def _canonical_unsigned(revocation: CrossDomainRevocation) -> bytes:
    payload = asdict(revocation)
    payload.pop("signature")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sign(revocation: CrossDomainRevocation) -> CrossDomainRevocation:
    signature = hmac.new(
        DOMAIN_A_REFERENCE_KEY,
        _canonical_unsigned(revocation),
        hashlib.sha256,
    ).hexdigest()
    return replace(revocation, signature=signature)


def _verify_authentic_and_fresh(
    revocation: CrossDomainRevocation, *, now: datetime
) -> bool:
    expected = hmac.new(
        DOMAIN_A_REFERENCE_KEY,
        _canonical_unsigned(revocation),
        hashlib.sha256,
    ).hexdigest()
    return (
        hmac.compare_digest(expected, revocation.signature)
        and revocation.issuer_domain == "DOMAIN-A-AUTHORITY-ISSUER"
        and revocation.status == "REVOKED"
        and datetime.fromisoformat(revocation.effective_at) <= now
        and datetime.fromisoformat(revocation.observed_at) <= now
        and now <= datetime.fromisoformat(revocation.valid_until)
    )


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
    now = datetime.now(timezone.utc)
    req = load_scenario(SCENARIO, rebase_to_now=False)
    req = replace(
        req,
        amount=Decimal("100000.00"),
        requested_execution_time=now,
        screening_captured_at=now,
        mandate_valid_until=now + timedelta(hours=1),
        institutional_operation_id="FS-XTD-001:RESOURCE:INV-78431",
    )

    prepared = prepare_payment_execution(
        req,
        route_id="DOMAIN-D-ROUTE-1",
        executor_id="DOMAIN-D-EXECUTOR-1",
        resolved_at=now,
    )
    permit = mint_rai_bound_execution_permit(req, prepared, bind_at=now)
    assert permit is not None, "SETUP FAILURE: baseline authority did not mint a permit"

    revocation = _sign(
        CrossDomainRevocation(
            issuer_domain="DOMAIN-A-AUTHORITY-ISSUER",
            authority_id=req.mandate_id,
            authority_subject=req.principal_id,
            status="REVOKED",
            authority_epoch=2,
            effective_at=(now + timedelta(seconds=1)).isoformat(),
            observed_at=(now + timedelta(seconds=2)).isoformat(),
            valid_until=(now + timedelta(minutes=5)).isoformat(),
        )
    )
    execution_time = now + timedelta(seconds=3)
    assert _verify_authentic_and_fresh(revocation, now=execution_time), (
        "SETUP FAILURE: Domain D could not independently establish an authentic, "
        "fresh revocation fixture"
    )

    outcome = execute_protected_consequence(
        permit=permit,
        attempted_action_binding_hash=action_binding_hash(
            _attempt(req, attempted_at=execution_time)
        ),
    )

    assert outcome != "CONSEQUENCE_FORMED", (
        "FS-XTD-001 RED: Domain D formed the consequence after an independently "
        "authentic and fresh Domain A revocation because the execution boundary "
        "has no cross-domain revocation-consumption seam"
    )

