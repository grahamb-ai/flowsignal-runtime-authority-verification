"""Reference candidate: both mock adapters share the actual gateway."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace
import base64
import pytest
from app.engines import execution_gateway as gw
from app.engines.synthetic_guarded_adapters import GuardedAdapterPair

@pytest.fixture
def case(monkeypatch):
    at=datetime.now(timezone.utc)
    req=gw.ExecutionAttempt(
        actor_id="agent",principal_id="principal",action="synthetic.release",
        target="synthetic-invoice",amount=Decimal("1"),currency="GBP",
        source_account="test",beneficiary="test",beneficiary_account_reference="test",
        purpose="test",mandate_id="test",attempted_at=at)
    receipt=SimpleNamespace(
        id="receipt",decision="REFUSE",action_binding_hash=gw.action_binding_hash(req),
        authority_state_version=3,valid_until=at+timedelta(minutes=2),
        authority_snapshot_id="snap",authority_subject_principal_id="principal",
        authority_subject_mandate_id="test",authority_epoch_id="epoch",
        authority_fence_scope_key="fence",authority_fence=1,
        authoritative_source_id="source",source_competence_root_id="root",
        authority_semantics_version="v1",authority_semantics_definition_id="def",
        authority_semantics_source_id="source")
    state={"version":3,"receipt_valid":True}
    monkeypatch.setattr(gw,"verify_receipt_hmac",lambda _:state["receipt_valid"])
    monkeypatch.setattr(gw,"get_authority_state_version",lambda:state["version"])
    monkeypatch.setattr(gw,"issue_execution_permit",lambda **_:object())
    return req,receipt,state,GuardedAdapterPair()

def encoded(action):
    return base64.b64encode(action.encode()).decode()

def test_both_adapters_refuse_and_outcome_remains_absent(case):
    req,receipt,_,pair=case
    a=pair.invoke("A",req,receipt)
    b=pair.invoke("B",req,receipt,encoded(req.action))
    assert (a.status,b.status)==("BLOCKED","BLOCKED")
    assert pair.count(req.target,req.action)==0

def test_repeated_attempts_remain_refused(case):
    req,receipt,_,pair=case
    for _ in range(3):
        assert not pair.invoke("B",req,receipt,encoded(req.action)).formed
    assert pair.count(req.target,req.action)==0

def test_incorrect_presentation_is_not_accepted(case):
    req,receipt,_,pair=case
    verdict=pair.invoke("B",req,receipt,encoded("synthetic.other"))
    assert verdict.reason=="PRESENTATION_ACTION_MISMATCH"
    assert pair.count(req.target,req.action)==0

def test_malformed_presentation_fails_closed(case):
    req,receipt,_,pair=case
    assert pair.invoke("B",req,receipt,"%%%").reason=="INVALID_PRESENTATION"
    assert pair.count(req.target,req.action)==0

def test_previous_receipt_rejected_after_state_version_changes(case):
    req,receipt,state,pair=case
    state["version"]=4
    assert not pair.invoke("B",req,receipt,encoded(req.action)).formed
    assert pair.count(req.target,req.action)==0

def test_invalid_receipt_integrity_is_refused(case):
    req,receipt,state,pair=case
    state["receipt_valid"]=False
    assert not pair.invoke("A",req,receipt).formed
    assert not pair.invoke("B",req,receipt,encoded(req.action)).formed
    assert pair.count(req.target,req.action)==0

def test_new_allow_can_record_synthetic_outcome(case):
    req,receipt,state,pair=case
    state["version"]=4
    new=SimpleNamespace(**{**vars(receipt),"id":"fresh","decision":"ALLOW",
                           "authority_state_version":4})
    assert pair.invoke("B",req,new,encoded(req.action)).formed
    assert pair.count(req.target,req.action)==1

def test_unknown_adapter_rejected(case):
    req,receipt,_,pair=case
    assert not pair.invoke("C",req,receipt).formed
    assert pair.count(req.target,req.action)==0
