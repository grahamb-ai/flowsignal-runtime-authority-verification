# FS-STRIPE-005 — Protected Capture Dispatcher, Real Stripe Test-Mode Qualification

**Date:** 3 November 2026. **Environment:** FlowSignal.ai connected Stripe sandbox, `livemode=false`. **Amount:** GBP 1.00 each synthetic card authorisation. **Production prevention: NOT ESTABLISHED.**

## Completed results

- Successful real Stripe test workflow: [GitHub Actions 41616097786](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41616097786), implementation SHA `97aa41cf353feaca622c137d5601436b51743c1b`.
- Archived artifact: `fs-stripe-005-41616097786`, SHA256 `3e63f13412d810bc4b9236c5c1fd4ed7497554dde5fb59945dbc1c7b50342bb6`.
- Protected dispatcher Python tests: [GitHub Actions 41616104445](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41616104445): **6 passed**, using real FlowSignal reference permit, owner process, and deliberately simulated provider for fault/race injection.
- Public reference baseline regression: [run 41616104576](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41616104576): success.
- Original frozen `main` not altered; original PR #62 and FS-STRIPE-004 evidence preserved.
- After success the live Stripe test workflow was switched to **manual-only workflow_dispatch** in commit `bb3d14c46ae8787867d874c8d019d837f1b147d4`, preventing new test captures on further branch pushes.

### Independent provider read-back

The following were independently retrieved via the connected Stripe test account's `GET /v1/payment_intents/{id}`, separate from GitHub logs:

| Case | Provider ID | Single-owner/local dispatch | Stripe final | Provider received |
|---|---|---|---|---|
| Authority revoked **after local admission, before dispatch** | `pi_3UXeZTGXpRZiZOWY15U18Vmv` | `REFUSED_STALE_AUTHORITY`, **local owner effect count = 1** | `canceled` | GBP 0.00 |
| Valid reference authority | `pi_3UXeZVGXpRZiZOWY2avsLTBd` | `PROVIDER_CONFIRMED_FORMED`, local owner effect count = 1 | `succeeded` | GBP 1.00 *test mode* |

Both Stripe records have `livemode=false`, `amount=100` minor units, `currency=gbp`, `capture_method=manual`, `metadata.experiment=FS-STRIPE-005`, and their own action-binding hashes matching the evidence outputs.

## Implementation change

- `harness/app/engines/stripe_protected_dispatch_reference.py` adds a bounded reference dispatcher: verify RAI grant/permit correspondence, exact original PaymentIntent ID in the bound request purpose, £1/GBP operation binding, independently retrieve provider metadata and authorisation status, obtain single-owner admission, re-read current owner authority immediately before capture, re-check provider amount/binding/status, send capture with a stable PaymentIntent+permit-signature idempotency key, and independently retrieve the provider outcome.
- Owner outcome unavailable / response dropped: `OWNER_OUTCOME_UNRESOLVED`; **no capture**.
- Provider request acknowledgement dropped: query provider by PaymentIntent ID. A confirmed `succeeded`/100p becomes `PROVIDER_CONFIRMED_FORMED`; any ambiguous state remains `PROVIDER_OUTCOME_UNRESOLVED` and **capture is not automatically retried**.
- `harness/tests/test_fs_stripe_005_protected_dispatch.py` tests current-authority capture, revocation between owner admission and dispatch, PaymentIntent substitution, metadata tampering, provider acknowledgement loss and owner process outage.
- `harness/experiments/fs_stripe_005.py` executes the provider sandbox cases, produces bounded non-secret evidence, and stops on any non-test key. It does not use the connected Stripe account's live credentials.

## Critical architectural distinction

The revoked case deliberately produced **one local owner synthetic effect record but no Stripe capture**. Thus a local `WITNESSED_CONSEQUENCE_FORMED` label is NOT an accurate statement that an external payment has formed. Provider `succeeded` and independently read `amount_received` are necessary to substantiate the downstream test outcome.

## Not established and remaining design work

1. The owner re-check and Stripe API acceptance still are **two separate operations**; revocation *after final re-check but before Stripe processes capture* may still allow capture. This is a non-atomic distributed commitment and cannot be solved by repeated local rechecks alone.
2. The owner presently writes a local synthetic commitment before external capture. A production-grade model should distinguish `RESERVED/AUTHORISED`, `DISPATCHED`, `PROVIDER_OUTCOME_UNRESOLVED` and `PROVIDER_CONFIRMED_FORMED`. Local state requires explicit recovery/compensation if provider capture never occurs.
3. A second caller with its own Stripe key could capture directly. No proof that all payment credentials and routes are exclusively within a hardened, independently administered executor.
4. The owner only holds a reference authority revision in test SQLite, not all institutional mandate scope, revocation evidence, aggregate capacity, operator trust, jurisdiction and per-mandate state.
5. A Stripe PaymentIntent in test mode is not a real bank rail or institutional customer sandbox. No production funds or real-world bank settlement.
6. Tests do not demonstrate Stripe webhooks, API-side idempotency retention duration, network partitions, fraud/chargebacks or concurrent direct Stripe callers.
7. Failed earlier diagnostic FS-STRIPE-005 runs remain preserved and were fixture/package corrections, not successful provider demonstrations.

## Required next gate

**Credential custody and a real protected executor boundary.** Move the payment provider key out of the AI agent and test harness, make the owner issue a one-use capture-authorizing request tied to exact PaymentIntent, amount, beneficiary and expiry, and require the executor to enforce it. Add provider reconciliation as source of external truth, with explicit UNRESOLVED state. Demonstrate that the agent cannot access an alternate Stripe capture path. Keep original evidence frozen.

**FS-STRIPE-005 bounded provider integration: GREEN. Production prevention: NOT ESTABLISHED.**
