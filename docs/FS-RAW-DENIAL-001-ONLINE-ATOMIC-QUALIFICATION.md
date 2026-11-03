# FS-RAW-DENIAL-001 — Online Authority and Source-Owned Reference Commit

**Date:** 3 November 2026  
**Status:** Source-owned local reference candidate GREEN; production prevention **NOT ESTABLISHED**.

## Evidence sequence

- Online authority lookup candidate: [draft PR #37](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/37). [Run 41597328946](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41597328946): **7 passed**. A valid FlowSignal RAI permit with current online source authority was accepted. A delivered source revocation, inaccessible source and unauthorised update were handled correctly. A deliberate test confirmed the unresolved upstream source-update gap.
- Check-to-commit race: [draft PR #38](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/38). [First RED run 41597572977](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41597572977): **1 failed as designed**. A barrier allowed the test to advance authority after the actuator's online lookup but before its separate SQLite write. The actuator returned HTTP 200 and a synthetic consequence was recorded.
- Source-owned atomic reference candidate: [draft PR #39](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/39). [Run 41597923583](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41597923583): **7 passed**. The authority-source service checks its own current version and records the synthetic consequence in the same `BEGIN IMMEDIATE` SQLite transaction. The actuator merely forwards the signed FlowSignal RAI assertion and returns the source service's result.
- Existing public verification workflow: [run 41597923371](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41597923371): **success**.
- Frozen public baseline `main` remains unchanged at `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.

## What is demonstrated

A genuine RAI final-bind permit and signed reference bridge assertion reach a separate local HTTP actuator. The actuator performs its preliminary online check and requests a final commit from the source-owned reference service. Both the authority state version and the represented effect are in one local SQLite database, so the source service's commit transaction serializes its own authority-version update with its own modeled effect write.

The candidate tests show valid commit once, cross-route replay refusal, refusal after prior revocation, refusal when authority changes **after the preliminary online check**, rejection of missing grants and unauthorised commit callers, and failure closed when the source is unreachable before the operation.

## Explicit remaining RED / limitations

1. **Upstream ownership:** A separate test deliberately advances the FlowSignal *in-process* authority state without delivering the change to the new source-owned service. The old grant still commits. Thus the service is not proven to be the sole authentic origin of authority changes.
2. **External settlement:** The authority service owns the *synthetic effect ledger*. A genuine bank/payment processor cannot generally be updated in the same local SQLite transaction. This is not proof of distributed atomicity, external idempotency or compensation/reconciliation.
3. **Provenance bridge:** Final-bind evidence is authenticated by a test-HMAC bridge that checks in-process RAI registry and provenance. Independent authority issuance across hosts, verifier identity and key custody remain unqualified.
4. **Access control:** Loopback test tokens are not production IAM, mTLS, KMS/HSM, operator separation or hardened administration.
5. **Recovery and concurrency:** Restart, rollback of the authoritative DB, power loss, lost acknowledgement, crash between external commit and response, competing source replicas and cross-host transactions are untested.
6. **Evidence independence:** The synthetic effect is recorded by the source service; the tests independently query that SQLite ledger, but it is not independent third-party custody.
7. **Agents and routes:** No live AI agent, real encoded shell command, external payment rail, customer environment or exhaustive alternate-route inventory was tested.

## Next distinct engineering qualification

Create one true source of authority whose mutation path is independently administered, durable and non-bypassable. Separate the authority decision from the real-world consequence, define the irreversible linearization point and adopt evidence that distinguishes *permitted*, *committed*, *outcome unresolved*, and *confirmed formed*. Run adversarial crash/retry and multi-process tests against the real external actuator before any production claim.

**Disposition: REFERENCE PROPERTY TESTED. REAL ROUTE CLOSURE AND PRODUCTION PREVENTION NOT ESTABLISHED.**
