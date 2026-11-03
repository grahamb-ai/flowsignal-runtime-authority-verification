# FS-STRIPE-004 — Genuine RAI + Single-Owner Authority + Stripe Sandbox

**Executed:** 3 November 2026. **Stripe account:** Flowsignal.ai sandbox (test mode, `livemode=false`). **Amount:** GBP 1.00 per manual-capture test authorisation. **No live funds.**

## Verified evidence

- Implementation code SHA: `20575fd627e53b372505d5fa6c99bd2f89e80601`.
- [Successful GitHub Actions run 41613691215](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41613691215): **success**. Workflow artifact `fs-stripe-004-41613691215`, SHA-256 digest `8ac554948a1f1e8a4b9b28436b0c0c700173c292670d418e4306d8909ce48c2e`. Evidence output excludes client secrets and test credentials.
- GitHub runs `41613176303` (Python import path), `41613291068` and `41613431397` (Stripe request rejected), and `41613596528` (Stripe rejected obsolete `payment_method_types` param) are preserved diagnostic history. None of those runs passed the capture workflow.
- **Independent provider check:** Stripe connected account API `GetPaymentIntentsIntent` retrieved both PaymentIntents after CI completion, showing the same final provider states and distinct metadata-bound RAI action hashes as the logs.

| Case | Stripe PaymentIntent | Owner boundary result | Stripe test-mode final state | Amount received |
| --- | --- | --- | --- | --- |
| Authority revoked before dispatch | `pi_3UXeIFGXpRZiZOWY18HEwexm` | HTTP 403, `AUTHORITY_STATE_STALE`; 0 local reference effect rows | `canceled`, `livemode=false` | 0 pence |
| Authority current, permitted | `pi_3UXeIHGXpRZiZOWY3SDuriSx` | HTTP 200, `WITNESSED_CONSEQUENCE_FORMED`; 1 local reference effect row | `succeeded`, `livemode=false` | 100 pence |

Both Stripe intents used `capture_method=manual`, `currency=gbp`, `amount=100`. A distinctive `rai_action_binding_hash` was present in each Stripe PaymentIntent's metadata and independently retrieved from Stripe.

## Actual execution path

1. CI's `stripe-sandbox` environment provides `STRIPE_TEST_SECRET_KEY`. The client refuses a key that does not begin `sk_test_` or `rk_test_`.
2. Stripe authorises a £1 test card PaymentIntent using manual capture and returns `requires_capture`. Test PaymentIntent ID becomes part of the RAI request's purpose; the request uses `amount=Decimal("1.00")` and `currency=GBP`.
3. FlowSignal's genuine `prepare_payment_execution`, `mint_rai_bound_execution_permit` and `export_final_bind` validate the bound operation and issue a reference permit/bridge assertion.
4. The PaymentIntent's RAI binding metadata and actual amount/status are retrieved from Stripe before the local owner commitment.
5. The single-owner service checks authority version and records a local synthetic commitment under one SQLite transaction.
6. In the revoked case, the owner refuses; no Stripe capture request is made; test authorisation is cancelled and its `canceled` status retrieved from Stripe.
7. In the allowed case, the owner accepts, the test dispatcher sends `POST /payment_intents/{id}/capture` using an idempotency key derived from the permit signature and PaymentIntent ID, then independently retrieves Stripe status `succeeded` and `amount_received=100`.

## Limits: do not overclaim

**This is a successful end-to-end controlled Stripe TEST-MODE demonstration, not proof of production prevention.**

- The source-owned reference authority is a local loopback SQLite service with test credentials, not independently administered institutional state, production KMS/IAM, operational HA or full per-mandate authority controls.
- The owner writes a local synthetic commitment BEFORE requesting Stripe capture. Stripe does not participate in the same transaction: **revocation after local owner commitment but before Stripe capture remains a real open interval**. A lost capture acknowledgement may require Stripe-side reconciliation.
- The test does not exclude a direct Stripe API caller holding separate credentials; it does not establish universal execution-route closure, external financial rail coverage, or secure production agent credential isolation.
- Existing delegated authority version is not sufficient to prove all institutional mandate updates (scope, counterparty, source authority, cumulative budget, approval) are owned by the same trusted service.
- The Stripe test card, manual-capture and sandbox data are test fixtures, not settlement against an institution's actual payment rail.
- The test code's bridge key and owner tokens are local reference fixtures. The GitHub environment's Stripe TEST key does not enter the artifact.
- This run did not inject revocation between owner commitment and Stripe acceptance. Do not claim instantaneous revocation across that external boundary.
- Stripe dashboard account is **test-only**; no live charge or financial consequence occurred.

## Next implementation milestone

Stop producing more simulator-only checks. To qualify a true customer sandbox, place the authoritative source and Stripe capture adapter in separately administered identities, remove agent-held Stripe credentials, enforce complete operation/beneficiary/amount bindings and single-use idempotency, then test source mutation during dispatch and provider outcome reconciliation using independent Stripe read-back. No merge to frozen `main` until engineering review of the ownership and external-finality contract.

**Status: FS-STRIPE-004 BOUNDED TEST-MODE INTEGRATION SUCCESS. Production prevention: NOT ESTABLISHED.**
