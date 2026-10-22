"""B04 bounded reference for independently authenticated monitoring policy.

Trust root (HMAC key and minimum version) is injected by trusted controller.
No production key custody, rollback-resistant storage or IAM isolation claimed.
"""
from dataclasses import dataclass
import hashlib,hmac,json

@dataclass(frozen=True)
class SignedPolicy:
    policy_id:str
    version:int
    required_controls:tuple[str,...]
    signature:str

def _body(p):
    return json.dumps({"policy_id":p.policy_id,"version":p.version,
      "required_controls":p.required_controls},sort_keys=True,separators=(",",":")).encode()

def sign_policy(key, policy_id, version, controls):
    p=SignedPolicy(policy_id,version,tuple(sorted(controls)),"")
    return SignedPolicy(p.policy_id,p.version,p.required_controls,
                        hmac.new(key,_body(p),hashlib.sha256).hexdigest())

def verify_policy(policy,key,*,expected_id,min_version):
    if not isinstance(policy,SignedPolicy):
        return "DENIED_POLICY_MISSING"
    if not isinstance(policy.signature,str):
        return "DENIED_POLICY_SIGNATURE_INVALID"
    sig=hmac.new(key,_body(policy),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig,policy.signature):
        return "DENIED_POLICY_SIGNATURE_INVALID"
    if policy.policy_id!=expected_id:
        return "DENIED_POLICY_ID_MISMATCH"
    if policy.version<min_version:
        return "DENIED_POLICY_ROLLBACK"
    if not policy.required_controls:
        return "DENIED_POLICY_CONTROLS_MISSING"
    return "VERIFIED"
