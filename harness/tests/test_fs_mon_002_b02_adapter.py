from dataclasses import replace
from app.engines.deployment_monitoring_guard import DeploymentRequest, MonitoringPolicy
from app.engines.monitoring_evidence_auth import issue_evidence
from app.engines.authenticated_deployment_adapter import evaluate_authenticated_deployment

KEY=b"private-reference-key"
D="a"*64
REQ=DeploymentRequest("agent",D,"service:a","receipt-1")
POL=MonitoringPolicy("policy-v1",frozenset({"alert","audit"}))
NOW=1792660000

def evidence(key=KEY,controls=("alert","audit")):
    return issue_evidence(key,artifact_digest=D,target=REQ.target,
        policy_id=POL.policy_id,controls=controls,
        issued_at=NOW-10,expires_at=NOW+30,nonce="nonce-1")
def run(e, authority=True, seen=None):
    return evaluate_authenticated_deployment(REQ,policy=POL,evidence=e,
        verification_key=KEY,authority_check=lambda _: authority,
        now=NOW,seen_nonces=set() if seen is None else seen)
def test_signed_current_evidence_allows():
    assert run(evidence())[0]=="ALLOW"
def test_forged_signer_refused():
    assert run(evidence(b"wrong-key"))[0]=="REFUSE"
def test_missing_monitoring_refused():
    assert run(evidence(controls=("audit",)))[0]=="REFUSE"
def test_authority_denied_even_if_signed():
    assert run(evidence(),authority=False)[0]=="REFUSE"
def test_previous_nonce_refused():
    assert run(evidence(),seen={"nonce-1"})==("REFUSE","DENIED_EVIDENCE_REPLAY")
