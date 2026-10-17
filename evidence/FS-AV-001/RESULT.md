# FS-AV-001 — Result

Date: 2026-10-17

## Candidate result

Reference-model candidate: `9 passed in 0.04s`.

Reference model plus CARLA adapter contract: `13 passed in 0.04s`.

The candidate produced the following bounded behaviours:

1. safe stop: `ALLOW / PERMITTED_MINIMUM_RISK_CONTINUATION`;
2. zone crossing where a safe permitted alternative exists: `REFUSE`;
3. only collision-avoiding path crosses active boundary without separate
   emergency authority: `ESCALATE`;
4. bounded crossing with separate current emergency authority: `ALLOW`;
5. stale road/hazard evidence: `ESCALATE`;
6. claimed emergency with no obstacle: `REFUSE`;
7. changed trajectory under the same execution identity: `REFUSE`;
8. exact replay: identical recorded decision;
9. no established safe continuation: `ESCALATE`, not a false claim of safety.

## Adjacent-suite disclosure

Full suite with candidate and CARLA adapter: `129 passed, 27 failed`.

Full suite excluding candidate: `116 passed, 27 failed`.

The same 27 pre-existing order/state-contamination failures remain. FS-AV-001
and its adapter add thirteen passing tests and introduce no additional
full-suite failure. This does not close or conceal the existing suite-state
defect.

## CARLA status

The four adapter contract tests establish control mapping, fail-closed braking,
state capture and evidence-digest behaviour against an interface-equivalent
fake CARLA surface.

No live CARLA simulation was run: the CARLA Python package and server were not
available in the test environment. Therefore this result does not establish
vehicle dynamics, scenario completion, collision avoidance or construction-
zone non-entry in CARLA.

## Classification

GREEN WITHIN THE DECLARED DETERMINISTIC REFERENCE-MODEL AND ADAPTER-CONTRACT
BOUNDARIES.

SIMULATOR, PERCEPTION, PLANNER, ACTUATOR, VEHICLE-DYNAMICS AND FUNCTIONAL-
SAFETY VALIDATION REMAIN OPEN.
