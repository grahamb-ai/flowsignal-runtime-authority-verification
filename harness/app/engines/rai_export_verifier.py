"""Pure verifier for exported RAI permit + trusted final-bind assertion.

No database configuration or executor side effects. This verifies reference
cryptographic integrity and correspondence only; current authority is checked
by the separate authority owner before consequence formation.
"""
from datetime import datetime,timezone
import hashlib,hmac,json

from app.engines.permit_authority import ExecutionPermit,verify_execution_permit

def validate_export(envelope,bridge_key:bytes):
    if not isinstance(envelope,dict):
        return "MISSING_FINAL_BIND_ASSERTION",None
    try:
        permit=ExecutionPermit(**envelope["permit"])
        statement=envelope["statement"]
        provided=envelope["bridge_mac"]
        if not isinstance(statement,dict) or not isinstance(provided,str):
            return "BAD_ASSERTION",None
        canonical=json.dumps(statement,sort_keys=True,separators=(",",":")).encode()
        expected=hmac.new(bridge_key,canonical,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided,expected):
            return "UNTRUSTED_BRIDGE_ASSERTION",None
        if not verify_execution_permit(permit):
            return "INVALID_RAI_PERMIT",None
        required=("determination_id","constraint_id","operation_id",
                  "execution_attempt_id","provenance_id")
        if not all(isinstance(statement.get(k),str) and statement[k] for k in required):
            return "MISSING_FINAL_BIND_PROVENANCE",None
        if (statement["permit_signature"]!=permit.signature or
            statement["action_binding_hash"]!=permit.action_binding_hash or
            statement["determination_id"]!=permit.rai_determination_id or
            statement["constraint_id"]!=permit.rai_constraint_id or
            statement["operation_id"]!=permit.rai_protected_operation_id or
            statement["execution_attempt_id"]!=permit.rai_execution_attempt_id):
            return "FINAL_BIND_CORRESPONDENCE_INVALID",None
        if permit.valid_until is None or datetime.now(timezone.utc)>datetime.fromisoformat(
                permit.valid_until).astimezone(timezone.utc):
            return "PERMIT_EXPIRED",None
    except (KeyError,TypeError,ValueError,AttributeError):
        return "INVALID_ENVELOPE",None
    return "VERIFIED",permit
