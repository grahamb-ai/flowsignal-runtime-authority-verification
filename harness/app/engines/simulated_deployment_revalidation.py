"""FS-MON-002 B03 candidate: final revalidation for simulated deployment only.

The callback must be backed by independent authoritative state. This does not
establish external atomicity, durable execution, or protection from bypass.
"""
from dataclasses import dataclass
from typing import Callable
from app.engines.deployment_monitoring_guard import (
    DeploymentRequest, MonitoringPolicy, MonitoringAssessment, evaluate_deployment
)

@dataclass(frozen=True)
class CommitOutcome:
    decision: str
    reason_code: str
    formed: bool

class RevalidatedSimulatedController:
    def __init__(self, policy: MonitoringPolicy,
                 assess: Callable[[DeploymentRequest], MonitoringAssessment | None],
                 authority: Callable[[DeploymentRequest], bool]):
        self._policy = policy
        self._assess = assess
        self._authority = authority
        self._deployed = {}

    def deploy(self, request: DeploymentRequest,
               *, before_commit: Callable[[], None] | None = None) -> CommitOutcome:
        first = evaluate_deployment(
            request, trusted_policy=self._policy,
            independently_assess=self._assess, authority_check=self._authority)
        if first.decision != "ALLOW":
            return CommitOutcome("REFUSE", first.reason_code, False)
        if before_commit is not None:
            try:
                before_commit()
            except Exception:
                return CommitOutcome("REFUSE", "PRECOMMIT_INTERRUPTED", False)
        second = evaluate_deployment(
            request, trusted_policy=self._policy,
            independently_assess=self._assess, authority_check=self._authority)
        if second.decision != "ALLOW":
            return CommitOutcome("REFUSE", "FINAL_REVALIDATION_" + second.reason_code, False)
        self._deployed[request.target] = request.artifact_digest
        return CommitOutcome("ALLOW", "SIMULATED_COMMIT_FORMED", True)

    def deployed_digest(self, target: str):
        return self._deployed.get(target)
