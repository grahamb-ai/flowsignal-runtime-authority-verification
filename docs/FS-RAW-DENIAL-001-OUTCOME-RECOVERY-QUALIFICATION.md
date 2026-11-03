# FS-RAW-DENIAL-001 — Crash / Lost-Acknowledgement Recovery Qualification

**3 November 2026 | Reference simulation only | Prevention NOT ESTABLISHED**

## Baseline and evidence

Frozen main baseline: `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`, not modified.

- Initial challenge [PR #40](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/40), [run 41599222141](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41599222141): **1 passed, 1 intentional RED**. Source-owned SQLite consequence formed; HTTP acknowledgement deliberately dropped; forwarding actuator reported `COMMIT_OUTCOME_UNRESOLVED`. Authenticated outcome lookup returned HTTP 404 `UNKNOWN_PATH`.
- Recovery candidate [PR #41](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/41): adds a read-token-gated source-ledger outcome endpoint and tests receipt match, missing record, replay and service restart.
- Test isolation [PR #42](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/42): test-only aggregate authority reservation reset after candidate showed setup failures; first fix gave six passes and one restart fault-injection failure.
- Restart fault scope correction [PR #43](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/43): restart no longer deliberately drops a second successful acknowledgement. No authority or consequence enforcement logic changed.
- [Final candidate run 41599831301](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41599831301): **7 passed, 0 failed**.
- [Baseline regression run 41599831802](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41599831802): **success**.

## Verified within scope

The authority-source service owns a synthetic consequence in its local SQLite transaction ledger. The initial HTTP response may be lost while a durable row has already been committed. The forwarding actuator treats the transport error as `COMMIT_OUTCOME_UNRESOLVED` with `formed=None`, not as `REFUSED` or proof of non-formation.

A separately authenticated `GET /outcome?signature=...` query returns the matching committed action binding and route. Unauthenticated readers receive HTTP 403. Missing reference rows return `OUTCOME_NOT_RECORDED` with `formed=None`; these are NOT proof of absence of external consequences. Reuse of the same grant on another actuator route returns `REPLAY_REFUSED`, with no extra SQLite effect row. The original recorded outcome survives restart of the authority source using its persistent test database, and replay remains refused.

## Critical limitations

1. This is **simulation of a dropped HTTP acknowledgement** after a local SQLite commit, not a full injected process kill at every failure point. Unexpected power loss, WAL durability, fsync, restored database snapshots and split-brain are untested.
2. The source service owns both authority and the **synthetic** effect record. No independent payment processor, external payment settlement, third-party witness or real-world irreversible side effect was involved.
3. The outcome endpoint uses test-only header credentials and a query by permit signature, not production-grade IAM/mTLS, segregated read permissions, threat model or audit custody.
4. A missing local record remains **UNKNOWN**, never a proven `NOT_FORMED` outcome.
5. A retry is rejected as replay; this is evidence against duplicate *local* commits, not downstream exactly-once payment settlement.
6. The upstream authority ownership/publication gap remains unresolved. The authenticated test bridge and in-process RAI provenance do not establish production source authenticity or cross-host issuer competence.
7. The fault-injection paths are explicit; no evidence that all arbitrary process crashes, reordered calls, cross-host concurrency or all alternate external execution routes are covered.

## Distinct next gate

Test a true interruption **before and after the local commit** with process kill/restart and independently recorded outcome. Then test concurrent retry clients, recovery of `OUTCOME_UNRESOLVED` after crash, source-ledger rollback, and external actuator acknowledgement uncertainty. Preserve first REDs and do not merge frozen baseline.

**Disposition: REFERENCE RECOVERY CANDIDATE GREEN; PRODUCTION PREVENTION NOT ESTABLISHED.**
