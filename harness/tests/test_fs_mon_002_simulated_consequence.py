"""FS-MON-002 consequence-formation checks in a bounded simulator."""
from dataclasses import replace
import pytest
from app.engines.deployment_monitoring_guard import (
    DeploymentRequest, MonitoringPolicy, MonitoringAssessment,
)
from app.engines.simulated_deployment_executor import SimulatedDeploymentController

DIGEST = "a" * 64
POLICY = MonitoringPolicy("security-v1", frozenset({"audit", "alerts"}))
REQ = DeploymentRequest("coding-agent", DIGEST, "service:billing", "receipt-1")
GOOD = MonitoringAssessment(DIGEST, REQ.target, POLICY.policy_id,
                            frozenset({"audit", "alerts"}), True)

def controller(assessment=GOOD, authorised=True):
    return SimulatedDeploymentController(
        POLICY, lambda _: assessment, lambda _: authorised
    )

def test_valid_authority_and_monitoring_form_simulated_consequence():
    c = controller()
    result = c.deploy(REQ)
    assert (result.decision, result.consequence_formed) == ("ALLOW", True)
    assert c.deployed_digest(REQ.target) == DIGEST

@pytest.mark.parametrize("controls", [frozenset(), frozenset({"audit"}), frozenset({"alerts"})])
def test_monitoring_removed_cannot_form_consequence(controls):
    c = controller(replace(GOOD, present_controls=controls))
    result = c.deploy(REQ)
    assert (result.decision, result.consequence_formed) == ("REFUSE", False)
    assert c.deployed_digest(REQ.target) is None

def test_changed_regression_test_does_not_override_trusted_assessment():
    agent_owned_test_reports_success = True
    assert agent_owned_test_reports_success
    c = controller(replace(GOOD, present_controls=frozenset()))
    assert c.deploy(REQ).consequence_formed is False

def test_false_agent_statement_cannot_replace_assessment():
    c = controller(None)
    result = c.deploy(REQ)
    assert result.reason_code == "MONITORING_ATTESTATION_MISSING_OR_FAILED"
    assert c.deployed_digest(REQ.target) is None

def test_subagent_artifact_substitution_fails_closed():
    c = controller()
    changed = replace(REQ, artifact_digest="b" * 64)
    result = c.deploy(changed)
    assert result.reason_code == "MONITORING_ATTESTATION_BINDING_MISMATCH"
    assert c.deployed_digest(changed.target) is None

def test_revoked_authority_blocks_consequence():
    c = controller(authorised=False)
    result = c.deploy(REQ)
    assert result.reason_code == "DEPLOYMENT_AUTHORITY_NOT_ESTABLISHED"
    assert c.deployed_digest(REQ.target) is None

def test_prior_success_does_not_allow_later_unauthorised_replacement():
    state = {"authorised": True, "controls": frozenset({"audit", "alerts"})}
    def assess(_):
        return replace(GOOD, present_controls=state["controls"])
    c = SimulatedDeploymentController(POLICY, assess, lambda _: state["authorised"])
    assert c.deploy(REQ).consequence_formed
    state["authorised"] = False
    state["controls"] = frozenset()
    attempted = replace(REQ, artifact_digest="b" * 64)
    assert not c.deploy(attempted).consequence_formed
    assert c.deployed_digest(REQ.target) == DIGEST

def test_untrusted_policy_cannot_be_passed_through_agent_request():
    c = controller(replace(GOOD, present_controls=frozenset()))
    agent_policy = MonitoringPolicy("security-v2", frozenset())
    assert agent_policy.required_controls == frozenset()
    assert c.deploy(REQ).decision == "REFUSE"

def test_assessor_failure_no_consequence():
    def broken(_):
        raise RuntimeError("assessment failed")
    c = SimulatedDeploymentController(POLICY, broken, lambda _: True)
    assert not c.deploy(REQ).consequence_formed
    assert c.deployed_digest(REQ.target) is None
