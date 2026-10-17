from __future__ import annotations

"""CARLA-facing adapter for FS-AV-001.

The adapter intentionally depends on a small structural interface so its trust
boundary can be contract-tested without claiming that a CARLA server ran.
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Callable

from app.engines.autonomous_vehicle_boundary import (
    VehicleBoundaryDecision,
    VehicleBoundaryRequest,
    determine_vehicle_continuation,
)


@dataclass(frozen=True)
class ProposedControl:
    throttle: float
    steer: float
    brake: float
    hand_brake: bool = False
    reverse: bool = False


@dataclass(frozen=True)
class CarlaBoundaryEvidence:
    carla_frame: int
    carla_elapsed_seconds: float
    actor_id: int
    location: tuple[float, float, float]
    velocity: tuple[float, float, float]
    decision: VehicleBoundaryDecision
    applied_control: ProposedControl
    evidence_digest: str


def _bounded(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _safe_control(control: ProposedControl) -> ProposedControl:
    return ProposedControl(
        throttle=_bounded(control.throttle, 0.0, 1.0),
        steer=_bounded(control.steer, -1.0, 1.0),
        brake=_bounded(control.brake, 0.0, 1.0),
        hand_brake=bool(control.hand_brake),
        reverse=bool(control.reverse),
    )


class CarlaVehicleBoundaryAdapter:
    def __init__(
        self,
        *,
        world: Any,
        vehicle: Any,
        control_factory: Callable[..., Any],
    ) -> None:
        self.world = world
        self.vehicle = vehicle
        self.control_factory = control_factory

    def bind_and_apply(
        self,
        request: VehicleBoundaryRequest,
        proposed_control: ProposedControl,
    ) -> CarlaBoundaryEvidence:
        snapshot = self.world.get_snapshot()
        transform = self.vehicle.get_transform()
        velocity = self.vehicle.get_velocity()
        decision = determine_vehicle_continuation(request)

        if decision.outcome == "ALLOW":
            applied = _safe_control(proposed_control)
        else:
            # REFUSE and ESCALATE both fail closed at the actuator adapter.
            applied = ProposedControl(0.0, 0.0, 1.0, hand_brake=False)

        self.vehicle.apply_control(self.control_factory(**asdict(applied)))

        payload = {
            "carla_frame": int(snapshot.frame),
            "carla_elapsed_seconds": float(snapshot.timestamp.elapsed_seconds),
            "actor_id": int(self.vehicle.id),
            "location": [
                float(transform.location.x),
                float(transform.location.y),
                float(transform.location.z),
            ],
            "velocity": [float(velocity.x), float(velocity.y), float(velocity.z)],
            "decision": asdict(decision),
            "applied_control": asdict(applied),
        }
        digest = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CarlaBoundaryEvidence(
            carla_frame=payload["carla_frame"],
            carla_elapsed_seconds=payload["carla_elapsed_seconds"],
            actor_id=payload["actor_id"],
            location=tuple(payload["location"]),
            velocity=tuple(payload["velocity"]),
            decision=decision,
            applied_control=applied,
            evidence_digest=digest,
        )
