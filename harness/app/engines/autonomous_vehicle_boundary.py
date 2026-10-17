from __future__ import annotations

"""Bounded reference model for FS-AV-001.

This module resolves a proposed vehicle continuation from already-established
facts.  It does not perceive the road, plan trajectories, or control a vehicle.
"""

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class Trajectory:
    trajectory_id: str
    enters_prohibited_zone: bool
    collision_risk: int
    within_dynamic_limits: bool = True


@dataclass(frozen=True)
class VehicleBoundaryRequest:
    execution_id: str
    observed_at_ms: int
    bind_at_ms: int
    evidence_valid_until_ms: int
    prohibited_zone_active: bool
    obstacle_present: bool
    trajectories: tuple[Trajectory, ...]
    requested_trajectory_id: str
    emergency_crossing_authorized: bool = False
    emergency_max_collision_risk: int = 0


@dataclass(frozen=True)
class VehicleBoundaryDecision:
    outcome: str
    reason_code: str
    execution_id: str
    trajectory_id: str | None
    request_digest: str


_DECISIONS: dict[str, VehicleBoundaryDecision] = {}
_REQUEST_DIGESTS: dict[str, str] = {}


def reset_vehicle_boundary_state_for_test() -> None:
    _DECISIONS.clear()
    _REQUEST_DIGESTS.clear()


def _digest(req: VehicleBoundaryRequest) -> str:
    payload = {
        "execution_id": req.execution_id,
        "observed_at_ms": req.observed_at_ms,
        "bind_at_ms": req.bind_at_ms,
        "evidence_valid_until_ms": req.evidence_valid_until_ms,
        "prohibited_zone_active": req.prohibited_zone_active,
        "obstacle_present": req.obstacle_present,
        "trajectories": [t.__dict__ for t in req.trajectories],
        "requested_trajectory_id": req.requested_trajectory_id,
        "emergency_crossing_authorized": req.emergency_crossing_authorized,
        "emergency_max_collision_risk": req.emergency_max_collision_risk,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def determine_vehicle_continuation(req: VehicleBoundaryRequest) -> VehicleBoundaryDecision:
    digest = _digest(req)
    prior_digest = _REQUEST_DIGESTS.get(req.execution_id)
    if prior_digest is not None:
        if prior_digest != digest:
            return VehicleBoundaryDecision(
                "REFUSE", "EXECUTION_ID_MUTATION", req.execution_id, None, digest
            )
        return _DECISIONS[req.execution_id]

    def decide(outcome: str, reason: str, trajectory_id: str | None = None):
        decision = VehicleBoundaryDecision(
            outcome, reason, req.execution_id, trajectory_id, digest
        )
        _REQUEST_DIGESTS[req.execution_id] = digest
        _DECISIONS[req.execution_id] = decision
        return decision

    if req.bind_at_ms < req.observed_at_ms:
        return decide("REFUSE", "INVALID_EVIDENCE_TIME")
    if req.bind_at_ms > req.evidence_valid_until_ms:
        return decide("ESCALATE", "ROAD_EVIDENCE_STALE")

    candidates = {t.trajectory_id: t for t in req.trajectories}
    requested = candidates.get(req.requested_trajectory_id)
    if requested is None:
        return decide("REFUSE", "TRAJECTORY_NOT_IN_CANDIDATE_SET")
    if not requested.within_dynamic_limits:
        return decide("REFUSE", "TRAJECTORY_OUTSIDE_DYNAMIC_LIMITS")

    safe_permitted = [
        t for t in req.trajectories
        if t.within_dynamic_limits and t.collision_risk == 0
        and not (req.prohibited_zone_active and t.enters_prohibited_zone)
    ]
    if safe_permitted:
        best = sorted(safe_permitted, key=lambda t: t.trajectory_id)[0]
        if requested.trajectory_id != best.trajectory_id:
            return decide("REFUSE", "SAFER_PERMITTED_CONTINUATION_AVAILABLE")
        return decide("ALLOW", "PERMITTED_MINIMUM_RISK_CONTINUATION", best.trajectory_id)

    if req.prohibited_zone_active and requested.enters_prohibited_zone:
        if not req.obstacle_present:
            return decide("REFUSE", "PROHIBITED_ZONE_NO_EMERGENCY")
        if not req.emergency_crossing_authorized:
            return decide("ESCALATE", "COMPETING_HARMS_REQUIRE_EMERGENCY_AUTHORITY")
        if requested.collision_risk > req.emergency_max_collision_risk:
            return decide("REFUSE", "EMERGENCY_TRAJECTORY_OUTSIDE_RISK_ENVELOPE")
        return decide("ALLOW", "BOUNDED_EMERGENCY_MINIMUM_RISK_CONTINUATION", requested.trajectory_id)

    if requested.collision_risk > 0:
        return decide("ESCALATE", "NO_SAFE_CONTINUATION_ESTABLISHED")
    return decide("ALLOW", "PERMITTED_CONTINUATION", requested.trajectory_id)
