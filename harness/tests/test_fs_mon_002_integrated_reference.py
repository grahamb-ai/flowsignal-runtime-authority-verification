from dataclasses import replace
from app.engines.deployment_monitoring_guard import DeploymentRequest
from app.engines.monitoring_policy_auth import sign_policy
from app.engines.monitoring_evidence_auth import issue_evidence
from app.engines.integrated_monitoring_reference import IntegratedReferenceExecutor

PK=b"test-policy-owner"
EK=b"test-evidence-owner"
NOW=1792660000
D="a"*64
REQ=DeploymentRequest("agent",D,"service:test","receipt-1")
P=sign_policy(PK,"monitor-v1",4,{"audit","alerts"})
E=issue_evidence(EK,artifact_digest=D,target=REQ.target,policy_id=P.policy_id,
    controls={"audit","alerts"},issued_at=NOW-10,expires_at=NOW+10,nonce="n1")

def client(policy=P,evidence=E,authorised=True,min_version=4):
    return IntegratedReferenceExecutor(policy,evidence,policy_key=PK,evidence_key=EK,
        expected_policy_id="monitor-v1",min_version=min_version,now=NOW,authorised=authorised)

def test_valid_authentic_inputs_form_simulated_consequence():
    with client() as c:
        assert c.request("deploy",REQ)==("ALLOW","SIMULATED_CONSEQUENCE_FORMED",True)
        assert c.request("read",REQ.target)==("STATE",D,False)

def test_missing_monitoring_refused_without_consequence():
    e=issue_evidence(EK,artifact_digest=D,target=REQ.target,policy_id=P.policy_id,
        controls={"audit"},issued_at=NOW-10,expires_at=NOW+10,nonce="n2")
    with client(evidence=e) as c:
        assert c.request("deploy",REQ)[0]=="REFUSE"
        assert c.request("read",REQ.target)==("STATE",None,False)

def test_forged_evidence_refused():
    e=issue_evidence(b"agent-key",artifact_digest=D,target=REQ.target,policy_id=P.policy_id,
        controls={"audit","alerts"},issued_at=NOW-10,expires_at=NOW+10,nonce="n3")
    with client(evidence=e) as c:
        assert c.request("deploy",REQ)[0]=="REFUSE"
        assert c.request("read",REQ.target)[1] is None

def test_forged_policy_refused():
    p=sign_policy(b"agent-key","monitor-v1",99,{"audit"})
    with client(policy=p) as c:
        assert c.request("deploy",REQ)[0]=="REFUSE"
        assert c.request("read",REQ.target)[1] is None

def test_rollback_policy_refused():
    with client(min_version=5) as c:
        assert c.request("deploy",REQ)[1]=="DENIED_POLICY_ROLLBACK"
        assert c.request("read",REQ.target)[1] is None

def test_unapproved_authority_refused():
    with client(authorised=False) as c:
        assert c.request("deploy",REQ)[1]=="AUTHORITY_NOT_ESTABLISHED"
        assert c.request("read",REQ.target)[1] is None

def test_artifact_substitution_refused():
    with client() as c:
        assert c.request("deploy",replace(REQ,artifact_digest="b"*64))[0]=="REFUSE"
        assert c.request("read",REQ.target)[1] is None

def test_unsupported_direct_write_refused():
    with client() as c:
        assert c.request("write",(REQ.target,D))[0]=="REFUSE"
        assert c.request("read",REQ.target)[1] is None

def test_local_client_mutation_not_remote_state():
    with client(authorised=False) as c:
        local={REQ.target:D}
        assert local[REQ.target]==D
        assert c.request("read",REQ.target)[1] is None

def test_expired_evidence_refused():
    e=issue_evidence(EK,artifact_digest=D,target=REQ.target,policy_id=P.policy_id,
        controls={"audit","alerts"},issued_at=NOW-20,expires_at=NOW-1,nonce="n4")
    with client(evidence=e) as c:
        assert c.request("deploy",REQ)[1]=="DENIED_EVIDENCE_NOT_CURRENT"
        assert c.request("read",REQ.target)[1] is None
