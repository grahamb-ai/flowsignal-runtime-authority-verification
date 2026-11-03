# FS-RAW-DENIAL-001 — Independent Commitment Witness Qualification

**3 November 2026 | Synthetic local reference | Production prevention NOT ESTABLISHED**

## Frozen baseline and first RED

- Public `main` unchanged at `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.
- [PR #54 — dual-store rollback FIRST RED](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/54); [run 41605548615](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41605548615): **1 intentional failure**. After original authority database and separate local anchor were both restored, the same genuine FlowSignal RAI reference permit was accepted again. A third test-owned SQLite observer that had not been restored documented two acceptances.

## Reference independent witness candidate

- [PR #55](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/55); [run 41605887179](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41605887179): **3 passed, 0 failed** in 1.15 s.
- [Existing regression run 41605887154](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41605887154): **success**.

A separately running localhost witness process maintains a third SQLite database, independent of the source authority database and local source anchor. The forwarding test proxy first requests local source/RAI-authorised synthetic commitment and, only if local source approves, requests a separate simulated external consequence from the witness using the same signed reference permit and bridge assertion. The witness applies a one-use unique signature constraint, independent of restored local files.

**Observed in the tested dual-restore sequence:** The first local and witness commits succeed. After the local authority DB and anchor are restored to pre-consumption images, local source wrongly accepts the same grant again; the witness instead refuses it with HTTP 409. The external witness database retains precisely **one** modeled consequence row.

An unavailable witness results in `WITNESS_OUTCOME_UNRESOLVED` with `formed=None` rather than a false claim that the external effect was formed or refused. A call to the witness without its test-only service credential is refused.

## Critical residual discrepancy

The local source may record a second **local** commitment despite the witness refusing a second modeled external effect. The two actions occur over separate HTTP calls and different databases, and are **not** atomic. In the outage test the source may commit locally while witness has no record: a retry may be refused by the local source before the external effect can be formed. The present candidate contains no reconciliation/repair protocol for this mismatch.

A successful test is therefore evidence for **one-use enforcement by a surviving synthetic witness**, not evidence that the local authority state, independent witness and any external payments always agree.

## Unqualified properties

1. Independent storage only in the sense of a third local process/SQLite file, **not** separate administrative ownership, physical isolation, immutable storage, cloud HA, production IAM or hardware custody.
2. The witness is itself vulnerable if its database and backups are rolled back, duplicated, replaced or independently re-created; no global epoch/monotonic trust root has been proven.
3. Source and witness state remain distinct and non-atomic. Lost acknowledgement, crashes between the two commits, network partitions and reconciliation are open.
4. Only the modeled external consequence is recorded in SQLite. No bank/payment rail, irreversible provider settlement, external network or third-party accounting record is involved.
5. The witness checks a signed reference permit and trusted bridge assertion, but does not independently establish authentic *current* institutional authority or the latest revocation. A stale but valid permit can still be accepted on its first witness use.
6. No AI agent attempted to rewrite persisted instructions, use a real alternate shell/tool, or bypass service credentials; original public incident prevention is **NOT ESTABLISHED**.
7. No changes or merges to the frozen public baseline or Structural Zero project.

## Next qualification gate

Preserve the local-vs-witness disagreement as a hostile test, distinguish `LOCAL_COMMITTED`, `EXTERNAL_COMMITTED`, and `OUTCOME_UNRESOLVED`, and demonstrate a recovery protocol for both orders of failure without double formation. A production claim will require external provider-owned evidence, independently authoritative state delivery and a trust boundary the agent cannot rewrite.

**Disposition: DUAL LOCAL RESTORE RED PRESERVED; INDEPENDENT SYNTHETIC WITNESS CANDIDATE GREEN; CROSS-SERVICE CONSEQUENCE CONSISTENCY AND PRODUCTION PREVENTION NOT ESTABLISHED.**
