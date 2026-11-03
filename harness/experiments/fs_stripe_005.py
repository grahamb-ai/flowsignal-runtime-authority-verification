"""FS-STRIPE-005 bounded Stripe TEST provider qualification.

Two £1 manual-capture test authorisations. The revoked case injects a direct
source-owner revocation AFTER local admission and BEFORE Stripe dispatch;
the allowed case captures and retrieves Stripe's final PaymentIntent status.

No live funds. The final owner read and provider capture are NOT atomic.
"""
import json,os,sys,tempfile,uuid
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.engines.authority_store import advance_authority_state_version,get_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.stripe_protected_dispatch_reference import capture_once
from experiments.fs_stripe_004 import (
    StripeTestClient,AuthorityOwner,rai_permit_for_payment,SandboxError,AMOUNT_MINOR,
)

class CaptureProvider:
    def __init__(self,stripe):
        self.stripe=stripe
    def retrieve(self,payment_id):
        return self.stripe.retrieve(payment_id)
    def capture_with_key(self,payment_id,key):
        return self.stripe.call(f"/payment_intents/{payment_id}/capture",{},
                                idempotency=key)

def execute(stripe,case,*,revoke_at_dispatch):
    reset_authority_usage_reference_state_for_test()
    with tempfile.TemporaryDirectory(prefix="fs-stripe-005-") as directory:
        with AuthorityOwner(directory) as owner:
            authorisation=stripe.authorize(case,experiment="FS-STRIPE-005")
            payment_id=authorisation["id"]
            if (authorisation.get("livemode") is not False
                or authorisation.get("status")!="requires_capture"
                or authorisation.get("amount")!=AMOUNT_MINOR
                or authorisation.get("currency")!="gbp"):
                raise SandboxError("Unexpected Stripe test authorisation")
            try:
                permit,grant,req=rai_permit_for_payment(payment_id,return_request=True,experiment="FS-STRIPE-005")
                stripe.bind(payment_id,permit.action_binding_hash)
                provider=CaptureProvider(stripe)
                result=capture_once(
                    payment_id=payment_id,permit=permit,grant=grant,
                    bound_request=req,owner_commit=owner.commit,
                    owner_version=get_authority_state_version,stripe=provider,
                    before_dispatch=advance_authority_state_version if revoke_at_dispatch else None,
                    expected_experiment="FS-STRIPE-005",
                )
                if revoke_at_dispatch:
                    if result.disposition!="REFUSED_STALE_AUTHORITY":
                        raise SandboxError("Expected pre-capture revocation refusal")
                    observed=stripe.retrieve(payment_id)
                    if observed["status"]!="requires_capture":
                        raise SandboxError("Provider status unexpected after refused dispatch")
                    stripe.cancel(payment_id)
                    observed=stripe.retrieve(payment_id)
                    if observed["status"]!="canceled" or observed["amount_received"]!=0:
                        raise SandboxError("Refused test authorisation not cancelled")
                else:
                    if result.disposition!="PROVIDER_CONFIRMED_FORMED":
                        raise SandboxError("Provider result not confirmed; do not retry blindly")
                    observed=stripe.retrieve(payment_id)
                    if observed["status"]!="succeeded" or observed["amount_received"]!=100:
                        raise SandboxError("Stripe provider readback is inconsistent")
                return dict(
                    case=case,
                    payment_intent_id=payment_id,
                    stripe_status=observed["status"],
                    stripe_amount_received=observed["amount_received"],
                    currency=observed["currency"],
                    livemode=observed["livemode"],
                    authority_version_at_issuance=permit.authority_state_version,
                    owner_effect_count=owner.count(),
                    rai_action_binding_hash=permit.action_binding_hash,
                    dispatch_disposition=result.disposition,
                )
            except Exception:
                try:
                    observed=stripe.retrieve(payment_id)
                    if observed["status"]=="requires_capture":
                        stripe.cancel(payment_id)
                except Exception:
                    pass
                raise

def main():
    stripe=StripeTestClient()
    tag=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8]
    results=[]
    for label,revoke in (("revoke-during-dispatch",True),("allow",False)):
        outcome=execute(stripe,"fs-stripe-005-"+label+"-"+tag,revoke_at_dispatch=revoke)
        print(json.dumps(outcome,sort_keys=True),flush=True)
        results.append(outcome)
    assert [r["stripe_status"] for r in results]==["canceled","succeeded"]
    assert [r["stripe_amount_received"] for r in results]==[0,100]
    path=Path(os.environ.get("FS_STRIPE_005_EVIDENCE_FILE","fs-stripe-005-evidence.json"))
    path.write_text(json.dumps({
        "experiment":"FS-STRIPE-005",
        "production_prevention":"NOT ESTABLISHED",
        "limits":"Owner check and Stripe capture remain separate operations",
        "results":results,
    },indent=2))

if __name__=="__main__":
    main()
