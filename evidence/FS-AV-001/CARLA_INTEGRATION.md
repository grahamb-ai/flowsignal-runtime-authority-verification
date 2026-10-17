# FS-AV-001 — CARLA Integration Boundary

The optional CARLA adapter connects an FS-AV-001 decision to an existing CARLA
ego actor in synchronous mode. On `ALLOW`, it applies the bound proposed
`VehicleControl`. On `REFUSE` or `ESCALATE`, it fails closed at the adapter by
applying full braking and zero throttle/steer.

The adapter records the CARLA frame, elapsed simulation time, actor identity,
location, velocity, decision, applied control and a SHA-256 evidence digest.

## Live invocation

With a CARLA server running and its Python API on `PYTHONPATH`:

```bash
cd harness
PYTHONPATH=. python scripts/run_fs_av_001_carla.py \
  --actor-id <ego-actor-id> \
  --request <frozen-request.json> \
  --output <evidence.json> \
  --throttle 0.25 --steer 0.0 --brake 0.0
```

The runner enables a 0.05-second synchronous fixed timestep and restores the
original world settings before exit.

## Current evidence status

The adapter contract is testable without CARLA by an interface-equivalent fake.
Those four contract tests passed on 2026-10-17. The CARLA Python package was not
available in the test environment, so no live simulator execution occurred.
A contract-test result is not a CARLA simulation result.

A live result may be claimed only after running the script against a pinned
CARLA build, map, actor, frozen scenario and simulator seed, then preserving
the produced JSON and CARLA recorder output. The current runner binds an
already-computed decision to vehicle control; it does not implement or validate
perception, trajectory generation, vehicle dynamics or collision avoidance.
