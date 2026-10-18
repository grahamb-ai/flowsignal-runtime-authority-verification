"""FS-STRIPE-004 contract gate — no Stripe calls, no authority claims.

Preliminary structural checks for a proposed Step 2 receipt. Structural
validity is NOT signature verification, independent authority, or clearance.
"""
from dataclasses import dataclass
from typing import Any

REQUIRED = frozenset({
    "id", "scenario_id", "decision", "reason_code", "sealed_at",
    "valid_until", "action_binding_hash", "authority_state_version",
    "receipt_hmac", "request_snapshot", "checks", "evidence_references",
})

@dataclass(frozen=True)
class ContractResult:
    accepted: bool
    reason: str

def check_receipt_structure(receipt: Any, *, expected_action_hash: str,
                            expected_version: int) -> ContractResult:
    if not isinstance(receipt, dict):
        return ContractResult(False, "RECEIPT_NOT_OBJECT")
    if not REQUIRED.issubset(receipt):
        return ContractResult(False, "RECEIPT_FIELDS_MISSING")
    if receipt["decision"] != "ALLOW":
        return ContractResult(False, "AUTHORITY_NOT_ALLOWED")
    if receipt["action_binding_hash"] != expected_action_hash:
        return ContractResult(False, "ACTION_BINDING_MISMATCH")
    if type(receipt["authority_state_version"]) is not int:
        return ContractResult(False, "INVALID_AUTHORITY_VERSION")
    if receipt["authority_state_version"] != expected_version:
        return ContractResult(False, "AUTHORITY_VERSION_MISMATCH")
    # The reference receipt_hmac is not a production credential. A matching
    # string does not authenticate the issuer. Fail closed until actual Step 2
    # verifier, key trust and deployed authority contract are pinned.
    return ContractResult(False, "AUTHENTICITY_UNVERIFIED")
