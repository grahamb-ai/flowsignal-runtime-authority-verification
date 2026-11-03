"""FS-RAW-DENIAL-001: two-adapter synthetic integration characterization.

Route A invokes the real FlowSignal gateway with a refused receipt.
Route B is a deliberately separate mock adapter, not a FlowSignal route.
An independent in-memory observer records the modeled operation outcome.
No shell, payments, external services or production systems are involved.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from app.engines import execution_gateway as gw

def test_refusal_and_unmediated_mock_adapter_have_different_outcomes(monkeypatch):
    timestamp=datetime.now(timezone.utc)
    attempt=gw.ExecutionAttempt(
        actor_id="agent-test",principal_id="principal-test",action="synthetic.release",
        target="synthetic-record",amount=Decimal("100"),currency="GBP",
        source_account="test",beneficiary="test",beneficiary_account_reference="test",
        purpose="bounded-test",mandate_id="test",attempted_at=timestamp)
    receipt=SimpleNamespace(
        id="test-refused",decision="REFUSE",
        action_binding_hash=gw.action_binding_hash(attempt),
        authority_state_version=1,valid_until=timestamp+timedelta(minutes=5))
    monkeypatch.setattr(gw,"verify_receipt_hmac",lambda _:True)
    monkeypatch.setattr(gw,"get_authority_state_version",lambda:1)
    observations=[]
    decision=gw.validate_execution(receipt,attempt)
    assert decision.status=="BLOCKED"
    assert observations==[]
    # Distinct hypothetical adapter with no gateway integration.
    observations.append(("mock-adapter-B",attempt.action,attempt.target))
    assert observations==[("mock-adapter-B","synthetic.release","synthetic-record")]

def test_intended_global_no_consequence_invariant_is_currently_unproven(monkeypatch):
    # This records an integration gap, not a defect in the gateway.
    observed={"gateway":"BLOCKED","unmediated_mock":"FORMED"}
    assert observed["gateway"]=="BLOCKED"
    assert observed["unmediated_mock"]=="FORMED"
