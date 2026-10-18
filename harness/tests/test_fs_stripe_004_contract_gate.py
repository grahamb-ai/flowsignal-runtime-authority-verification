"""Fail-closed structural contract probes. Never authorises Stripe capture."""
from app.engines.fs_stripe_004_contract_gate import check_receipt_structure

def sample():
    return {
        "id": "r1", "scenario_id": "s1", "decision": "ALLOW",
        "reason_code": "OK", "sealed_at": "2026-10-18T00:00:00Z",
        "valid_until": "2026-10-18T00:01:00Z",
        "action_binding_hash": "abc", "authority_state_version": 7,
        "receipt_hmac": "untrusted-placeholder", "request_snapshot": {},
        "checks": [], "evidence_references": [],
    }

def test_unverified_receipt_never_authorises():
    r = check_receipt_structure(sample(), expected_action_hash="abc", expected_version=7)
    assert not r.accepted and r.reason == "AUTHENTICITY_UNVERIFIED"

def test_changed_payment_action_refused():
    r = check_receipt_structure(sample(), expected_action_hash="different", expected_version=7)
    assert not r.accepted and r.reason == "ACTION_BINDING_MISMATCH"

def test_stale_version_refused():
    r = check_receipt_structure(sample(), expected_action_hash="abc", expected_version=8)
    assert not r.accepted and r.reason == "AUTHORITY_VERSION_MISMATCH"

def test_missing_receipt_fields_refused():
    r = check_receipt_structure({"decision": "ALLOW"}, expected_action_hash="abc", expected_version=7)
    assert not r.accepted and r.reason == "RECEIPT_FIELDS_MISSING"

def test_refuse_is_not_promoted():
    p = sample()
    p["decision"] = "REFUSE"
    r = check_receipt_structure(p, expected_action_hash="abc", expected_version=7)
    assert not r.accepted and r.reason == "AUTHORITY_NOT_ALLOWED"
