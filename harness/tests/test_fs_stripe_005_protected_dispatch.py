"""FS-STRIPE-005 integration checks: genuine RAI permit and one owner, with a
fake provider to force exact pre-capture races and lost acknowledgements.
No additional Stripe PaymentIntents are created by these tests.
"""
from dataclasses import replace
import pytest
from app.engines.authority_store import advance_authority_state_version,get_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.stripe_protected_dispatch_reference import (
    DispatchRefused,capture_once
)
from experiments.fs_stripe_004 import rai_permit_for_payment, AuthorityOwner

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def owner(tmp_path):
    with AuthorityOwner(tmp_path) as instance:
        yield instance

class StripeSimulator:
    def __init__(self,payment_id,binding,*,error_after_commit=False):
        self.payment_id=payment_id
        self.binding=binding
        self.status="requires_capture"
        self.amount_received=0
        self.calls=0
        self.error_after_commit=error_after_commit
        self.idem_keys=[]
    def retrieve(self,payment_id):
        assert payment_id==self.payment_id
        return dict(id=payment_id,livemode=False,currency="gbp",amount=100,
            capture_method="manual",status=self.status,
            amount_received=self.amount_received,
            metadata={"rai_action_binding_hash":self.binding})
    def capture_with_key(self,payment_id,idem):
        assert payment_id==self.payment_id
        self.calls+=1
        self.idem_keys.append(idem)
        self.status="succeeded"
        self.amount_received=100
        if self.error_after_commit:
            raise ConnectionResetError("simulated lost provider response")

def exercise(owner,*,payment_id="pi_fs_stripe_005_demo",error_after_commit=False):
    permit,grant,req=rai_permit_for_payment(payment_id,return_request=True)
    provider=StripeSimulator(payment_id,permit.action_binding_hash,
                             error_after_commit=error_after_commit)
    return permit,grant,req,provider

def dispatch(owner,permit,grant,req,provider,hook=None):
    return capture_once(payment_id=provider.payment_id,permit=permit,
        grant=grant,bound_request=req,owner_commit=owner.commit,
        owner_version=get_authority_state_version,stripe=provider,
        before_dispatch=hook)

def test_valid_single_owner_capture_is_independently_retrieved(owner):
    permit,grant,req,stripe=exercise(owner)
    result=dispatch(owner,permit,grant,req,stripe)
    assert result.disposition=="PROVIDER_CONFIRMED_FORMED"
    assert result.provider_status=="succeeded" and result.amount_received==100
    assert stripe.calls==1 and owner.count()==1

def test_revocation_after_local_owner_commit_prevents_stripe_dispatch(owner):
    permit,grant,req,stripe=exercise(owner)
    result=dispatch(owner,permit,grant,req,stripe,
                    hook=advance_authority_state_version)
    assert result.disposition=="REFUSED_STALE_AUTHORITY"
    assert stripe.calls==0
    assert owner.count()==1  # Pending local record != external formation.

def test_provider_target_substitution_refused_before_owner_commit(owner):
    permit,grant,req,stripe=exercise(owner)
    stripe.payment_id="pi_fs_stripe_005_substituted"
    with pytest.raises(DispatchRefused,match="PROVIDER_TARGET_NOT_BOUND"):
        dispatch(owner,permit,grant,req,stripe)
    assert stripe.calls==0 and owner.count()==0

def test_action_metadata_substitution_refused(owner):
    permit,grant,req,stripe=exercise(owner)
    stripe.binding="incorrect-action-binding"
    with pytest.raises(DispatchRefused,match="PROVIDER_ACTION_BINDING"):
        dispatch(owner,permit,grant,req,stripe)
    assert stripe.calls==0 and owner.count()==0

def test_lost_capture_acknowledgement_resolved_by_provider_read(owner):
    permit,grant,req,stripe=exercise(owner,error_after_commit=True)
    result=dispatch(owner,permit,grant,req,stripe)
    assert result.disposition=="PROVIDER_CONFIRMED_FORMED"
    assert stripe.calls==1 and stripe.idem_keys[0].startswith("fs-stripe-005-")
    assert owner.count()==1

def test_owner_unreachable_does_not_send_stripe_capture(owner):
    permit,grant,req,stripe=exercise(owner)
    owner.process.terminate()
    owner.process.communicate(timeout=3)
    result=dispatch(owner,permit,grant,req,stripe)
    assert result.disposition=="OWNER_OUTCOME_UNRESOLVED"
    assert stripe.calls==0
