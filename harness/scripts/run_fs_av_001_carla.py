#!/usr/bin/env python3
from __future__ import annotations

"""Run one frozen FS-AV-001 bind against an existing CARLA ego actor.

CARLA must already be running. The caller supplies the ego actor id and frozen
request JSON; this script does not claim to perceive or generate trajectories.
"""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from app.engines.autonomous_vehicle_boundary import Trajectory, VehicleBoundaryRequest
from app.engines.carla_vehicle_boundary import CarlaVehicleBoundaryAdapter, ProposedControl


def _request(payload: dict) -> VehicleBoundaryRequest:
    return VehicleBoundaryRequest(
        execution_id=payload["execution_id"],
        observed_at_ms=int(payload["observed_at_ms"]),
        bind_at_ms=int(payload["bind_at_ms"]),
        evidence_valid_until_ms=int(payload["evidence_valid_until_ms"]),
        prohibited_zone_active=bool(payload["prohibited_zone_active"]),
        obstacle_present=bool(payload["obstacle_present"]),
        trajectories=tuple(Trajectory(**item) for item in payload["trajectories"]),
        requested_trajectory_id=payload["requested_trajectory_id"],
        emergency_crossing_authorized=bool(payload.get("emergency_crossing_authorized", False)),
        emergency_max_collision_risk=int(payload.get("emergency_max_collision_risk", 0)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--actor-id", type=int, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--throttle", type=float, default=0.0)
    parser.add_argument("--steer", type=float, default=0.0)
    parser.add_argument("--brake", type=float, default=1.0)
    args = parser.parse_args()

    import carla  # Optional runtime dependency supplied by a CARLA installation.

    client = carla.Client(args.host, args.port)
    client.set_timeout(10.0)
    world = client.get_world()
    original_settings = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.05
    world.apply_settings(settings)
    try:
        vehicle = world.get_actor(args.actor_id)
        if vehicle is None:
            raise RuntimeError(f"CARLA actor {args.actor_id} not found")
        world.tick()
        payload = json.loads(args.request.read_text(encoding="utf-8"))
        adapter = CarlaVehicleBoundaryAdapter(
            world=world,
            vehicle=vehicle,
            control_factory=carla.VehicleControl,
        )
        evidence = adapter.bind_and_apply(
            _request(payload),
            ProposedControl(args.throttle, args.steer, args.brake),
        )
        world.tick()
        args.output.write_text(
            json.dumps(asdict(evidence), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0
    finally:
        world.apply_settings(original_settings)


if __name__ == "__main__":
    raise SystemExit(main())
