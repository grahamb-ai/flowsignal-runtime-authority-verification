"""FS-STRIPE-001 — real Stripe sandbox manual-capture lifecycle.

Run only with a restricted Stripe TEST secret key. No production key, no
customer data, no live payment. This is provider behaviour testing, NOT
FlowSignal production integration or proof of atomic revocation/capture.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

KEY = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
BASE = "https://api.stripe.com/v1"


def call(method, path, data=None, idempotency=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    headers = {"Authorization": f"Bearer {KEY}"}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read())
        return exc.code, payload


def ensure_status(obj, expected, stage):
    actual = obj.get("status")
    if actual != expected:
        raise AssertionError(f"{stage}: expected {expected}, got {actual}; id={obj.get('id')}")


def run():
    if not KEY.startswith(("sk_test_", "rk_test_")):
        raise RuntimeError("STRIPE_TEST_SECRET_KEY must be a test secret (sk_test_ or rk_test_)")
    case_id = uuid.uuid4().hex
    # Card test PaymentMethod is a Stripe fixture, not real card data.
    fields = {
        "amount": "100",
        "currency": "gbp",
        "payment_method": "pm_card_visa",
        "automatic_payment_methods[enabled]": "true",
        "automatic_payment_methods[allow_redirects]": "never",
        "capture_method": "manual",
        "confirm": "true",
        "description": "FS-STRIPE-001 isolated test",
        "metadata[case_id]": case_id,
        "metadata[experiment]": "FS-STRIPE-001",
    }
    status, intent = call("POST", "/payment_intents", fields, f"fs-stripe-001-create-{case_id}")
    if status != 200:
        err = intent.get("error", {})
        print(json.dumps({"stage": "create_rejected", "http_status": status,
                          "type": err.get("type"), "code": err.get("code"),
                          "param": err.get("param"), "message": err.get("message"),
                          "request_log_url": err.get("request_log_url")}), flush=True)
        raise AssertionError(f"create rejected by Stripe: HTTP {status}")
    pid = intent["id"]
    ensure_status(intent, "requires_capture", "manual authorisation")
    print(json.dumps({"case": case_id, "stage": "authorised", "id": pid, "status": intent["status"], "livemode": intent["livemode"]}))
    assert intent["livemode"] is False

    # Branch A: the FlowSignal reference decision is now REVOKED.
    # The experiment explicitly tests Stripe's provider-native behaviour
    # *without* FlowSignal enforcement. Cancel before capture.
    status, cancelled = call("POST", f"/payment_intents/{pid}/cancel",
                             {"cancellation_reason": "requested_by_customer"},
                             f"fs-stripe-001-cancel-{case_id}")
    assert status == 200, f"cancel failed: HTTP {status} {cancelled.get('error', {}).get('code')}"
    ensure_status(cancelled, "canceled", "cancel after simulated revocation")
    print(json.dumps({"stage": "cancelled", "id": pid, "status": cancelled["status"]}))

    # An attempted capture of a cancelled PaymentIntent must be rejected.
    status, capture = call("POST", f"/payment_intents/{pid}/capture", {},
                           f"fs-stripe-001-capture-after-cancel-{case_id}")
    assert status >= 400, f"cancelled intent unexpectedly capturable: HTTP {status}"
    print(json.dumps({"stage": "capture_after_cancel", "id": pid,
                      "http_status": status, "error_code": capture.get("error", {}).get("code")}))

    status, final = call("GET", f"/payment_intents/{pid}")
    assert status == 200
    ensure_status(final, "canceled", "final provider state")
    print(json.dumps({"stage": "final", "id": pid, "status": final["status"], "livemode": final["livemode"]}))


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FS-STRIPE-001 FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
