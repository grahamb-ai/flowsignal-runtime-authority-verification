# FS-RAW-DENIAL-001 — Split Authority and Rollback Qualification

**Date:** 3 November 2026
**Scope:** Single-host, local SQLite reference; **production prevention NOT ESTABLISHED**.

## Evidence history

- Public main baseline unchanged: `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.
- [PR #50 — split authority FIRST RED](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/50): [run 41604383530](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41604383530) **one intentional failure**. Two independent authority source databases accepted the same genuine RAI final-bind permit and each recorded one synthetic consequence.
- [PR #51 — common authoritative ledger](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/51): [run 41604630219](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41604630219) **2 passed**. Sixteen clients across two authority service processes sharing one SQLite commitment ledger yielded one formed effect and fifteen replay refusals. Restoring an old copy as a separate writable source formed a duplicate; this is a deliberately preserved gap characterisation, NOT a successful security test.
- [PR #52 — canonical ledger rollback FIRST RED](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/52): [run 41604886125](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41604886125) **one intentional failure**. Restoring a pre-commit copy of the canonical SQLite ledger caused the same permit to be accepted again. A test-owned witness database outside the restored file recorded both acceptances.
- [PR #53 — surviving commitment anchor](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/53): [run 41605166054](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41605166054) **3 passed**, 0 failed.
- Existing public baseline regression: [run 41605166100](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41605166100) **success**.

## Bounded candidate

A local source service checks authority in its primary SQLite database and inserts a one-use synthetic commitment into an **attached, separately stored anchor SQLite database** within one local transaction. The anchor is intentionally *not* restored when the primary authority DB is replaced with an earlier copy.

- Replaying a permit after primary-DB restoration returns `REPLAY_REFUSED` if the anchor survives, and the anchor's original commitment row remains.
- Two independent source database files using one shared anchor accept the first represented commit and refuse the second.
- A separate hostile test restores the anchor itself to a pre-consumption image. The previously used permit then **forms a second synthetic effect**. That test passes only as a **characterisation of a critical remaining weakness**, not as evidence of prevention.

## Nonclaims and open conditions

1. The anchor is **not** immutable, separately administered, remotely attested, append-only under privileged attackers, tamper-proof or resistant to whole-storage snapshot restoration.
2. SQLite `ATTACH` on one host with local files does not prove safe transactionality under power loss, asynchronous replication, distributed file systems, cross-host failover or split-brain.
3. Two independent sources are effectively co-ordinated only because they share the same accessible local anchor. No real consensus protocol, globally elected writer or authenticated epoch ownership is implemented.
4. A privileged or alternate writer that ignores the anchor remains out of scope. The original route-bypass risk therefore remains critical.
5. This is a **synthetic** modeled consequence, not a bank transfer or provider-owned independently witnessed settlement.
6. Source authority state is still supplied through a reference harness: authentic external delivery, mandate-scoped monotonic epoch transitions, inability to rewrite source state and secure expiry remain unqualified.
7. Final-bind bridge HMAC and process-local provenance are reference trust assumptions. Production IAM, cryptographic key custody, institutional countersignature and service identity are not demonstrated.
8. No production prevention claims or tests of real agent persistent-instruction rewriting are supported.

## Next qualification gate

A **separately owned, rollback-resistant one-use authority state and consequence witness** with explicit source-of-truth identity, write competence, monotonic epoch/commit sequence, hostile restoration/rollback detection and automatic fail-closed behaviour for unavailable state. Such a claim will require a stronger storage and process boundary, not merely another locally restored SQLite file.

**Disposition: SPLIT-SOURCE FIRST RED PRESERVED; LOCAL SURVIVING-ANCHOR CANDIDATE GREEN; FULL ROLLBACK RESISTANCE AND PRODUCTION PREVENTION NOT ESTABLISHED.**
