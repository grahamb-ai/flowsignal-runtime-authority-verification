# FS-RAW-DENIAL-001 — Two-Actuator Contention Qualification

**3 November 2026 | Reference only | Production prevention NOT ESTABLISHED**

## Pinned evidence

- Draft [PR #45](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/45): direct source-owned commit contention from independent client processes. [Run 41601635940](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41601635940): **3 passed**.
- Draft [PR #46](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/46): actual two-actuator process contention. [Run 41601961822](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41601961822): **2 passed**, 0 failed, 0.72s.
- Existing [public baseline regression 41601961598](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41601961598): success.
- Frozen `main` baseline unchanged at `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.

## Actual test architecture

The test starts a threaded local HTTP source service with one source-owned SQLite authority/version and synthetic consequence ledger. It also starts two different OS processes, each running the reference forwarding actuator on a **different localhost port**. Eight additional OS client processes are released on a common test gate. Four clients call actuator 1 route `/execute-a`; four clients call actuator 2 route `/execute-b`.

All eight use one genuine RAI final-bind permit and a signed reference bridge assertion generated through the existing FlowSignal harness. Each actuator verifies authority and forwards to the source's atomic commit endpoint. The source's final local SQLite transaction checks the current version and inserts the synthetic effect, using the permit signature as the unique key.

Observed: exactly one successful HTTP commit, seven replay refusals, and exactly one independently queried SQLite effect row matching the original permit signature and action binding.

A separate second test first forms the synthetic consequence through actuator 1, terminates actuator 1, then sends the same permit through actuator 2. Actuator 2 receives `REPLAY_REFUSED` and the source ledger remains unchanged.

## Limits

1. Two independent actuator **processes** were exercised, but both depend on a single **local** source process and SQLite database—not separate source hosts, replicated databases or independently controlled external effectors.
2. The effect is a synthetic ledger entry inside the source's SQLite transaction, **not** a third-party payment commit. Independent verification consists of a separate test reader of that same ledger.
3. Trust assumptions include synthetic shared test keys and a source-owned bridge verifier. No production identity, secret isolation, mTLS, IAM, third-party evidence custody or payment-rail authorization.
4. Simultaneous requests were scheduled by a common gate, but exact host scheduling and relative arrival order are not fully controlled. Test success demonstrates the observed contention run only.
5. Actuator termination occurs **after** the first successful commit, not during an indeterminate network/commit interval. Concurrent process crashes, distributed leader failover and rollback are not qualified.
6. Source authority ownership upstream and undelivered authority changes remain a preserved open failure. Universal alternative-route closure is not demonstrated.

## Next qualification

Test source rollback and restored snapshot under a surviving external checkpoint; run independently hosted source replicas and loss/reordering of authority updates; then connect an external provider-owned sandbox consequence witness. Until that point, avoid claims about exactly-once financial settlement or guaranteed revocation.

**Disposition: TWO-ACTUATOR LOCAL REFERENCE CONTENTION GREEN. Production prevention NOT ESTABLISHED.**
