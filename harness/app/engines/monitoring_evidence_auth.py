"""B02 reference: authenticated, bound, expiring monitoring assertions.

HMAC provides integrity under an independently held symmetric key in this
bounded reference. This is NOT a production attestator, PKI, HSM or key isolation.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json

@dataclass(frozen=True)
class MonitoringEvidence:
    artifact_digest: str
    target: str
    policy_id: str
    required_controls: tuple[str, ...]
    issued_at: int
    expires_at: int
    nonce: str
    signature: str

def _payload(e):
    return json.dumps({k:getattr(e,k) for k in (
        "artifact_digest","target","policy_id","required_controls",
        "issued_at","expires_at","nonce")},sort_keys=True,separators=(",",":")).encode()

def issue_evidence(key, *, artifact_digest, target, policy_id, controls, issued_at, expires_at, nonce):
    unsigned=MonitoringEvidence(artifact_digest,target,policy_id,tuple(sorted(controls)),issued_at,expires_at,nonce,"")
    return MonitoringEvidence(**{**unsigned.__dict__,
        "signature":hmac.new(key,_payload(unsigned),hashlib.sha256).hexdigest()})

def verify_evidence(e, key, *, artifact_digest, target, policy_id, required_controls, now=None,
                    seen_nonces=None):
    now=int(datetime.now(timezone.utc).timestamp()) if now is None else now
    if not isinstance(e, MonitoringEvidence):
        return "DENIED_EVIDENCE_MISSING"
    if not isinstance(e.signature,str) or len(e.signature)!=64:
        return "DENIED_SIGNATURE_INVALID"
    expected=hmac.new(key,_payload(e),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,e.signature):
        return "DENIED_SIGNATURE_INVALID"
    if e.artifact_digest!=artifact_digest or e.target!=target or e.policy_id!=policy_id:
        return "DENIED_EVIDENCE_BINDING_MISMATCH"
    if not set(required_controls).issubset(e.required_controls):
        return "DENIED_MONITORING_ABSENT"
    if e.issued_at>now or e.expires_at<=now or e.expires_at<=e.issued_at:
        return "DENIED_EVIDENCE_NOT_CURRENT"
    if not e.nonce or (seen_nonces is not None and e.nonce in seen_nonces):
        return "DENIED_EVIDENCE_REPLAY"
    return "VERIFIED"
