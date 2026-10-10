# TCS-001 — Coupled Capacity Challenge

## Frozen proposition

Two individually admissible movements share one governing capacity:

- shared capacity: `C = 10`
- movement A burden: `M_A = 6`
- movement B burden: `M_B = 6`
- combined burden: `M = M_A + M_B = 12`
- remaining capacity: `Phi = C - M = 10 - 12 = -2`

The proposition is frozen before running the challenge tests.

## Governing condition

For one shared authority-usage scope, the active aggregate burden MUST NOT
exceed the capacity:

`sum(active reservations) <= 10`

`RESERVED`, `CONSUMED`, and `QUARANTINED` reservations are active. A movement
that would make the aggregate burden exceed 10 MUST NOT obtain an execution
capability and MUST NOT form a protected consequence.

## Bounded test cases

1. **Sequential continuation** — A reserves and forms burden 6. B then attempts
   burden 6 in the same scope. B must be refused before protected-state change.
2. **Concurrent continuation** — A and B attempt burden 6 concurrently in the
   same scope. At most one may reserve capacity; the other must be refused.
3. **Combined movement** — one attempted movement of burden 12 against capacity
   10 must be refused.

## Falsification criteria

The challenge fails if any of the following occurs:

- both 6-unit movements obtain active reservations in the same scope;
- both movements obtain execution capabilities;
- both movements form protected consequences;
- a 12-unit combined movement obtains an execution capability; or
- active aggregate burden exceeds 10 at any observed boundary.

## Evidence boundary

This challenge evaluates the published bounded Python reference harness. It
does not establish production deployment, cross-process or distributed
serialisation, financial settlement, universal lawful formation, or any
physical or mathematical claim outside the executable artifact.

The first test output is to be preserved before remediation. Enforcement,
receipt, and replay results are reported separately; a thrown exception is not
to be described as a signed refusal receipt.
