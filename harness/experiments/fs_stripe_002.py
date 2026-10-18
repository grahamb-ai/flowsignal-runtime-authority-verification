"""FS-STRIPE-002: bounded provider sandbox revocation/capture ordering.

This experiment does NOT establish atomicity across Stripe and an independent
authority store. It measures gateway decisions and actual Stripe provider state.
No live payments. Requires restricted rk_test_ key with PaymentIntents write.
"""
import json
import os
import urllib.parse
import urllib.request
import urllib.error
import uuid

KEY = os.getenv("STRIPE_TEST_SECRET_KEY", "")
API = "https://api.stripe.com/v1"

def request(method, path, fields=None, idempotency=None):
    data = urllib.parse.urlencode(fields).encode() if fields is not None else None
    headers = {"Authorization": "Bearer " + KEY}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def emit(**kwargs):
    print(json.dumps(kwargs, sort_keys=True), flush=True)

def create(case):
    token = uuid.uuid4().hex
    fields = {
        "amount": "100", "currency": "gbp", "payment_method": "pm_card_visa",
        "capture_method": "manual", "confirm": "true",
        "automatic_payment_methods[enabled]": "true",
        "automatic_payment_methods[allow_redirects]": "never",
        "description": "FS-STRIPE-002 test only",
        "metadata[experiment]": "FS-STRIPE-002",
        "metadata[case]": case,
    }
    code, obj = request("POST", "/payment_intents", fields, "fs-stripe-002-create-" + token)
    if code != 200 or obj.get("status") != "requires_capture" or obj.get("livemode") is not False:
        emit(case=case, stage="create_failed", http=code, error=obj.get("error"))
        raise AssertionError("Sandbox authorisation failed")
    emit(case=case, stage="authorised", id=obj["id"], status=obj["status"], livemode=False)
    return obj["id"], token

def status(pid):
    code, obj = request("GET", "/payment_intents/" + pid)
    assert code == 200
    return obj["status"]

def main():
    if not KEY.startswith(("rk_test_", "sk_test_")):
        raise RuntimeError("Restricted or standard TEST key required")

    # Case A: revocation occurs before gateway final check. No capture API
    # request may be sent; cancel the outstanding Stripe authorisation.
    pid, token = create("revoked_before_gateway")
    authority_version = 1
    authority_version = 2  # simulated authoritative revocation
    checked_version = 1
    dispatched = False
    if checked_version == authority_version:
        raise AssertionError("Invalid fixture: revocation not exercised")
    emit(case="revoked_before_gateway", stage="gateway_refused",
         authority_version=authority_version, dispatch_sent=dispatched)
    code, cancelled = request("POST", "/payment_intents/" + pid + "/cancel",
                              {"cancellation_reason": "requested_by_customer"},
                              "fs-stripe-002-cancel-" + token)
    assert code == 200 and cancelled.get("status") == "canceled"
    assert status(pid) == "canceled"
    emit(case="revoked_before_gateway", stage="provider_final", status="canceled")

    # Case B: gateway checks valid authority and Stripe accepts capture.
    # Revocation *after* Stripe capture does not undo a formed consequence.
    pid, token = create("capture_before_revocation")
    authority_version = 1
    checked_version = 1
    assert authority_version == checked_version
    code, captured = request("POST", "/payment_intents/" + pid + "/capture", {},
                             "fs-stripe-002-capture-" + token)
    emit(case="capture_before_revocation", stage="capture_result",
         http=code, status=captured.get("status"), error_code=captured.get("error", {}).get("code"))
    assert code == 200 and captured.get("status") == "succeeded"
    authority_version = 2
    final = status(pid)
    assert final == "succeeded"
    emit(case="capture_before_revocation", stage="revoked_after_capture",
         authority_version=authority_version, provider_status=final,
         consequence_already_formed=True)
    emit(stage="qualification", result="PASS_BOUNDED_ORDERINGS",
         limitation="No independent authority service; no concurrent in-flight provider race; no atomic external commitment proof")

if __name__ == "__main__":
    main()
