"""B02: adapt verified evidence to the existing monitoring guard.

The verifying key and nonce ledger must be owned by a separate trusted
controller. This composition is reference-only and not durable or atomic.
"""
from app.engines.monitoring_evidence_auth import verify_evidence
from app.engines.deployment_monitoring_guard import MonitoringAssessment, evaluate_deployment

def evaluate_authenticated_deployment(request, *, policy, evidence, verification_key,
                                      authority_check, now, seen_nonces):
    status=verify_evidence(evidence,verification_key,
        artifact_digest=request.artifact_digest,target=request.target,
        policy_id=policy.policy_id,required_controls=policy.required_controls,
        now=now,seen_nonces=seen_nonces)
    if status!="VERIFIED":
        return ("REFUSE",status)
    assessment=MonitoringAssessment(
        request.artifact_digest,request.target,policy.policy_id,
        frozenset(evidence.required_controls),True)
    result=evaluate_deployment(request,trusted_policy=policy,
        independently_assess=lambda _: assessment,authority_check=authority_check)
    return (result.decision,result.reason_code)
