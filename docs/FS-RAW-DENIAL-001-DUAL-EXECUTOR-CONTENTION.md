# FS-RAW-DENIAL-001 — Multi-Client / Dual-Executor Contention Qualification

**Date:** 3 November 2026  
**Status:** Reference two-executor contention tests GREEN; production prevention **NOT ESTABLISHED**.

## Evidence

- Existing `main` baseline: `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0` (unchanged).
- First multiprocess contention branch: [PR #47](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/47). Initial run [41602250896](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41602250896) **2 failed** due to test wrapper import-time actuator validator override within source process. Not a consequence or authority enforcement defect.
- Role-isolation correction: [PR #48](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/48), [run 41602406811](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41602406811) **2 passed, 0 failed**. Eight separate client processes using two HTTP paths on one threaded actuator, source-owned SQLite serialisation, post-commit process crash and restart.
- Dual-executor candidate: [PR #49](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/49), [run 41602646931](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41602646931) **2 passed, 0 failed** in 2.06s.
- Existing verification baseline [run 41602646747](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41602646747) **success**.

## Dual-executor scenario 1: simultaneous attempts

Two separate threaded actuator HTTP server **processes**, sharing one separate threaded authority-source service and its local SQLite effect ledger, received **16 distinct Python client process** requests using a genuine reference RAI final-bind permit and bridge assertion.

Observed: **one** successful HTTP 200 outcome, **15** HTTP 409 replay refusals and **one** SQLite synthetic effect row whose signature and action binding match the permit.

## Dual-executor scenario 2: crash under contention and recovery

The source service terminates after the first successful local SQLite synthetic effect COMMIT while clients compete.

Observed: source process exit code 92, **one** surviving SQLite effect row. After source restart on the same loopback port, **16 independent client-process retries** across both still-running actuator processes each received HTTP 409 replay refusal. The SQLite effect ledger remained unchanged.

## What this supports

For a single source-owned reference SQLite database with uniqueness keyed by permit signature, transaction serialisation and replay refusal operate under the tested cross-process HTTP concurrency. An after-commit source process exit did not produce a duplicate reference consequence on restart/retry.

## Strict limitations

1. **Single-host, single-source DB only**: no cross-host shared storage, HA/replica failover, quorum, split-brain, network partition or multiple simultaneously writable source databases.
2. The outcome is **synthetic** and recorded in the same SQLite database that implements the reference authority commitment. There is no external payment, provider-owned outcome witness or distributed transaction.
3. The source service's upstream ownership remains unresolved: a revocation to FlowSignal's original in-process authority state that is not delivered to this service can still leave an old permit executable (earlier preserved RED).
4. Source/actuator test-token authentication and bridge HMAC are not qualified production identity, key custody, hardware isolation or operator separation.
5. No power-loss, damaged write-ahead log, disk rollback, restored snapshots, clock/epoch rollback or true network partitions were injected.
6. This does not prove every practical agent execution tool has been forced through the tested authority boundary.

**Next distinct gate:** multi-source conflict/rollback detection and external provider consequence witness, keeping the first REDs unchanged.

**Prevention: NOT ESTABLISHED. No changes to frozen main.**
