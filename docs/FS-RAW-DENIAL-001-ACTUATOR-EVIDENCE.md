# FS-RAW-DENIAL-001 — Isolated Actuator Evidence (3 November 2026)

**Status: Reference candidate GREEN; production route closure NOT ESTABLISHED**

## Evidence chains

- Existing frozen main commit: `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.
- First RED branch: `challenge/fs-raw-denial-001-sandbox-actuator-first-red`, draft PR #29.
- First RED run: [41593056292](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41593056292) — **3 passed, 1 failed**. Deliberately unprotected local HTTP `/direct` route formed a synthetic SQLite effect despite the unrelated gateway refusal.
- Candidate branch: `candidate/fs-raw-denial-001-actuator-grant-gate`, draft PR #30.
- Candidate run: [41593277393](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41593277393) — **8 passed**.
- Baseline regression run: [41593277251](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41593277251) — succeeded.

## What the candidate actually shows

A dedicated loopback HTTP server in a separate local process records successful synthetic effects to a separate SQLite store. Both `/guarded` and `/direct` now require an HMAC-authenticated, unexpired, action/target-bound, one-use synthetic grant. The test process queries the actuator's database to verify outcomes rather than relying only on HTTP status.

A missing grant, wrong signer, changed target, expired grant, unknown route and second use of one grant are refused under the tested conditions. Valid test-issued grants form the represented synthetic consequence exactly once.

## Critical limits

1. The HMAC grant is minted by an explicitly trusted **test fixture**, not by FlowSignal's actual RAI final-bind issuance. Consequently, this test does **not** establish that a genuine FlowSignal denial causes the independent actuator to refuse; it establishes that absence of the separately supplied test grant causes refusal.
2. Server and issuer use a shared test key, not a production IAM/KMS/HSM trust boundary. It does not demonstrate isolation from a compromised agent/host or key theft.
3. The single-process actuator serialises requests and uses a local SQLite nonce uniqueness constraint. Cross-host distributed consumption, rollback/failover, external payment idempotency and crash recovery remain open.
4. The first RED was **constructed intentionally** by exposing an unsafe `/direct` endpoint. It is not a discovered bypass of FlowSignal's existing protected payment executor.
5. These are local loopback HTTP calls against a simulated consequence, not a customer environment, payment rail or cloud external service.
6. This does not test an agent rewriting persistent instructions or genuine encoded shell-command semantics.

## Next qualification gate — NOT EXECUTED

- Bind an external grant cryptographically and causally to a successfully minted FlowSignal RAI final-bind permit and exact operation/route/executor.
- Define how a separate process verifies authoritative provenance without relying on the original Python process-local registry. Verify freshness, revocation, one-use and cross-process replay.
- Prove that all practical actuator transport identities require the external grant, and no agent has alternative direct-write credentials.
- Add crash/restart/rollback/race scenarios with a separately readable independent outcome witness.
- Keep historical RED and candidate GREEN evidence unchanged; perform no baseline merge.

**FlowSignal prevention: NOT ESTABLISHED.**
