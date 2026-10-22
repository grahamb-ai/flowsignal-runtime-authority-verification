from dataclasses import replace
import pytest
from app.engines.monitoring_evidence_auth import issue_evidence, verify_evidence

KEY=b"independent-verifier-secret-for-test-only"
D="a"*64
T="service:billing"
P="monitor-v1"
R={"security-alerts","audit"}
NOW=1792660000

def valid():
    return issue_evidence(KEY,artifact_digest=D,target=T,policy_id=P,
        controls=R,issued_at=NOW-20,expires_at=NOW+20,nonce="unique-1")

def check(e,**overrides):
    args=dict(artifact_digest=D,target=T,policy_id=P,required_controls=R,now=NOW)
    args.update(overrides)
    return verify_evidence(e,KEY,**args)

def test_valid_attestation(): assert check(valid())=="VERIFIED"
def test_forged_signature(): assert check(replace(valid(),signature="0"*64))=="DENIED_SIGNATURE_INVALID"
def test_tampered_controls(): assert check(replace(valid(),required_controls=("audit",)))=="DENIED_SIGNATURE_INVALID"
def test_tampered_artifact(): assert check(replace(valid(),artifact_digest="b"*64))=="DENIED_SIGNATURE_INVALID"
def test_other_artifact_binding(): assert check(valid(),artifact_digest="b"*64)=="DENIED_EVIDENCE_BINDING_MISMATCH"
def test_other_target_binding(): assert check(valid(),target="service:other")=="DENIED_EVIDENCE_BINDING_MISMATCH"
def test_other_policy_binding(): assert check(valid(),policy_id="monitor-v2")=="DENIED_EVIDENCE_BINDING_MISMATCH"
def test_expiry(): assert check(valid(),now=NOW+21)=="DENIED_EVIDENCE_NOT_CURRENT"
def test_future_issue(): assert check(valid(),now=NOW-21)=="DENIED_EVIDENCE_NOT_CURRENT"
def test_replay_marked_nonce(): assert check(valid(),seen_nonces={"unique-1"})=="DENIED_EVIDENCE_REPLAY"
def test_missing_required_control_signed_by_verifier():
    e=issue_evidence(KEY,artifact_digest=D,target=T,policy_id=P,
        controls={"audit"},issued_at=NOW-20,expires_at=NOW+20,nonce="unique-2")
    assert check(e)=="DENIED_MONITORING_ABSENT"
def test_wrong_signer_key():
    e=issue_evidence(b"unauthorised-key",artifact_digest=D,target=T,policy_id=P,
        controls=R,issued_at=NOW-20,expires_at=NOW+20,nonce="unique-3")
    assert check(e)=="DENIED_SIGNATURE_INVALID"
