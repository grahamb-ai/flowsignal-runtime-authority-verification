# FS-RAW-DENIAL-001 — Independent Client Contention and Process Exit

**3 November 2026. Reference-only synthetic consequence. Production prevention NOT ESTABLISHED.**

## Verified run

- Draft challenge: [PR #45](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/45)
- [GitHub Actions 41601635940](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41601635940) — 3 passed in 1.10s
- [Baseline regression 41601635687](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41601635687) — success
- Frozen main commit: `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`, unchanged

## Exactly what was exercised

A genuine RAI final-bind permit and its signed bridge assertion were generated in the test harness. Eight distinct child Python processes were started and released using a shared test gate. Each made a direct HTTP request to the **source-owned /commit endpoint**, with alternating `/execute-a` and `/execute-b` **route labels**. They did **not** traverse two separate deployed actuator services. The source uses ThreadingHTTPServer in the normal contention case, allowing overlapping request handling. Each client had an independent result file.

The final SQLite consequence ledger, independently read by the parent process, contained one entry. One HTTP response was successful (200) and seven were rejected as duplicate (409).

Two further tests started four client processes each against the previously qualified crash-injected source. That server is serial in its request handling; the source exited before or after the first effect COMMIT. After recovery and another four child-process retries, the final local ledger contained one entry. No duplicate synthetic effect formed.

The caller cannot infer formation solely from a dropped connection. An unacknowledged/failed transport is classified as `COMMIT_OUTCOME_UNRESOLVED` by the client helper, not as a proven refusal.

## Qualification boundaries

1. A single local SQLite file is both authoritative version store and **synthetic effect ledger**; this is not external payment idempotency or independent settlement evidence.
2. Normal contention covers multiple clients, but **one source service and one database**, not competing source hosts or database replicas.
3. Route A and B were **values submitted to the source endpoint**, not independently hosted actuator entrypoints. Direct server-side commit authentication was satisfied by shared test credentials, not production IAM.
4. Crash tests had multiple client processes but a **serial** HTTP source, and therefore do not demonstrate true multi-writer contention at the crash instant.
5. No real agent, encoded shell command, genuine external consequence, network partition, storage rollback, distributed consensus or power-loss durability was tested.
6. Earlier undelivered authority changes upstream of the source service remain an unresolved safety gap. The bridge issuer and source state owner are still test assumptions.
7. The result establishes at most one reference-ledger row for the same permit signature under the specified conditions, **not** a universal exactly-once guarantee.

## Next distinct test

Use two independent actuator processes with their own routes and credentials, invoke them from competing client processes, and verify that both rely on one externally controlled consequence boundary. Then inject source or actuator process failure mid-contention and test state rollback and reconciliation using an independently owned outcome witness.

**Disposition:** MULTI-CLIENT LOCAL SOURCE CONTENTION GREEN; REAL MULTI-ACTUATOR / EXTERNAL SETTLEMENT OPEN. Prevention NOT ESTABLISHED.
