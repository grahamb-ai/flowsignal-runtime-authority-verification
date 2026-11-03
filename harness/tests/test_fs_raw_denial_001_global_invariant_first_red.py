"""First RED: a synthetic second adapter has no common authority gate.

This is a deliberately incomplete integration, not a defect in FlowSignal's
existing payment executor. No external operation is performed.
"""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace
from app.engines import execution_gateway as gw

def test_same_synthetic_effect_requires_authority_across_both_adapters(monkeypatch):
    at=datetime.now(timezone.utc)
    req=gw.ExecutionAttempt(
        actor_id="actor",principal_id="principal",action="synthetic.release",
        target="synthetic-target",amount=Decimal("1"),currency="GBP",
        source_account="test",beneficiary="test",beneficiary_account_reference="test",
        purpose="test",mandate_id="test",attempted_at=at)
    refused=SimpleNamespace(id="receipt",decision="REFUSE",
        action_binding_hash=gw.action_binding_hash(req),
        authority_state_version=1,valid_until=at+timedelta(minutes=1))
    monkeypatch.setattr(gw,"verify_receipt_hmac",lambda _:True)
    monkeypatch.setattr(gw,"get_authority_state_version",lambda:1)
    witness=[]
    decision=gw.validate_execution(refused,req)
    assert decision.status=="BLOCKED"
    assert witness==[]
    # A separate, intentionally unmediated mock integration route:
    witness.append(("adapter-B",req.target,req.action))
    assert witness==[], (
        "FIRST RED: unmediated synthetic adapter recorded an operation after "
        "the gateway refused it. Global route closure remains unestablished."
    )
