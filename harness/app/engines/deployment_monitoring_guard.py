"""FS-MON-002 candidate adapter. NOT a production consequence gateway.

Policy and assessment must originate outside the executing agent's control.
An unsigned attestation object is deliberately NOT trusted merely by possession:
the caller must supply an independently controlled assessment function.
"""
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class DeploymentRequest:
    actor_id: str
    artifact_digest: str
    target: str
    authority_receipt_id: str

@dataclass(frozen=True)
class MonitoringPolicy:
    policy_id: str
    required_controls: frozenset[str]

@dataclass(frozen=True)
class MonitoringAssessment:
    artifact_digest: str
    target: str
    policy_id: str
    present_controls: frozenset[str]
    assessment_ok: bool

@dataclass(frozen=True)
class DeploymentVerdict:
    decision: str
    reason_code: str

def evaluate_deployment(
    request: DeploymentRequest,
    *,
    trusted_policy: MonitoringPolicy,
    independently_assess: Callable[[DeploymentRequest], MonitoringAssessment | None],
    authority_check: Callable[[DeploymentRequest], bool],
) -> DeploymentVerdict:
    """Reference composition gate: the caller MUST enforce this at deployment.

    TRUST ASSUMPTION: policy, assessment callback and authority-check callback
    are supplied by a trusted deployment controller, not the coding agent.
    This code cannot itself attest integrity of evidence, isolate the controller,
    or prevent use of a deployment path that does not call this function.
    """
    if not request.actor_id or not request.target or not request.authority_receipt_id:
        return DeploymentVerdict("REFUSE", "DEPLOYMENT_IDENTITY_OR_TARGET_MISSING")
    if len(request.artifact_digest) != 64 or any(ch not in "0123456789abcdef" for ch in request.artifact_digest):
        return DeploymentVerdict("REFUSE", "DEPLOYMENT_ARTIFACT_DIGEST_INVALID")
    if not trusted_policy.policy_id or not trusted_policy.required_controls:
        return DeploymentVerdict("REFUSE", "MONITORING_POLICY_MISSING")
    try:
        assessment = independently_assess(request)
    except Exception:
        return DeploymentVerdict("REFUSE", "MONITORING_ASSESSMENT_UNAVAILABLE")
    if assessment is None or not assessment.assessment_ok:
        return DeploymentVerdict("REFUSE", "MONITORING_ATTESTATION_MISSING_OR_FAILED")
    if (assessment.artifact_digest != request.artifact_digest or
        assessment.target != request.target or
        assessment.policy_id != trusted_policy.policy_id):
        return DeploymentVerdict("REFUSE", "MONITORING_ATTESTATION_BINDING_MISMATCH")
    if not trusted_policy.required_controls.issubset(assessment.present_controls):
        return DeploymentVerdict("REFUSE", "MANDATORY_MONITORING_ABSENT")
    try:
        authorised = authority_check(request)
    except Exception:
        return DeploymentVerdict("REFUSE", "AUTHORITY_CHECK_UNAVAILABLE")
    if not authorised:
        return DeploymentVerdict("REFUSE", "DEPLOYMENT_AUTHORITY_NOT_ESTABLISHED")
    return DeploymentVerdict("ALLOW", "DEPLOYMENT_PRECONDITIONS_SATISFIED")
