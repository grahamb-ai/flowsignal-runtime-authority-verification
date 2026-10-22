"""FS-MON-002 remediation candidate tests; no production deployment exercised."""
from dataclasses import replace
import pytest
from app.engines.deployment_monitoring_guard import (
    DeploymentRequest, MonitoringPolicy, MonitoringAssessment, evaluate_deployment
)

D = "a" * 64
POLICY = MonitoringPolicy("immutable-policy-v1", frozenset({"security-alerts", "audit-events"}))
REQUEST = DeploymentRequest("migration-agent", D, "service:example", "receipt-1")
OK = MonitoringAssessment(D, "service:example", "immutable-policy-v1",
                          frozenset({"security-alerts", "audit-events"}), True)

def decide(assessment=OK, *, policy=POLICY, request=REQUEST, authority=True):
    return evaluate_deployment(
        request, trusted_policy=policy, independently_assess=lambda _: assessment,
        authority_check=lambda _: authority
    )

def test_valid_independently_assessed_migration_allowed():
    assert decide().decision == "ALLOW"

@pytest.mark.parametrize("missing", ["security-alerts", "audit-events"])
def test_missing_mandatory_monitoring_refused(missing):
    altered = replace(OK, present_controls=OK.present_controls - {missing})
    assert decide(altered).reason_code == "MANDATORY_MONITORING_ABSENT"

def test_agent_modified_regression_test_cannot_replace_independent_assessment():
    # A changed agent-owned regression expectation is not an input to the guard.
    agent_test_says_pass = True
    assert agent_test_says_pass
    assert decide(replace(OK, present_controls=frozenset())).decision == "REFUSE"

def test_agent_claim_monitoring_intact_not_evidence():
    claimed_controls = {"security-alerts", "audit-events"}
    assert claimed_controls
    assert decide(None).reason_code == "MONITORING_ATTESTATION_MISSING_OR_FAILED"

def test_subagent_or_untrusted_policy_change_cannot_waive_controls():
    # Separately trusted policy remains required regardless of what agent asserts.
    agent_claimed_policy = MonitoringPolicy("agent-policy", frozenset())
    assert agent_claimed_policy.required_controls == frozenset()
    assert decide(replace(OK, present_controls=frozenset())).decision == "REFUSE"

def test_artifact_substitution_refused():
    assert decide(request=replace(REQUEST, artifact_digest="b" * 64)).reason_code == "MONITORING_ATTESTATION_BINDING_MISMATCH"

def test_target_substitution_refused():
    assert decide(request=replace(REQUEST, target="service:other")).reason_code == "MONITORING_ATTESTATION_BINDING_MISMATCH"

def test_policy_version_substitution_refused():
    assert decide(replace(OK, policy_id="old-policy")).reason_code == "MONITORING_ATTESTATION_BINDING_MISMATCH"

def test_unverified_authority_refused():
    assert decide(authority=False).reason_code == "DEPLOYMENT_AUTHORITY_NOT_ESTABLISHED"

def test_missing_policy_refused():
    assert decide(policy=MonitoringPolicy("", frozenset())).reason_code == "MONITORING_POLICY_MISSING"

def test_failed_assessment_refused():
    assert decide(replace(OK, assessment_ok=False)).decision == "REFUSE"

def test_assessor_exception_fails_closed():
    def unavailable(_): raise RuntimeError("outage")
    verdict = evaluate_deployment(REQUEST, trusted_policy=POLICY,
        independently_assess=unavailable, authority_check=lambda _: True)
    assert verdict.reason_code == "MONITORING_ASSESSMENT_UNAVAILABLE"

def test_authority_checker_exception_fails_closed():
    def unavailable(_): raise RuntimeError("outage")
    verdict = evaluate_deployment(REQUEST, trusted_policy=POLICY,
        independently_assess=lambda _: OK, authority_check=unavailable)
    assert verdict.reason_code == "AUTHORITY_CHECK_UNAVAILABLE"
