"""FS-STRIPE-003 first-RED: revocation after check, before Stripe capture.

Deliberately vulnerable reference dispatcher; records actual Stripe test-mode
consequence. Failure is expected if capture succeeds after injected revocation.
No claim of production enforcement or atomic provider-side revocation.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
import uuid

KEY=os.getenv("STRIPE_TEST_SECRET_KEY","")
BASE="https://api.stripe.com/v1"

def api(method,path,fields=None,idem=None):
    data=urllib.parse.urlencode(fields).encode() if fields is not None else None
    headers={"Authorization":"Bearer "+KEY}
    if data is not None: headers["Content-Type"]="application/x-www-form-urlencoded"
    if idem: headers["Idempotency-Key"]=idem
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as r: return r.status,json.load(r)
    except urllib.error.HTTPError as e: return e.code,json.loads(e.read())

def record(**values):
    print(json.dumps(values,sort_keys=True),flush=True)

def main():
    if not KEY.startswith(("rk_test_","sk_test_")): raise RuntimeError("Test-only Stripe key required")
    token=uuid.uuid4().hex
    fields={"amount":"100","currency":"gbp","payment_method":"pm_card_visa",
        "capture_method":"manual","confirm":"true",
        "automatic_payment_methods[enabled]":"true",
        "automatic_payment_methods[allow_redirects]":"never",
        "description":"FS-STRIPE-003 hostile reference challenge",
        "metadata[experiment]":"FS-STRIPE-003"}
    code,pi=api("POST","/payment_intents",fields,"fs-stripe-003-create-"+token)
    if code!=200 or pi.get("status")!="requires_capture" or pi.get("livemode") is not False:
        record(stage="setup_failed",http=code,error=pi.get("error"))
        raise AssertionError("Sandbox setup failed")
    pid=pi["id"]
    record(stage="authorised",payment_intent_id=pid,provider_status=pi["status"],livemode=False)
    # Vulnerable check-then-dispatch: initial version checked once.
    authority_version=1
    checked_version=authority_version
    assert checked_version==1
    record(stage="gateway_check",checked_version=checked_version,decision="ALLOW")
    # Deterministic injection after the check but before the HTTP request.
    authority_version=2
    record(stage="injected_revocation",current_version=authority_version,previous_version=checked_version)
    # Remediation: check current authority again immediately before dispatch.
    # This closes the injected *pre-dispatch* gap in the bounded dispatcher.
    # It does not make Stripe capture atomic with a remote revocation.
    dispatch_sent = False
    if checked_version != authority_version:
        record(stage="dispatch_refused", checked_version=checked_version,
               current_version=authority_version, dispatch_sent=False)
        code, cancelled = api("POST", f"/payment_intents/{pid}/cancel",
                              {"cancellation_reason": "requested_by_customer"},
                              "fs-stripe-003-cancel-" + token)
        assert code == 200 and cancelled.get("status") == "canceled"
    else:
        dispatch_sent = True
        code, captured = api("POST", f"/payment_intents/{pid}/capture", {},
                             "fs-stripe-003-capture-" + token)
        record(stage="capture_response", http=code, status=captured.get("status"))
    code, final = api("GET", f"/payment_intents/{pid}")
    assert code == 200
    record(stage="provider_final", status=final.get("status"),
           livemode=final.get("livemode"), payment_intent_id=pid)
    assert not dispatch_sent
    assert final.get("status") == "canceled"
    record(stage="qualification", result="PASS_BOUNDED_PRE_DISPATCH_REVALIDATION",
           limitation="Simulated authority version; no independent authority service or atomic external capture enforcement")

if __name__=="__main__":
    main()
