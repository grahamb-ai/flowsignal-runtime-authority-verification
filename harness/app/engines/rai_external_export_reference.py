"""Bounded export of a genuine RAI final-bind permit to a separate actuator.

A bridge controlled by the reference harness signs a transferable assertion
only after checking the in-process RAI registry and final-bind provenance.
Not a production trust root, remote attestor, or distributed state proof.
"""
from dataclasses import asdict
import hashlib,hmac,json
from app.engines.permit_authority import verify_execution_permit
from app.engines.rai_execution_registry import get_rai_execution_binding,verify_rai_execution_binding
from app.engines.final_bind_provenance import verify_final_bind_provenance

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":")).encode()

def export_final_bind(permit, *, bridge_key:bytes):
    if permit is None or not verify_execution_permit(permit):
        return None
    binding=get_rai_execution_binding(permit.signature)
    if binding is None:
        return None
    if not verify_rai_execution_binding(
        permit_signature=permit.signature,determination_id=permit.rai_determination_id,
        constraint_id=permit.rai_constraint_id,
        protected_operation_id=permit.rai_protected_operation_id,
        authority_exercise_id=permit.rai_authority_exercise_id,
        execution_attempt_id=permit.rai_execution_attempt_id,
        action_binding_hash=permit.action_binding_hash):
        return None
    if not verify_final_bind_provenance(
        binding.final_bind_provenance_id,
        determination_id=binding.determination_id,
        constraint_id=binding.constraint_id,
        protected_operation_id=binding.protected_operation_id,
        authority_exercise_id=binding.authority_exercise_id,
        execution_attempt_id=binding.execution_attempt_id,
        action_binding_hash=binding.action_binding_hash,
        usage_reservation_id=binding.usage_reservation_id,
        permit_signature=permit.signature):
        return None
    statement={
        "permit_signature":permit.signature,
        "action_binding_hash":permit.action_binding_hash,
        "determination_id":binding.determination_id,
        "constraint_id":binding.constraint_id,
        "operation_id":binding.protected_operation_id,
        "execution_attempt_id":binding.execution_attempt_id,
        "provenance_id":binding.final_bind_provenance_id,
    }
    mac=hmac.new(bridge_key,canonical(statement),hashlib.sha256).hexdigest()
    return {"permit":asdict(permit),"statement":statement,"bridge_mac":mac}
