# FS-STRIPE-001–003 — Bounded Stripe sandbox qualification record

Status: **CLOSED WITHIN BOUNDED REFERENCE-DISPATCHER / STRIPE TEST-MODE SCOPE**  
Production / independent authority / distributed atomicity: **OPEN**  
Date: 2026-10-18

## Scope

Real Stripe test-mode PaymentIntents, GBP 1.00 per isolated case, manual capture, test card fixture. No live funds, production credentials, or customer payments. Authority versions in FS-STRIPE-002/003 are simulated locally; this is not a deployed independent FlowSignal authority service.

## Evidence lineage

| Case | Source / evidence | Observed outcome | Classification |
| --- | --- | --- | --- |
| FS-STRIPE-001 | Experiment correction `67ebe57301cfafdd717a224473dcdc46291c89a8`; GitHub Actions run #6, artifact preserved | PaymentIntent `requires_capture` -> `canceled`; later capture HTTP 400 `payment_intent_unexpected_state`; final `canceled`; `livemode=false` | PASS — provider cancellation lifecycle |
| FS-STRIPE-002 | `0a91d90b6ba211085a5c73d4e0281f146bdb6c48`; bounded ordering workflow and artifact | Simulated revocation before dispatch: no capture sent, provider `canceled`. Capture before simulated revocation: HTTP 200, provider `succeeded` | PASS — bounded orderings |
| FS-STRIPE-003 FIRST RED | `ed0eb0a124e6a942eab8b2decf3cc59016dce40e`; preserved first-red workflow artifact | Gateway checked authority version 1; injected version 2; deliberately vulnerable dispatcher still sent capture; Stripe HTTP 200, `succeeded` | RED — stale check used for capture |
| FS-STRIPE-003 remediation | `399a6c914a03a9caf509d9c8180d5906b83ae141`; remediation workflow artifact | Version 1 check followed by version 2 injection; corrected dispatcher refused dispatch; Stripe final `canceled` | PASS — bounded pre-dispatch revalidation |

Experiment implementation commit for first RED: `6123792e51241bdabbc504b76e1ee8585e70a065`. Remediation implementation commit: `44109551feb29a6963d19b0b09a204747099f831`.

**Evidence source:** GitHub Actions logs and uploaded artifacts, retained under the corresponding workflow runs. PaymentIntent identifiers and precise timestamps remain in the original logs. A green workflow alone is not an independent audit or production assurance certificate.

## What the evidence does not prove

- No independent FlowSignal authority service was used as the source of truth for Stripe capture.
- No atomic compare-and-set or equivalent transaction spans authority revocation and Stripe's external capture.
- No proof that a revocation arriving *after* the final gateway check but before Stripe accepts capture prevents the consequence.
- No independent proof of all possible provider routes, asynchronous retries, webhook processing, or irreversible external consequences.
- No banking-rail or production-money qualification. Stripe's test mode is the provider surface here.
- FS-STRIPE-003's pre-dispatch recheck closes only the injected window in the bounded dispatcher; it does not establish distributed atomicity.

## Next proof obligations

1. Bind capture requests to an independently maintained authority state/version with immutable evidence.
2. Introduce deterministic barriers at check, dispatch, provider acceptance and response reconciliation.
3. Demonstrate that every supported capture route is mediated, including retries and alternative callers.
4. Specify the authority cut-off and the external provider's point of irrevocability; distinguish *refused before dispatch*, *dispatched but unknown*, *provider accepted*, and *compensated after acceptance*.
5. Qualify idempotency, cancellation races, network timeout ambiguity, duplicate submissions and compensation independently.
6. Preserve original REDs, provider request identifiers, full result lineage and new remediation evidence.

## Public claim boundary

Defensible: "In a controlled Stripe sandbox experiment, we reproduced a stale-authority check leading to an actual test-mode capture, then demonstrated a bounded pre-dispatch revalidation that refused capture and cancelled the authorisation."

Not established: "FlowSignal guarantees no external payment consequence after revocation across every distributed route."

This record is an engineering qualification, not a third-party certification.
