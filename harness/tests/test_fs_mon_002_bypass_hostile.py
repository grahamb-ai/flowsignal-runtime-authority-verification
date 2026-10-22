"""FS-MON-002 hostile bypass characterization.

Tests are intentionally bounded to this in-memory Python reference controller.
Strict XFAILs preserve unsupported security properties; tests never touch
external services or production infrastructure.
"""
from dataclasses import replace
import pytest
from app.engines.deployment_monitoring_guard import (
    DeploymentRequest, MonitoringPolicy, MonitoringAssessment
)
from app.engines.simulated_deployment_executor import SimulatedDeploymentController

DIGEST = "a" * 64
EVIL = "b" * 64
POLICY = MonitoringPolicy("monitoring-v1", frozenset({"security-alerts", "audit"}))
REQ = DeploymentRequest("migration-agent", DIGEST, "service:example", "receipt-1")
GOOD = MonitoringAssessment(DIGEST, REQ.target, POLICY.policy_id,
                            frozenset({"security-alerts", "audit"}), True)
REMOVED = replace(GOOD, present_controls=frozenset())

def controller(assessment=GOOD, authority=True):
    return SimulatedDeploymentController(POLICY, lambda _: assessment,
                                         lambda _: authority)

@pytest.mark.xfail(strict=True, reason="FS-MON-002-B01: Python in-process store is directly mutable; no independent actuator isolation")
def test_B01_direct_store_mutation_cannot_form_consequence():
    c = controller(REMOVED, False)
    c._deployed[REQ.target] = EVIL
    assert c.deployed_digest(REQ.target) is None

def test_B01_direct_store_mutation_is_currently_possible():
    c = controller(REMOVED, False)
    c._deployed[REQ.target] = EVIL
    assert c.deployed_digest(REQ.target) == EVIL

@pytest.mark.xfail(strict=True, reason="FS-MON-002-B02: caller supplies unsigned assessment via trusted callback; no origin authenticity")
def test_B02_forged_callback_attestation_must_be_rejected():
    # Real artifact has no monitoring, but a forged callback claims GOOD.
    real_artifact_has_monitoring = False
    c = controller(GOOD, True)
    result = c.deploy(REQ)
    assert not result.consequence_formed, real_artifact_has_monitoring

def test_B02_unsigned_forged_callback_is_currently_accepted():
    c = controller(GOOD, True)
    assert c.deploy(REQ).consequence_formed is True

@pytest.mark.xfail(strict=True, reason="FS-MON-002-B03: assessment/authority can change after validation; no commit-time recheck")
def test_B03_post_approval_revocation_prevents_commit(monkeypatch):
    from app.engines import simulated_deployment_executor as module
    state = {"authority": True}
    original = module.evaluate_deployment
    def revoke_after_validation(*args, **kwargs):
        verdict = original(*args, **kwargs)
        state["authority"] = False
        return verdict
    monkeypatch.setattr(module, "evaluate_deployment", revoke_after_validation)
    c = SimulatedDeploymentController(POLICY, lambda _: GOOD, lambda _: state["authority"])
    assert not c.deploy(REQ).consequence_formed

def test_B03_post_validation_revocation_currently_allows_simulated_commit(monkeypatch):
    from app.engines import simulated_deployment_executor as module
    state = {"authority": True}
    original = module.evaluate_deployment
    def revoke_after_validation(*args, **kwargs):
        verdict = original(*args, **kwargs)
        state["authority"] = False
        return verdict
    monkeypatch.setattr(module, "evaluate_deployment", revoke_after_validation)
    c = SimulatedDeploymentController(POLICY, lambda _: GOOD, lambda _: state["authority"])
    assert c.deploy(REQ).consequence_formed is True

@pytest.mark.xfail(strict=True, reason="FS-MON-002-B04: policy and callback are constructor inputs, with no authenticated control-plane ownership")
def test_B04_untrusted_controller_cannot_replace_required_policy():
    forged_policy = MonitoringPolicy("agent-selected", frozenset({"agent-test-passed"}))
    forged_assessment = MonitoringAssessment(DIGEST, REQ.target, "agent-selected",
                                             frozenset({"agent-test-passed"}), True)
    c = SimulatedDeploymentController(forged_policy, lambda _: forged_assessment, lambda _: True)
    assert not c.deploy(REQ).consequence_formed

def test_B04_agent_supplied_policy_can_be_used_in_reference():
    forged_policy = MonitoringPolicy("agent-selected", frozenset({"agent-test-passed"}))
    forged_assessment = MonitoringAssessment(DIGEST, REQ.target, "agent-selected",
                                             frozenset({"agent-test-passed"}), True)
    c = SimulatedDeploymentController(forged_policy, lambda _: forged_assessment, lambda _: True)
    assert c.deploy(REQ).consequence_formed is True
