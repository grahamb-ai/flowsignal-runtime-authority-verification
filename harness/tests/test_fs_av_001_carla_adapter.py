from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.engines.autonomous_vehicle_boundary import (
    Trajectory,
    VehicleBoundaryRequest,
    reset_vehicle_boundary_state_for_test,
)
from app.engines.carla_vehicle_boundary import CarlaVehicleBoundaryAdapter, ProposedControl


class FakeVehicle:
    id = 42

    def __init__(self):
        self.controls = []

    def get_transform(self):
        return SimpleNamespace(location=SimpleNamespace(x=1.0, y=2.0, z=3.0))

    def get_velocity(self):
        return SimpleNamespace(x=4.0, y=0.0, z=0.0)

    def apply_control(self, control):
        self.controls.append(control)


class FakeWorld:
    def get_snapshot(self):
        return SimpleNamespace(
            frame=101,
            timestamp=SimpleNamespace(elapsed_seconds=5.05),
        )


def control_factory(**kwargs):
    return SimpleNamespace(**kwargs)


@pytest.fixture(autouse=True)
def _state():
    reset_vehicle_boundary_state_for_test()
    yield
    reset_vehicle_boundary_state_for_test()


def _request(execution_id="FS-AV-001-CARLA:BASE"):
    return VehicleBoundaryRequest(
        execution_id=execution_id,
        observed_at_ms=5_000,
        bind_at_ms=5_050,
        evidence_valid_until_ms=5_100,
        prohibited_zone_active=True,
        obstacle_present=True,
        trajectories=(Trajectory("STOP", False, 0),),
        requested_trajectory_id="STOP",
    )


def _adapter():
    vehicle = FakeVehicle()
    return CarlaVehicleBoundaryAdapter(
        world=FakeWorld(), vehicle=vehicle, control_factory=control_factory
    ), vehicle


def test_allow_applies_only_the_bound_proposed_control_and_records_carla_state():
    adapter, vehicle = _adapter()
    evidence = adapter.bind_and_apply(
        _request("FS-AV-001-CARLA:ALLOW"),
        ProposedControl(0.25, -0.1, 0.0),
    )
    assert evidence.decision.outcome == "ALLOW"
    assert evidence.carla_frame == 101
    assert evidence.location == (1.0, 2.0, 3.0)
    assert vehicle.controls[0].throttle == 0.25
    assert vehicle.controls[0].brake == 0.0
    assert len(evidence.evidence_digest) == 64


@pytest.mark.parametrize("outcome_case", ["REFUSE", "ESCALATE"])
def test_non_allow_fails_closed_at_carla_actuator_adapter(outcome_case):
    adapter, vehicle = _adapter()
    if outcome_case == "REFUSE":
        req = replace(
            _request("FS-AV-001-CARLA:REFUSE"),
            trajectories=(Trajectory("CROSS_ZONE", True, 0),),
            requested_trajectory_id="CROSS_ZONE",
            obstacle_present=False,
        )
    else:
        req = replace(
            _request("FS-AV-001-CARLA:ESCALATE"),
            bind_at_ms=5_101,
        )
    evidence = adapter.bind_and_apply(req, ProposedControl(1.0, 0.8, 0.0))
    assert evidence.decision.outcome == outcome_case
    assert vehicle.controls[0].throttle == 0.0
    assert vehicle.controls[0].steer == 0.0
    assert vehicle.controls[0].brake == 1.0


def test_out_of_range_control_is_clamped_before_carla_application():
    adapter, vehicle = _adapter()
    adapter.bind_and_apply(
        _request("FS-AV-001-CARLA:CLAMP"),
        ProposedControl(2.0, -4.0, -1.0),
    )
    assert vehicle.controls[0].throttle == 1.0
    assert vehicle.controls[0].steer == -1.0
    assert vehicle.controls[0].brake == 0.0
