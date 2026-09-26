from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


# Harness-only evidence-integrity key for represented consequence outcomes.
# This demonstrates tamper-evident consequence evidence; it is not production
# key management, durable storage, external settlement evidence or a deployment
# trust boundary.
_CONSEQUENCE_RECEIPT_KEY = b"flowsignal-pmq001-consequence-receipt-harness-key"


@dataclass(frozen=True)
class ConsequenceOutcomeReceipt:
    id: str
    authority_receipt_id: str | None
    action_binding_hash: str
    authority_state_version: int | None
    outcome: str
    consequence_formed: bool
    recorded_at: str
    receipt_hmac: str


def _payload(
    *,
    receipt_id: str,
    authority_receipt_id: str | None,
    action_binding_hash: str,
    authority_state_version: int | None,
    outcome: str,
    consequence_formed: bool,
    recorded_at: str,
) -> bytes:
    return json.dumps(
        {
            "receipt_id": receipt_id,
            "authority_receipt_id": authority_receipt_id,
            "action_binding_hash": action_binding_hash,
            "authority_state_version": authority_state_version,
            "outcome": outcome,
            "consequence_formed": consequence_formed,
            "recorded_at": recorded_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sign(**kwargs) -> str:
    return hmac.new(
        _CONSEQUENCE_RECEIPT_KEY,
        _payload(**kwargs),
        hashlib.sha256,
    ).hexdigest()


def create_consequence_outcome_receipt(
    *,
    authority_receipt_id: str | None,
    action_binding_hash: str,
    authority_state_version: int | None,
    outcome: str,
) -> ConsequenceOutcomeReceipt:
    receipt_id = str(uuid.uuid4())
    recorded_at = datetime.now(timezone.utc).isoformat()
    consequence_formed = outcome == "CONSEQUENCE_FORMED"
    fields = {
        "receipt_id": receipt_id,
        "authority_receipt_id": authority_receipt_id,
        "action_binding_hash": action_binding_hash,
        "authority_state_version": authority_state_version,
        "outcome": outcome,
        "consequence_formed": consequence_formed,
        "recorded_at": recorded_at,
    }
    return ConsequenceOutcomeReceipt(
        id=receipt_id,
        authority_receipt_id=authority_receipt_id,
        action_binding_hash=action_binding_hash,
        authority_state_version=authority_state_version,
        outcome=outcome,
        consequence_formed=consequence_formed,
        recorded_at=recorded_at,
        receipt_hmac=_sign(**fields),
    )


def verify_consequence_outcome_receipt(receipt: ConsequenceOutcomeReceipt) -> bool:
    expected = _sign(
        receipt_id=receipt.id,
        authority_receipt_id=receipt.authority_receipt_id,
        action_binding_hash=receipt.action_binding_hash,
        authority_state_version=receipt.authority_state_version,
        outcome=receipt.outcome,
        consequence_formed=receipt.consequence_formed,
        recorded_at=receipt.recorded_at,
    )
    return hmac.compare_digest(receipt.receipt_hmac, expected)
