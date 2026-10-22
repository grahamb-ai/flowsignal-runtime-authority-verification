"""Compose B04 independently verified policy with B02 authenticated evidence."""
from app.engines.monitoring_policy_auth import verify_policy
from app.engines.monitoring_evidence_auth import verify_evidence

def verify_deployment_controls(request, policy, evidence, *,
    policy_key, evidence_key, expected_policy_id, minimum_policy_version,
    now, nonce_ledger):
    status = verify_policy(policy, policy_key, expected_id=expected_policy_id,
                           min_version=minimum_policy_version)
    if status != "VERIFIED":
        return ("REFUSE", status)
    evidence_status = verify_evidence(
        evidence, evidence_key, artifact_digest=request.artifact_digest,
        target=request.target, policy_id=policy.policy_id,
        required_controls=policy.required_controls,
        now=now, seen_nonces=nonce_ledger)
    if evidence_status != "VERIFIED":
        return ("REFUSE", evidence_status)
    return ("ALLOW", "REFERENCE_POLICY_AND_EVIDENCE_VERIFIED")
