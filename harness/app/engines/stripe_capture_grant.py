"""Exact Stripe PaymentIntent binding for a reference RAI final-bind grant.

The signer requires an original operation request whose action-binding hash
matches the genuine RAI permit. It then signs the exact Stripe capture
parameters into the exported bridge assertion. This is still a test-HMAC key,
NOT an independently protected institutional signing service.
"""
from dataclasses import replace
from decimal import Decimal
import hashlib,hmac,json

from app.engines.execution_gateway import ExecutionAttempt,action_binding_hash
from app.engines.rai_external_export_reference import export_final_bind

SCHEMA="FS-STRIPE-CAPTURE-001"

def bind_stripe_capture(req,permit,payment_id,*,bridge_key):
    if not isinstance(payment_id,str) or not payment_id.startswith("pi_"):
        return None
    if req.purpose!=f"FS-STRIPE-004 PaymentIntent {payment_id}":
        return None
    if req.amount!=Decimal("1.00") or req.currency.upper()!="GBP":
        return None
    attempt=ExecutionAttempt(actor_id=req.actor_id,principal_id=req.principal_id,
        action=req.action,target=req.target,amount=req.amount,currency=req.currency,
        source_account=req.source_account,beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time)
    if action_binding_hash(attempt)!=permit.action_binding_hash:
        return None
    grant=export_final_bind(permit,bridge_key=bridge_key)
    if grant is None:return None
    statement=dict(grant["statement"])
    statement.update(schema=SCHEMA,payment_intent_id=payment_id,
        amount_minor=100,currency="gbp",capture_method="manual")
    raw=json.dumps(statement,sort_keys=True,separators=(",",":")).encode()
    grant["statement"]=statement
    grant["bridge_mac"]=hmac.new(bridge_key,raw,hashlib.sha256).hexdigest()
    return grant
