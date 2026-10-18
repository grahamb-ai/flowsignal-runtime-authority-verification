# FS-STRIPE-004 — Stripe Actuator Contract v0.1

Status: **DESIGN ONLY — NO STRIPE API CALLS, NO PRODUCTION QUALIFICATION**  
Target seam: Google CAGE `ExecutionActuator` / `dispatch_actuation` and FlowSignal Step 2 authority receipt (source not yet independently pinned).

## Principle

The Stripe actuator must not accept an application-provided ALLOW flag as authority. It must receive a CAGE-issued, verifiable execution clearance bound to a fresh FlowSignal determination and the exact Stripe capture operation. The actual capture is a separate provider consequence and cannot be represented as atomic with a Redis consumption event.

## Minimum clearance binding

- `execution_id`, `thread_id`, `actor_id`, `principal_id`, `caller_identity`
- `action = stripe.payment_intent.capture`
- `payment_intent_id`, `amount_to_capture` (minor currency units), `currency`
- `authority_receipt_id`, `authority_state_version`, `authority_fence` where supported
- `action_binding_hash`, `routing_seal` / action hash, `issued_at`, `expires_at`
- `idempotency_key` bound to the same operation and immutable across retries
- `executor_id` and expected actuator identity

Any missing, substituted or stale material must result in refusal before a Stripe capture request is dispatched. Exact fields must be reconciled with the frozen Step 2 contract before implementation.

## Actuator state model

1. `PROPOSED`: capture intent recorded, no provider request
2. `AUTHORITY_VERIFIED`: trusted determination accepted for this exact capture
3. `DISPATCH_COMMITTED`: dispatch record durably bound to execution/idempotency key
4. `PROVIDER_REQUEST_SENT`: network request may have reached Stripe
5. `PROVIDER_ACCEPTED` / `PROVIDER_REJECTED` / `PROVIDER_UNKNOWN`
6. `RECONCILED`: final Stripe PaymentIntent state and evidence correlated

A local `EXECUTE` or `DISPATCH_COMMITTED` is not a Stripe capture outcome. A timeout after sending cannot be classified as non-formation.

## Hostile acceptance matrix

| Case | Injection | Required evidence |
| --- | --- | --- |
| A | Revocation before final authority determination | No capture request, refusal receipt |
| B | Revocation after determination before dispatch | Stale clearance refused; original RED preserved if not |
| C | Revocation during provider request | Preserve actual provider acceptance/unknown and timing; do not claim universal prevention |
| D | Change PaymentIntent/amount/currency after receipt | Binding mismatch, zero dispatch |
| E | Replay same clearance | Single-use refusal and no second capture |
| F | Concurrent workers with same execution ID | One durable dispatch reservation; reconcile Stripe status |
| G | Timeout/connection reset after request sent | UNKNOWN and reconciliation, no blind retry |
| H | Authority service unavailable | Fail closed for new dispatch; reconcile existing in-flight request |
| I | Provider accepted then authority revoked | Accepted consequence retained; cancellation/refund is separate compensation |
| J | Direct Stripe call outside CAGE | Detect and explicitly classify ungoverned route; cannot claim route closure |

## Implementation hold

Before writing a live Stripe actuator:
1. Obtain frozen Step 2 source, exact receipt schema and signing/verification implementation.
2. Verify current Phase 4 CAGE actuator interface and immutable commit.
3. Specify a durable independent authority service with authenticated revocation and version monotonicity.
4. Approve an isolated test environment and Stripe restricted-key access.
5. Establish provider evidence retention and a runbook for ambiguous capture outcomes.

**No API key is to be committed, logged, or copied into this design record.**
