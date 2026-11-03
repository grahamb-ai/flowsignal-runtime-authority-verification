"""FS-STRIPE-005: protected capture adapter, reference candidate.

Only this adapter receives provider credentials. Callers supply a signed RAI
assertion, exact payment ID and action hash, never a Stripe credential.
The owner is consulted immediately before dispatch; an owner commitment and
provider capture are NOT atomic. On transport ambiguity we retrieve provider
state and return UNRESOLVED if no conclusive evidence exists.

No production isolation, provider route closure, or external atomicity claim.
"""
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

class CaptureProvider(Protocol):
    def retrieve(self, payment_id: str) -> dict: ...
    def capture(self, payment_id: str, signature: str) -> dict: ...

class AuthorityBoundary(Protocol):
    def commit(self, envelope: dict, action_hash: str) -> tuple[int,dict]: ...

@dataclass(frozen=True)
class CaptureOutcome:
    status: str
    reason: str
    payment_id: str
    provider_status: str | None = None

def execute_capture(
    provider: CaptureProvider, authority: AuthorityBoundary, *,
    payment_id: str, envelope: dict, action_hash: str,
    before_provider_dispatch=None,
) -> CaptureOutcome:
    """No automatic retry. Provider readback is authoritative for its status."""
    if not isinstance(payment_id,str) or not payment_id.startswith("pi_"):
        return CaptureOutcome("REFUSE","INVALID_PAYMENT_ID",str(payment_id))
    if not isinstance(action_hash,str) or len(action_hash)!=64:
        return CaptureOutcome("REFUSE","INVALID_BINDING",payment_id)
    if not isinstance(envelope,dict) or not isinstance(envelope.get("permit"),dict):
        return CaptureOutcome("REFUSE","NO_SIGNED_PERMIT",payment_id)
    permit=envelope["permit"]
    signature=permit.get("signature")
    if not isinstance(signature,str) or not signature:
        return CaptureOutcome("REFUSE","NO_PERMIT_SIGNATURE",payment_id)
    if permit.get("action_binding_hash")!=action_hash:
        return CaptureOutcome("REFUSE","PERMIT_BINDING_MISMATCH",payment_id)

    try:
        observed=provider.retrieve(payment_id)
    except Exception:
        return CaptureOutcome("UNRESOLVED","PROVIDER_PREFLIGHT_UNAVAILABLE",payment_id)
    if (observed.get("livemode") is not False
            or observed.get("currency")!="gbp"
            or observed.get("amount")!=100
            or observed.get("capture_method")!="manual"
            or observed.get("status")!="requires_capture"
            or observed.get("metadata",{}).get("rai_action_binding_hash")!=action_hash):
        return CaptureOutcome("REFUSE","PROVIDER_OPERATION_MISMATCH",payment_id,
                              observed.get("status"))

    try:
        code,decision=authority.commit(envelope,action_hash)
    except Exception:
        return CaptureOutcome("UNRESOLVED","OWNER_COMMIT_OUTCOME_UNKNOWN",payment_id)
    if code!=200 or decision.get("status")!="WITNESSED_CONSEQUENCE_FORMED":
        return CaptureOutcome("REFUSE","AUTHORITY_OWNER_REFUSED",payment_id)

    # Test hook allows deterministic revocation after owner commit, before
    # provider dispatch. A second owner read cannot guarantee external
    # atomicity; never claim this as complete prevention.
    if before_provider_dispatch is not None:
        before_provider_dispatch()

    try:
        final=provider.capture(payment_id,signature)
    except Exception:
        try:
            final=provider.retrieve(payment_id)
        except Exception:
            return CaptureOutcome("UNRESOLVED","PROVIDER_OUTCOME_UNKNOWN",payment_id)
    if final.get("livemode") is not False:
        return CaptureOutcome("UNRESOLVED","PROVIDER_MODE_UNVERIFIED",payment_id)
    # Independently read back after any capture response.
    try:
        confirmed=provider.retrieve(payment_id)
    except Exception:
        return CaptureOutcome("UNRESOLVED","PROVIDER_READBACK_UNAVAILABLE",payment_id)
    if (confirmed.get("livemode") is False and confirmed.get("status")=="succeeded"
            and confirmed.get("amount_received")==100
            and confirmed.get("metadata",{}).get("rai_action_binding_hash")==action_hash):
        return CaptureOutcome("CONFIRMED","PROVIDER_CAPTURE_CONFIRMED",payment_id,"succeeded")
    return CaptureOutcome("UNRESOLVED","PROVIDER_NOT_CONFIRMED",payment_id,
                          confirmed.get("status"))
