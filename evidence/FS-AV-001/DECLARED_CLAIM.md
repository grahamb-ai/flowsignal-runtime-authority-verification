# FS-AV-001 — Declared Claim

## Frozen proposition

Within this bounded deterministic reference model, a proposed autonomous-
vehicle continuation must not cross an active prohibited boundary merely
because the trajectory is executable.

Where a safe permitted continuation exists, it must be preferred. Where the
only collision-avoiding continuation crosses the prohibited boundary, the
system must not silently allow or categorically refuse it: separate current
emergency authority and a frozen risk envelope are required. Stale evidence,
changed trajectories under the same execution identity, and unsupported
emergency claims must not authorize movement.

## Tested outcomes

The candidate exercises safe stop, safe alternative, competing harms,
emergency crossing, stale evidence, unsupported emergency, bind-time mutation,
exact replay, and absence of any established safe continuation.

## Explicit non-claims

FS-AV-001 does not establish:

- road or obstacle perception accuracy;
- completeness or optimality of trajectory generation;
- real vehicle dynamics or actuator enforcement;
- integration with Waymo or any autonomous-driving system;
- functional-safety certification or fitness for public-road deployment.

It tests only deterministic decision and binding behaviour over frozen inputs.
