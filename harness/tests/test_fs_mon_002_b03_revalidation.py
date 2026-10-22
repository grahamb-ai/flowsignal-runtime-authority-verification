from dataclasses import replace
from app.engines.deployment_monitoring_guard import DeploymentRequest, MonitoringPolicy, MonitoringAssessment
from app.engines.simulated_deployment_revalidation import RevalidatedSimulatedController

D="a"*64
REQ=DeploymentRequest("agent", D, "service:example", "receipt")
POLICY=MonitoringPolicy("p1", frozenset({"alerts"}))
GOOD=MonitoringAssessment(D, "service:example", "p1", frozenset({"alerts"}), True)

def test_valid_deployment_forms_simulated_consequence():
    c=RevalidatedSimulatedController(POLICY, lambda _: GOOD, lambda _: True)
    assert c.deploy(REQ).formed
    assert c.deployed_digest(REQ.target)==D

def test_authority_revoked_between_checks_is_refused():
    state={"authorised":True}
    c=RevalidatedSimulatedController(POLICY, lambda _: GOOD, lambda _: state["authorised"])
    r=c.deploy(REQ,before_commit=lambda: state.update(authorised=False))
    assert (r.decision,r.formed)==("REFUSE",False)
    assert r.reason_code=="FINAL_REVALIDATION_DEPLOYMENT_AUTHORITY_NOT_ESTABLISHED"
    assert c.deployed_digest(REQ.target) is None

def test_monitoring_removed_between_checks_is_refused():
    state={"assessment":GOOD}
    c=RevalidatedSimulatedController(POLICY, lambda _: state["assessment"], lambda _: True)
    r=c.deploy(REQ,before_commit=lambda: state.update(assessment=replace(GOOD,present_controls=frozenset())))
    assert r.reason_code=="FINAL_REVALIDATION_MANDATORY_MONITORING_ABSENT"
    assert not r.formed
    assert c.deployed_digest(REQ.target) is None

def test_changed_artifact_evidence_between_checks_is_refused():
    state={"assessment":GOOD}
    c=RevalidatedSimulatedController(POLICY, lambda _: state["assessment"], lambda _: True)
    r=c.deploy(REQ,before_commit=lambda: state.update(assessment=replace(GOOD,artifact_digest="b"*64)))
    assert not r.formed
    assert r.reason_code=="FINAL_REVALIDATION_MONITORING_ATTESTATION_BINDING_MISMATCH"

def test_precommit_exception_fails_closed():
    c=RevalidatedSimulatedController(POLICY, lambda _: GOOD, lambda _: True)
    def fail(): raise RuntimeError("interrupted")
    r=c.deploy(REQ,before_commit=fail)
    assert (r.reason_code,r.formed)==("PRECOMMIT_INTERRUPTED",False)
