"""FS-STRIPE-005 provider adapter contract tests. No Stripe API calls."""
from app.engines.stripe_protected_capture import execute_capture

HASH="a"*64
PERMIT={"permit":{"signature":"permit-test-1","action_binding_hash":HASH}}
PID="pi_reference_test_001"

class Provider:
    def __init__(self):
        self.status="requires_capture"
        self.calls=0
        self.livemode=False
        self.fail_capture=False
        self.fail_readback=False
        self.amount=100
        self.binding=HASH
    def retrieve(self,payment_id):
        if self.fail_readback:
            raise ConnectionError("readback unavailable")
        return {"id":payment_id,"livemode":self.livemode,
                "amount":self.amount,"currency":"gbp",
                "capture_method":"manual","status":self.status,
                "amount_received":100 if self.status=="succeeded" else 0,
                "metadata":{"rai_action_binding_hash":self.binding}}
    def capture(self,payment_id,signature):
        self.calls+=1
        self.status="succeeded"
        if self.fail_capture:
            raise ConnectionError("acknowledgement lost after provider commit")
        return self.retrieve(payment_id)

class Owner:
    def __init__(self,allowed=True):
        self.allowed=allowed
        self.calls=0
    def commit(self,envelope,hash_value):
        self.calls+=1
        if not self.allowed:
            return 403,{"status":"AUTHORITY_STATE_STALE"}
        return 200,{"status":"WITNESSED_CONSEQUENCE_FORMED"}

def run(provider=None,owner=None,**kwargs):
    p=provider or Provider()
    o=owner or Owner()
    return execute_capture(p,o,payment_id=PID,envelope=PERMIT,
                           action_hash=HASH,**kwargs),p,o

def test_valid_owner_and_provider_confirmed():
    result,p,o=run()
    assert result.status=="CONFIRMED"
    assert p.calls==1 and o.calls==1

def test_revoked_owner_blocks_capture():
    result,p,o=run(owner=Owner(False))
    assert (result.status,result.reason)==("REFUSE","AUTHORITY_OWNER_REFUSED")
    assert p.calls==0

def test_wrong_payment_binding_refused_before_owner_commit():
    p=Provider()
    p.binding="b"*64
    result,p,o=run(provider=p)
    assert result.reason=="PROVIDER_OPERATION_MISMATCH"
    assert p.calls==0 and o.calls==0

def test_live_mode_refused_even_with_valid_reference_permit():
    p=Provider()
    p.livemode=True
    result,p,o=run(provider=p)
    assert result.status=="REFUSE" and p.calls==0

def test_lost_capture_ack_reconciles_provider_success():
    p=Provider()
    p.fail_capture=True
    result,p,o=run(provider=p)
    assert result.status=="CONFIRMED" and p.calls==1

def test_readback_unavailable_is_unresolved_not_failed():
    class LateReadFailure(Provider):
        def __init__(self):
            super().__init__()
            self.reads=0
        def retrieve(self,payment_id):
            self.reads+=1
            if self.reads>1:
                raise ConnectionError("provider readback lost")
            return super().retrieve(payment_id)
    result,p,o=run(provider=LateReadFailure())
    assert result.status=="UNRESOLVED" and p.calls==1

def test_invalid_permit_does_not_reach_provider():
    p,o=Provider(),Owner()
    result=execute_capture(p,o,payment_id=PID,envelope={"permit":{}},action_hash=HASH)
    assert result.status=="REFUSE"
    assert p.calls==0 and o.calls==0

def test_revocation_after_owner_commit_is_still_open():
    p,o=Provider(),Owner()
    revoked={"value":False}
    def revoke_between_operations():
        revoked["value"]=True
    result,p,o=run(provider=p,owner=o,before_provider_dispatch=revoke_between_operations)
    assert revoked["value"]
    assert result.status=="CONFIRMED" and p.calls==1
    # Characterization of remaining distributed check/commit gap, NOT a
    # successful immediate-revocation safety property.
