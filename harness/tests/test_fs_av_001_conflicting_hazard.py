"""FS-AV-001: conflicting hazard and prohibited-zone continuation.

Boundary: deterministic decision/bind reference model only.  These tests do
not establish perception accuracy, trajectory-planner completeness, vehicle
dynamics, actuator enforcement, or safety of an autonomous vehicle.
"""

from dataclasses import replace

import pytest

from app.engines.autonomous_vehicle_boundary import (
    Trajectory,
    VehicleBoundaryRequest,
    determine_vehicle_continuation,
    reset_vehicle_boundary_state_for_test,
)


@pytest.fixture(autouse=True)
def _isolated_state():
    reset_vehicle_boundary_state_for_test()
    yield
    reset_vehicle_boundary_state_for_test()


def _request(execution_id: str = "FS-AV-001:BASE") -> VehicleBoundaryRequest:
    return VehicleBoundaryRequest(
        execution_id=execution_id,
        observed_at_ms=1_000,
        bind_at_ms=1_050,
        evidence_valid_until_ms=1_100,
        prohibited_zone_active=True,
        obstacle_present=True,
        trajectories=(
            Trajectory("STOP", False, 0),
            Trajectory("CROSS_ZONE", True, 0),
        ),
        requested_trajectory_id="STOP",
    )


def test_01_safe_stop_available_is_allowed_without_zone_entry():
    decision = determine_vehicle_continuation(_request("FS-AV-001:SAFE-STOP"))
    assert (decision.outcome, decision.reason_code, decision.trajectory_id) == (
        "ALLOW", "PERMITTED_MINIMUM_RISK_CONTINUATION", "STOP"
    )


def test_02_safe_permitted_alternative_is_selected_over_zone_crossing():
    req = replace(
        _request("FS-AV-001:ALTERNATIVE"),
        trajectories=(
            Trajectory("SAFE_LEFT", False, 0),
            Trajectory("CROSS_ZONE", True, 0),
        ),
        requested_trajectory_id="CROSS_ZONE",
    )
    decision = determine_vehicle_continuation(req)
    assert (decision.outcome, decision.reason_code) == (
        "REFUSE", "SAFER_PERMITTED_CONTINUATION_AVAILABLE"
    )


def test_03_only_collision_avoiding_path_requires_separate_emergency_authority():
    req = replace(
        _request("FS-AV-001:COMPETING-HARMS"),
        trajectories=(
            Trajectory("BRAKE", False, 9),
            Trajectory("CROSS_ZONE", True, 0),
        ),
        requested_trajectory_id="CROSS_ZONE",
    )
    decision = determine_vehicle_continuation(req)
    assert (decision.outcome, decision.reason_code) == (
        "ESCALATE", "COMPETING_HARMS_REQUIRE_EMERGENCY_AUTHORITY"
    )


def test_04_bounded_emergency_crossing_can_be_allowed_inside_frozen_risk_envelope():
    req = replace(
        _request("FS-AV-001:EMERGENCY-ALLOW"),
        trajectories=(
            Trajectory("BRAKE", False, 9),
            Trajectory("CROSS_ZONE", True, 0),
        ),
        requested_trajectory_id="CROSS_ZONE",
        emergency_crossing_authorized=True,
        emergency_max_collision_risk=0,
    )
    decision = determine_vehicle_continuation(req)
    assert (decision.outcome, decision.reason_code, decision.trajectory_id) == (
        "ALLOW", "BOUNDED_EMERGENCY_MINIMUM_RISK_CONTINUATION", "CROSS_ZONE"
    )


def test_05_stale_zone_and_hazard_evidence_cannot_authorize_movement():
    req = replace(
        _request("FS-AV-001:STALE"),
        bind_at_ms=1_101,
        requested_trajectory_id="CROSS_ZONE",
        emergency_crossing_authorized=True,
    )
    decision = determine_vehicle_continuation(req)
    assert (decision.outcome, decision.reason_code) == (
        "ESCALATE", "ROAD_EVIDENCE_STALE"
    )


def test_06_forged_emergency_without_obstacle_is_refused():
    req = replace(
        _request("FS-AV-001:FORGED-EMERGENCY"),
        obstacle_present=False,
        trajectories=(Trajectory("CROSS_ZONE", True, 0),),
        requested_trajectory_id="CROSS_ZONE",
        emergency_crossing_authorized=True,
    )
    decision = determine_vehicle_continuation(req)
    assert (decision.outcome, decision.reason_code) == (
        "REFUSE", "PROHIBITED_ZONE_NO_EMERGENCY"
    )


def test_07_last_moment_candidate_change_requires_new_bound_execution_identity():
    original = _request("FS-AV-001:MUTATION")
    first = determine_vehicle_continuation(original)
    mutated = replace(
        original,
        requested_trajectory_id="CROSS_ZONE",
        trajectories=(Trajectory("CROSS_ZONE", True, 0),),
        emergency_crossing_authorized=True,
    )
    second = determine_vehicle_continuation(mutated)
    assert first.outcome == "ALLOW"
    assert (second.outcome, second.reason_code) == (
        "REFUSE", "EXECUTION_ID_MUTATION"
    )


def test_08_exact_replay_returns_same_decision_without_new_authority():
    req = _request("FS-AV-001:REPLAY")
    first = determine_vehicle_continuation(req)
    replay = determine_vehicle_continuation(req)
    assert replay == first


def test_09_no_safe_continuation_is_not_misreported_as_safe_refusal():
    req = replace(
        _request("FS-AV-001:NO-SAFE-PATH"),
        prohibited_zone_active=False,
        trajectories=(Trajectory("BRAKE", False, 8),),
        requested_trajectory_id="BRAKE",
    )
    decision = determine_vehicle_continuation(req)
    assert (decision.outcome, decision.reason_code) == (
        "ESCALATE", "NO_SAFE_CONTINUATION_ESTABLISHED"
    )
