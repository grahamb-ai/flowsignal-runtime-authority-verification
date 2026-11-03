# FS-RAW-DENIAL-001 — Single Authority Owner Reference Correction

**3 November 2026 | Architecturally corrected for the *authority version / synthetic commitment* reference scope. Production prevention NOT ESTABLISHED.**

## Decision

**Do not replicate mutable authority from the FlowSignal caller into the executor after the fact.**

Instead, the consequence owner is the authority-revision writer and the synthetic effect writer. A configured FlowSignal reference process delegates `get_authority_state_version()` and `advance_authority_state_version()` directly to the one owner, with no process-local fallback. That owner commits revocation (`POST /revoke`) and checks the same authoritative revision during synthetic consequence formation (`POST /commit`) using one SQLite database and `BEGIN IMMEDIATE`.

The owner controls the revision's next value. Arbitrary client-chosen `POST /advance` is deliberately unavailable. The legacy process-local counter still exists ONLY for environments not opting into the experimental owner, preserving the frozen baseline and the prior regression suite. The owner is started on loopback with distinct test credentials for read, administration and commit.

## Implementation

- `harness/fs_raw_denial_001_authority_owner.py`: sole owner of the reference revision and synthetic consequence, direct administrative revocation, atomic current-revision comparison and one-use commitment.
- `harness/app/engines/authority_owner_client.py`: explicit owner API, fail closed on unavailable owner or rejected credentials, no cached authority or local fallback.
- `harness/app/engines/authority_store.py`: opt-in delegation for version read and advance through `FLOWSIGNAL_AUTHORITY_OWNER_URL`. Original frozen `main` has **not** been changed.
- `harness/tests/test_fs_raw_denial_001_single_owner.py`: seven tests with genuine reference RAI final-bind permit minting.

## Verification

[Draft PR #62](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/62), [CI run 41610009345](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41610009345): **7 passed, 0 failed**, including:

1. Current owner revision is read by RAI minting and the owner commits the modeled effect exactly once.
2. Direct administrative revocation updates the owner database; the pre-revocation permit is refused.
3. Unavailable owner causes reference reads and revocations to fail without falling back to memory.
4. Incorrect admin credentials are refused, without changing the owner version.
5. Arbitrary user-chosen source version writes are unavailable.
6. Genuine permit minting can use the new delegated epoch when owner remains current.
7. A caller that intentionally disables delegation for minting may obtain a **stale local** reference permit, but the owner rejects its consequence after direct owner revocation.

Existing public regression [run 41610009044](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41610009044): **success**. Frozen `main` SHA remains `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.

## What is now materially different

The previous series repeatedly failed because the original in-process authority version could advance without a corresponding update at the consequence owner. **That source/version divergence is eliminated by construction in the new opt-in reference path:** the administrative mutation goes straight to the source that owns commitment, and the final writer reads this same source's state transactionally.

This is a design correction, not merely another copied-state fence.

## Critical production gaps — not solved by this reference change

- This delegates one reference authority *revision*, not all institutional permission data, mandate revocation semantics, per-mandate epochs, evidence authenticity or aggregate usage. The wider `institutional_authority`/other stores are not migrated to the new owner.
- The opt-in is an environment setting in a reference harness. A malicious host can modify local code, environment, keys and the test-owned SQLite database. No independently administered or hardened production service trust boundary is established.
- Process-local Python locks are **not** distributed locks. The only tested atomicity is the owner's local SQLite synthetic consequence transaction.
- The consequence is a synthetic row written in the same database. No real bank/payment provider can be assumed to participate in that transaction, so external payment finality, provider idempotency and independent custody remain open.
- The test HMAC keys and header credentials are not production-grade KMS/IAM/mTLS. The server has no operational HA, authentic leadership election, crash-resistant independent epoch anchor, quorum or protected rollback witness.
- A configured client that has lost access to the owner fails closed; a separate unauthorised direct-to-bank route has **not** been eliminated by this code.

## Implementation gate for live payment sandbox

1. Put all applicable institutional authority changes under a genuinely independent **source-owned** authoritative service, with revocation competency, evidence, per-mandate epochs and monotonic mutation audit. Remove separate writable copies.
2. Route every consequence-capable agent tool and executor to a payment adapter with no alternate payment credentials; define service identity and prohibit agent access to administrative/commit tokens.
3. Keep authority current through a permit lifecycle and verify final admissibility at the payment execution boundary. For external providers, define reserve/consume/confirm, idempotency, timeout, outcome-unresolved and reconciliation semantics explicitly rather than pretending bank settlement is a local database write.
4. Test with a real provider **sandbox** and independently observed outcomes, including a provider that commits but loses acknowledgement, source unavailability and revocation immediately before submission.
5. Qualify independently before promoting any draft into the production architecture.

**Status: SINGLE-OWNER VERSION/REFERENCE CONSEQUENCE CORRECTION TESTED. FULL INSTITUTIONAL AUTHORITY OWNERSHIP AND PRODUCTION PAYMENT PREVENTION NOT ESTABLISHED.**
