# FS-RAW-DENIAL-001 — Authority Delivery / Freshness Qualification

**3 November 2026 | Reference scope only | Production prevention NOT ESTABLISHED**

## First RED — missing revocation delivery

The frozen public verification baseline was not modified.

- Challenge: [PR #34](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/34)
- [Original RED GitHub run 41595883071](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41595883071): **1 failed** (intended)
- Genuine FlowSignal RAI final-bind issued a permit and bridge assertion. Source authority version was advanced; publication to the separate localhost actuator was deliberately omitted.
- **Observed:** actuator HTTP 200, `CONSEQUENCE_FORMED`, independent SQLite effect row.
- **Required:** refuse an operation when source authority has changed. A matching local version alone does not establish source freshness.
- This is a reference integration failure, not an exploit against a production payment rail.

## Candidate and test-isolation evidence

- Lease candidate: [PR #35](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/35)
- Original candidate run **1 passed / 5 failed**, caused by aggregate-usage reservations leaking across test cases (setup failure, not an enforcement finding).
- Isolated test correction: [PR #36](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/36)
- [Verified run 41596271871](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41596271871): **6 passed**, 0 failed.
- [Existing baseline regression 41596271787](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41596271787): success.
- Tests examine current publication, expired publication, undelivered revocation after expiry, missing state, fresh but undelivered revocation, and delivered higher-version rejection.

## Crucial residual failure

The test `test_revocation_without_delivery_inside_lease_remains_a_gap` **passes because the old grant actually forms a synthetic consequence** before the publication lease expires.

That test is a *characterisation of a remaining gap*, not evidence of protection. The original immediate-refusal property in PR #34 is still **RED**.

## What the lease establishes

The separate actuator queries its locally published version and publication timestamp inside the same SQLite transaction as the represented effect write. If the publication is missing, future-dated, older than the bounded test lease, or at a different version from the permit, the operation is refused. This limits the maximum age of the actuator's last observed state, but does not prove its actual currency.

## What it does NOT establish

1. Immediate revocation protection during undelivered updates (the first RED still applies).
2. Authenticated, nonforgeable state delivery or ownership of the publisher.
3. A source-of-truth version that survives restart, rollback, multiple processes or regions.
4. Continuity during network partition: a still-valid lease could permit stale authority.
5. Clock integrity, synchronized time or tolerance to realistic skew.
6. Control-plane authentication, signed freshness attestations or key rotation.
7. Safe external payment finality or independent production consequence proof.

## Next research gate

Implement and hostile-test an authoritative online state service, or a source-owned monotonic fence that the real actuator can read or consume **atomically with consequence formation**. Test partitions, crash/restart, delayed and reordered updates, replay, clock skew, multiple executors, and unresolved outcome handling. Keep all RED evidence unchanged.

**Overall status: BOUNDED LEASE GREEN; IMMEDIATE REVOCATION / DELIVERY INTEGRITY OPEN. Prevention: NOT ESTABLISHED.**
