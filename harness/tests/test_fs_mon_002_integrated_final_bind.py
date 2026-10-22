from dataclasses import replace
from app.engines.deployment_monitoring_guard import DeploymentRequest
from app.engines.monitoring_policy_auth import sign_policy
from app.engines.monitoring_evidence_auth import issue_evidence
from app.engines.integrated_final_bind_reference import FinalBindReferenceExecutor

PK=b"test-policy"; EK=b"test-evidence"; NOW=1792660000; D="a"*64
REQ=DeploymentRequest("agent",D,"service:one","receipt-1")
P=sign_policy(PK,"monitor",4,{"alerts","audit"})
E=issue_evidence(EK,artifact_digest=D,target=REQ.target,policy_id=P.policy_id,
    controls={"alerts","audit"},issued_at=NOW-10,expires_at=NOW+20,nonce="abc")
def executor(evidence=E,policy=P,authorised=True):
    return FinalBindReferenceExecutor(policy,evidence,policy_key=PK,
        evidence_key=EK,expected_policy_id="monitor",min_version=4,now=NOW,
        authorised=authorised)

def test_valid_prepared_commit_formed():
    with executor() as x:
        assert x.request("prepare",REQ)[0]=="PREPARED"
        assert x.request("commit",REQ)==("ALLOW","SIMULATED_CONSEQUENCE_FORMED",True)
        assert x.request("read",REQ.target)[1]==D

def test_revoked_between_prepare_and_commit_refused():
    with executor() as x:
        assert x.request("prepare",REQ)[0]=="PREPARED"
        assert x.request("set_authority",False)[0]=="OK"
        assert x.request("commit",REQ)==("REFUSE","AUTHORITY_CHANGED_BEFORE_COMMIT",False)
        assert x.request("read",REQ.target)[1] is None

def test_revocation_then_regrant_still_invalidates_old_preparation():
    with executor() as x:
        x.request("prepare",REQ)
        x.request("set_authority",False)
        x.request("set_authority",True)
        assert x.request("commit",REQ)[1]=="AUTHORITY_CHANGED_BEFORE_COMMIT"
        assert x.request("read",REQ.target)[1] is None

def test_changed_artifact_cannot_commit():
    with executor() as x:
        x.request("prepare",REQ)
        assert x.request("commit",replace(REQ,artifact_digest="b"*64))[0]=="REFUSE"
        assert x.request("read",REQ.target)[1] is None

def test_no_prepare_does_not_commit():
    with executor() as x:
        assert x.request("commit",REQ)[1]=="NO_MATCHING_PREPARATION"

def test_one_shot_preparation():
    with executor() as x:
        x.request("prepare",REQ)
        assert x.request("commit",REQ)[0]=="ALLOW"
        assert x.request("commit",REQ)[1]=="NO_MATCHING_PREPARATION"

def test_forged_evidence_blocks_prepare():
    bad=replace(E,signature="0"*64)
    with executor(evidence=bad) as x:
        assert x.request("prepare",REQ)[0]=="REFUSE"
        assert x.request("commit",REQ)[0]=="REFUSE"

def test_forged_policy_blocks_prepare():
    bad=sign_policy(b"wrong","monitor",4,{"alerts","audit"})
    with executor(policy=bad) as x:
        assert x.request("prepare",REQ)[0]=="REFUSE"
        assert x.request("commit",REQ)[0]=="REFUSE"

def test_unauthorised_initial_state_blocks_prepare():
    with executor(authorised=False) as x:
        assert x.request("prepare",REQ)[1]=="AUTHORITY_NOT_ESTABLISHED"
        assert x.request("read",REQ.target)[1] is None

def test_direct_write_not_exposed():
    with executor() as x:
        assert x.request("write",(REQ.target,D))[1]=="UNSUPPORTED_OPERATION"
        assert x.request("read",REQ.target)[1] is None
