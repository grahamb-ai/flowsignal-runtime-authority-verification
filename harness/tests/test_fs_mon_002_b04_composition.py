from app.engines.deployment_monitoring_guard import DeploymentRequest
from app.engines.monitoring_policy_auth import sign_policy
from app.engines.monitoring_evidence_auth import issue_evidence
from app.engines.policy_evidence_composition import verify_deployment_controls
PK=b"policy-owner"
EK=b"evidence-owner"
NOW=1792660000
REQ=DeploymentRequest("agent","a"*64,"service:billing","receipt")
P=sign_policy(PK,"required-monitoring",5,{"alerts","audit"})
E=issue_evidence(EK,artifact_digest=REQ.artifact_digest,target=REQ.target,
                 policy_id=P.policy_id,controls={"alerts","audit"},
                 issued_at=NOW-10,expires_at=NOW+10,nonce="test-1")
def check(p=P,e=E,minimum_version=5):
    return verify_deployment_controls(REQ,p,e,policy_key=PK,
         evidence_key=EK,expected_policy_id="required-monitoring",
         minimum_policy_version=minimum_version,now=NOW,nonce_ledger=set())
def test_valid_policy_and_evidence(): assert check()[0]=="ALLOW"
def test_unsigned_agent_policy_cannot_replace_required_policy():
    p=sign_policy(b"wrong",P.policy_id,100,{"audit"})
    assert check(p)[0]=="REFUSE"
def test_signed_old_policy_rejected_when_current_version_advances():
    assert check(minimum_version=6)==("REFUSE","DENIED_POLICY_ROLLBACK")
def test_valid_policy_missing_monitoring_refuses():
    e=issue_evidence(EK,artifact_digest=REQ.artifact_digest,target=REQ.target,
        policy_id=P.policy_id,controls={"audit"},issued_at=NOW-10,
        expires_at=NOW+10,nonce="test-2")
    assert check(e=e)==("REFUSE","DENIED_MONITORING_ABSENT")
