"""FS-STRIPE-005: bounded, test-only protected Stripe capture dispatcher.

Genuine reference RAI permit and owner admission must precede this function.
The dispatcher re-reads OWNER state immediately before the Stripe capture call.
It validates Stripe's independently retrieved manual-capture authorisation and
exact metadata binding, uses a stable idempotency key, and reconciles uncertain
responses by reading the PaymentIntent. It never automatically retries capture
after transport uncertainty.

A current-state read and Stripe capture are NOT one atomic transaction. There
remains a revocation interval between them; direct Stripe credential callers
remain out of scope. No production prevention claims.
"""
from dataclasses import dataclass
from hashlib import sha256

class DispatchRefused(RuntimeError):
    pass

@dataclass(frozen=True)
class DispatchResult:
    disposition: str
    payment_intent_id: str
    provider_status: str | None
    amount_received: int | None

def _checked_provider(intent, payment_id, bound_hash, amount_minor):
    if not isinstance(intent,dict):
        raise DispatchRefused("PROVIDER_RESPONSE_INVALID")
    if intent.get("id")!=payment_id or intent.get("livemode") is not False:
        raise DispatchRefused("PROVIDER_IDENTITY_OR_MODE_MISMATCH")
    if (intent.get("currency")!="gbp" or type(intent.get("amount")) is not int
            or intent["amount"]!=amount_minor or intent.get("capture_method")!="manual"):
        raise DispatchRefused("PROVIDER_AMOUNT_OR_CAPTURE_MISMATCH")
    if intent.get("metadata",{}).get("rai_action_binding_hash")!=bound_hash:
        raise DispatchRefused("PROVIDER_ACTION_BINDING_MISMATCH")
    return intent

def capture_once(*,payment_id,permit,grant,owner_commit,owner_version,
                 stripe,amount_minor=100,before_dispatch=None):
    """Enforce the local admission gate and verify Stripe final state.

    before_dispatch is a test-only synchronous hook for deterministic
    pre-capture revocation, not a mechanism granting production authority.
    """
    if not isinstance(payment_id,str) or not payment_id.startswith("pi_"):
        raise DispatchRefused("INVALID_PROVIDER_TARGET")
    if grant is None or permit is None:
        raise DispatchRefused("MISSING_RAI_FINAL_BIND")
    if grant.get("permit",{}).get("signature")!=permit.signature:
        raise DispatchRefused("PERMIT_PROVENANCE_MISMATCH")
    if grant.get("permit",{}).get("action_binding_hash")!=permit.action_binding_hash:
        raise DispatchRefused("GRANT_ACTION_MISMATCH")
    # A target identifier must be causally present in the original RAI bound
    # operation. A different PaymentIntent cannot be substituted post-bind.
    original=grant.get("statement",{})
    if original.get("permit_signature")!=permit.signature:
        raise DispatchRefused("GRANT_CORRESPONDENCE_INVALID")
    pre=_checked_provider(stripe.retrieve(payment_id),payment_id,
                          permit.action_binding_hash,amount_minor)
    if pre.get("status")!="requires_capture":
        raise DispatchRefused("PROVIDER_NOT_READY_FOR_CAPTURE")
    status,answer=owner_commit(grant,permit.action_binding_hash)
    if status!=200 or answer.get("status")!="WITNESSED_CONSEQUENCE_FORMED":
        return DispatchResult("REFUSED_BY_OWNER",payment_id,pre["status"],
                              pre.get("amount_received"))
    if before_dispatch is not None:
        before_dispatch()
    # Last local source check. A failure is an explicit refusal, not an
    # ambiguous fallback; never dispatch Stripe capture in this case.
    try:
        version=owner_version()
    except Exception:
        return DispatchResult("REFUSED_OWNER_UNAVAILABLE",payment_id,None,None)
    if type(version) is not int or version!=permit.authority_state_version:
        return DispatchResult("REFUSED_STALE_AUTHORITY",payment_id,None,None)
    again=_checked_provider(stripe.retrieve(payment_id),payment_id,
                            permit.action_binding_hash,amount_minor)
    if again["status"]!="requires_capture":
        raise DispatchRefused("PROVIDER_STATE_CHANGED")
    # Capture key binds target and single-use RAI signature; never use a fresh
    # key on a retry, including when provider acknowledgement was lost.
    idem="fs-stripe-005-"+sha256((payment_id+":"+permit.signature).encode()).hexdigest()
    try:
        stripe.capture_with_key(payment_id,idem)
    except Exception:
        try:
            observed=_checked_provider(stripe.retrieve(payment_id),payment_id,
                                       permit.action_binding_hash,amount_minor)
        except Exception:
            return DispatchResult("PROVIDER_OUTCOME_UNRESOLVED",payment_id,None,None)
        if observed["status"]=="succeeded" and observed.get("amount_received")==amount_minor:
            return DispatchResult("PROVIDER_CONFIRMED_FORMED",payment_id,
                                  observed["status"],amount_minor)
        # A pending authorization after a timeout does not prove absence of a
        # capture that may be processing, so never retry blindly.
        return DispatchResult("PROVIDER_OUTCOME_UNRESOLVED",payment_id,
                              observed["status"],observed.get("amount_received"))
    final=_checked_provider(stripe.retrieve(payment_id),payment_id,
                            permit.action_binding_hash,amount_minor)
    if final["status"]=="succeeded" and final.get("amount_received")==amount_minor:
        return DispatchResult("PROVIDER_CONFIRMED_FORMED",payment_id,
                              final["status"],amount_minor)
    return DispatchResult("PROVIDER_OUTCOME_UNRESOLVED",payment_id,
                          final["status"],final.get("amount_received"))
