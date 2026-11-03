# FS-RAW-DENIAL-001 — Recovery Final-Bind Witness Qualification

**Date:** 3 November 2026
**Scope:** Localhost reference simulation only. **Prevention: NOT ESTABLISHED**.

## Evidence chain

- [PR #58](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/58): [FIRST RED run 41606959266](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41606959266), **1 failed** as designed. Authority revoked after reconciliation preflight but before the independent witness request; old witness accepted and recorded one synthetic consequence.
- [PR #59](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/59): [candidate run 41607294342](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41607294342), **2 passed**. Witness checks current online authority itself before its write, refusing revocation delivered between reconciliation preflight and witness invocation.
- [PR #60](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/60): [FIRST RED run 41607543636](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41607543636), **1 failed** as designed. A test barrier after witness's successful authority lookup but before its separate SQLite write allows a revocation; witness still returns HTTP 200 and forms a synthetic effect.
- [PR #61](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/61): [candidate run 41607931609](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41607931609), **4 passed**. New reference witness owns an authority version and synthetic effect record in one SQLite database. Test cases: delivered revocation refused, current permit commits once, replay refused, unauthorised witness caller refused, and explicitly documented stale permit acceptance when source revocation is not delivered. The aggregate consists of four tests; the undelivered-update characterization is a passing demonstration of a remaining weakness, not a safety proof.
- [Public baseline regression 41607931672](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41607931672): successful. Original main remains unchanged at `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.

## What the latest candidate does establish

Within the new witness-owned *single local SQLite database*, the witness checks its own published authority version inside `BEGIN IMMEDIATE`, inserts a unique reference permit-signature effect and commits before reporting success. Version updates through the same database's authorised test endpoint must serialize against those effect transactions. This removes the specific intra-database check-to-insert gap shown in the earlier separate lookup model, under that model's storage assumptions.

## What it does NOT establish

1. Source ownership and delivery authenticity: the original FlowSignal in-process authority source can advance without the witness observing the change; a test deliberately shows stale authority acceptance. Therefore there is no demonstrated global immediate-revocation guarantee.
2. Institutionally authoritative grant state: test-only SQLite state and header secrets are not production, independently controlled, IAM/KMS-backed or cross-host quorum state.
3. External consequence atomicity: the modeled effect is in the same database as witness authority. No bank/provider API, external settlement, independently attested remote payment or distributed transaction was executed.
4. Whole-store rollback: loss/restoration of witness's own authority-and-effect database can reintroduce previously exercised permits. No immutable storage or adversarial privileged-writer resistance established.
5. Persistent agent instructions, actual encoded tool commands, and universal alternate-route closure were not re-tested in this qualification.
6. The suite does not include a separate deterministic mid-transaction interleaving test; the transaction boundary is inspected in source and existing reference contention tests support analogous single-store behavior.

## Research disposition

Continue only with a clearly defined **source-of-truth ownership contract** and a real external provider whose consequence can be independently witnessed. Preserve all first REDs, keep the frozen baseline untouched and do not claim that the latest GREEN supersedes failed authorization continuity requirements.

**REFERENCE CANDIDATE GREEN; AUTHORITATIVE SOURCE DELIVERY AND PRODUCTION PREVENTION NOT ESTABLISHED.**
