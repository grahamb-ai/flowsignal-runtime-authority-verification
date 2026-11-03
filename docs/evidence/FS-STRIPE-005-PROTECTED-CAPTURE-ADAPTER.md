# FS-STRIPE-005 — Protected Capture Adapter Integration Gate

**Date:** 3 November 2026. **Status:** Reference contract GREEN, deployment and credential isolation OPEN.

## Implemented

The adapter `app/engines/stripe_protected_capture.py` defines a narrow execution interface: signed RAI assertion, exact PaymentIntent ID, action-binding hash and an authority-owner commitment dependency. Callers do not provide Stripe API credentials. The provider implementation is injected into the adapter and must be deployed in a protected process for the intended isolation property.

Before asking the owner to commit, the adapter independently retrieves the provider PaymentIntent and checks `livemode=false`, GBP 1.00, manual capture, `requires_capture` and the exact RAI binding hash stored in Stripe metadata. It refuses malformed requests and mismatched provider state. If the owner refuses, capture is not attempted. After capture, the adapter independently retrieves the PaymentIntent and distinguishes `CONFIRMED`, `REFUSE` and `UNRESOLVED`. A lost capture acknowledgement is reconciled by provider read-back; uncertain results are not blindly retried.

## Verification

- [PR #65](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/65)
- [Contract run 41617732381](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41617732381): **8 passed** with a simulated provider, no Stripe API calls.
- Earlier real Stripe sandbox evidence remains in [FS-STRIPE-004](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/63), [successful run 41613691215](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41613691215). Independently retrieved provider PaymentIntents `pi_3UXeIFGXpRZiZOWY18HEwexm` (canceled) and `pi_3UXeIHGXpRZiZOWY3SDuriSx` (succeeded, 100 pence), both `livemode=false`.
- No additional PaymentIntents were created for FS-STRIPE-005.

## Unresolved architectural conditions

1. The adapter is **not deployed as a separate process with exclusive Stripe credentials**. A caller with independent Stripe credentials could bypass it. The API shape alone is not credential isolation.
2. Authority-owner commit and provider capture are still two separate operations. A deterministic test explicitly characterizes revocation after owner commit and before provider dispatch as an **OPEN gap**, even though its test function passes. The code does not guarantee instantaneous revocation at Stripe acceptance.
3. Stripe's `requires_capture` state and action-binding metadata are necessary checks, not cryptographic proof of who created the PaymentIntent or who else can capture it.
4. An owner-commit timeout can mean the local record was formed or not; the adapter reports UNRESOLVED without blindly retrying. Durable recovery and reconciliation are not yet implemented.
5. Provider capture may be accepted but the response lost; independent read-back can confirm, but if Stripe retrieval is unavailable the outcome remains UNRESOLVED.
6. Provider credentials, full mandate authority, institutional owner IAM, per-mandate versioning, independent logs and alternative tool routes remain unqualified.
7. Tests are mock-provider contract tests; they do not supersede the previous FS-STRIPE-004 actual test-mode PaymentIntent evidence.

## Implementation next step, not another isolated hostile test

Deploy a protected Stripe test-mode executor with credentials accessible only to that service, restrict all agent/other process direct access, add durable request-id and outcome reconciliation, and obtain a bank or provider sandbox architecture where the final authority cut-off and provider capture point are clearly defined. Do not claim cross-service atomicity unless the provider participates in the enforcement transaction or equivalent native authorisation boundary.

**Production prevention: NOT ESTABLISHED. Frozen main and Structural Zero unchanged.**
