"""FS-MON-002 bounded single-process deployment consequence simulator.

Only this controller has a reference to the private simulated deployment store.
This is neither a real deployment system nor proof of unbypassable routing.
"""
from dataclasses import dataclass
from typing import Callable
from app.engines.deployment_monitoring_guard import (
    DeploymentRequest, MonitoringPolicy, MonitoringAssessment, DeploymentVerdict,
    evaluate_deployment,
)

@dataclass(frozen=True)
class DeploymentOutcome:
    decision: str
    reason_code: str
    consequence_formed: bool

class SimulatedDeploymentController:
    def __init__(self, trusted_policy: MonitoringPolicy,
                 independently_assess: Callable[[DeploymentRequest], MonitoringAssessment | None],
                 authority_check: Callable[[DeploymentRequest], bool]):
        self._policy = trusted_policy
        self._assess = independently_assess
        self._authority = authority_check
        self._deployed = {}

    def deploy(self, request: DeploymentRequest) -> DeploymentOutcome:
        verdict = evaluate_deployment(
            request, trusted_policy=self._policy,
            independently_assess=self._assess, authority_check=self._authority,
        )
        if verdict.decision != "ALLOW":
            return DeploymentOutcome(verdict.decision, verdict.reason_code, False)
        # Simulated consequence only after the guard permits.
        self._deployed[request.target] = request.artifact_digest
        return DeploymentOutcome("ALLOW", "SIMULATED_DEPLOYMENT_FORMED", True)

    def deployed_digest(self, target: str) -> str | None:
        return self._deployed.get(target)
