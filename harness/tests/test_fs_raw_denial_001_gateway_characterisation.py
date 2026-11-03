"""FS-RAW-DENIAL-001: bounded failure-first characterization of the EXISTING
FlowSignal execution gateway, pinned to the main baseline at creation.

These tests DO NOT execute shell commands, alternate tools, agent memory, or a
production consequence. Receipt verification/state access/permit issuance are
test doubles to isolate gateway behaviour. Route closure is NOT ESTABLISHED.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.engines import execution_gateway as gw

@pytest.fixture
def setup(monkeypatch):
    now=datetime.now(timezone.utc)
    attempt=gw.ExecutionAttempt(
        actor_id="agent-01", principal_id="principal-01",
        action="payment.release", target="payment:one",
        amount=Decimal("100.00"), currency="GBP",
        source_account="SOURCE", beneficiary="PAYEE",
        beneficiary_account_reference="ACCT-001",
        purpose="supplier-invoice", mandate_id="mandate-01",
        attempted_at=now)
    receipt=SimpleNamespace(
        id="receipt-001", decision="ALLOW",
        action_binding_hash=gw.action_binding_hash(attempt),
        valid_until=now+timedelta(minutes=5),authority_state_version=7,
        authority_snapshot_id="snap-01",authority_subject_principal_id="principal-01",
        authority_subject_mandate_id="mandate-01",authority_epoch_id="epoch-01",
        authority_fence_scope_key="scope-01",authority_fence=1,
        authoritative_source_id="authority-source",
        source_competence_root_id="root-01",authority_semantics_version="v1",
        authority_semantics_definition_id="def-01",
        authority_semantics_source_id="authority-source")
    controls={"signature_valid":True,"version":7}
    monkeypatch.setattr(gw,"verify_receipt_hmac",
                        lambda _: controls["signature_valid"])
    monkeypatch.setattr(gw,"get_authority_state_version",
                        lambda: controls["version"])
    monkeypatch.setattr(gw,"issue_execution_permit",
                        lambda **_: object())
    return attempt,receipt,controls

def test_D01_changed_operation_representation_not_authorised_by_old_receipt(setup):
    original,receipt,_=setup
    # Encoding/shell execution itself is NOT tested; this is an exact-binding
    # proxy using a different action representation.
    changed=replace(original,action="encoded:payment.release")
    r=gw.validate_execution(receipt,changed)
    assert (r.status,r.reason_code)==("BLOCKED","ACTION_BINDING_MISMATCH")
    assert r.execution_permit is None

def test_D02_changed_target_tool_route_proxy_not_authorised(setup):
    original,receipt,_=setup
    # The gateway binds target, not all possible external tool routes.
    changed=replace(original,target="tool-b:payment:one")
    r=gw.validate_execution(receipt,changed)
    assert r.reason_code=="ACTION_BINDING_MISMATCH"
    assert r.execution_permit is None

def test_D03_agent_written_instruction_cannot_override_invalid_receipt(setup):
    original,receipt,controls=setup
    controls["signature_valid"]=False
    # Agent-writable instructions are not an input to validate_execution.
    r=gw.validate_execution(receipt,original)
    assert (r.status,r.reason_code)==("BLOCKED","AUTHORITY_RECEIPT_INTEGRITY_INVALID")
    assert r.execution_permit is None

def test_D04_later_session_stale_authority_version_blocks(setup):
    original,receipt,controls=setup
    controls["version"]=8  # An independently supplied version change.
    r=gw.validate_execution(receipt,original)
    assert (r.status,r.reason_code)==("BLOCKED","AUTHORITY_STATE_STALE_REEVALUATION_REQUIRED")
    assert r.execution_permit is None

def test_D05_fresh_matching_allow_is_permitted_to_mint_reference_permit(setup):
    original,receipt,controls=setup
    controls["version"]=8
    new=SimpleNamespace(**{**vars(receipt),"id":"receipt-002","authority_state_version":8})
    r=gw.validate_execution(new,original)
    assert r.status=="PERMITTED" and r.execution_permit is not None
    # PERMITTED != CONSEQUENCE_FORMED; mint is a test double.

def test_refusal_persists_for_repeated_matching_requests(setup):
    original,receipt,_=setup
    denied=SimpleNamespace(**{**vars(receipt),"decision":"REFUSE"})
    for _ in range(3):
        r=gw.validate_execution(denied,original)
        assert (r.status,r.reason_code)==("BLOCKED","NO_APPLICABLE_ALLOW")
        assert r.execution_permit is None
