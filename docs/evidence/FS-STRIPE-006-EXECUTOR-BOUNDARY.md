# FS-STRIPE-006 — Separate Executor Service and Signed Payment Scope

**3 November 2026 | Reference implementation completed. Real deployment isolation NOT ESTABLISHED.**

## Why this differs from the previous adapter

FS-STRIPE-005 was a Python function with a provider interface. FS-STRIPE-006 is an actual **separate localhost HTTP server process**, accepting only a narrow authenticated `POST /capture` and read-only `GET /outcome` API. A genuine RAI final-bind permit, its provenance assertion and the exact Stripe PaymentIntent are prerequisites to the authority owner and provider calls.

The captured operation's payment ID, 100 pence amount, GBP currency and manual-capture mode are **inside the bridge-HMAC-signed RAI assertion**. The signing function confirms that the underlying original FlowSignal action-binding hash corresponds to the exact PaymentIntent identifier and operation request before adding the scope. The executor rejects a generic grant or any attempt to substitute another PaymentIntent.

## Implemented components

- `harness/app/engines/rai_export_verifier.py`: side-effect-free verification of permit signature, bridge assertion, RAI provenance correspondence and expiry. No dependency on the old actuator's SQLite environment.
- `harness/app/engines/stripe_capture_grant.py`: exact PaymentIntent/amount/currency/capture mode signing, with original request-binding correspondence check.
- `harness/fs_stripe_006_executor_service.py`: separate HTTP executor, signed-grant verification, authenticated request surface, test-mode provider constraints, source owner call and persistent SQLite attempt journal. `fixture` provider mode must be explicitly selected for unit/integration tests; `stripe` mode requires a test-only secret key.
- `harness/app/engines/stripe_protected_capture.py` (FS-STRIPE-005): provider status preflight, authority-owner gate, capture and independent provider outcome read-back. Does not retry blindly on unknown transport results.

## Verified evidence

[Draft PR #66](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/66), [final reference CI run 41619567145](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41619567145): **17 passed, 0 failed**, including 9 separate-process integration cases and 8 adapter contract checks.

[Existing public baseline regression 41619566988](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41619566988): **success**. Frozen main remains unchanged at `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.

The original FS-STRIPE-006 integration run failed at startup due to an old verifier's import-time database dependency, and the intermediate diagnostic runs remain preserved. The pure verifier removes that dependency instead of configuring an unrelated database.

Reference cases cover:
- Genuine RAI signed capture passed to a separate HTTP process and an independently stored synthetic provider effect.
- Direct authority owner revocation prevented the provider effect.
- Unauthorised HTTP caller denied for both capture and outcome lookup.
- Tampered cryptographic assertion denied without a provider attempt.
- Provider payment metadata/hash mismatch denied.
- Persistent executor attempt journal prevents redispatch after restart.
- Repeated payment operation does not cause a second provider capture.
- Mutating permit signature denied.
- Valid RAI permit aimed at a different PaymentIntent denied.
- Generic RAI export without signed Stripe-specific operation scope denied.
- FS-STRIPE-005 provider adapter: refusal, confirmation, lost acknowledgement read-back and unresolved classification (including an explicitly OPEN owner-commit-to-Stripe revocation window).

## Real Stripe provider evidence, separately preserved

The earlier [FS-STRIPE-004 actual Stripe test-mode run 41613691215](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41613691215) remains independently verified with Stripe read-back:
- `pi_3UXeIFGXpRZiZOWY18HEwexm`: canceled after owner REFUSE; 0 pence captured.
- `pi_3UXeIHGXpRZiZOWY3SDuriSx`: succeeded after owner ALLOW; 100 pence captured.
- Both `livemode=false`.

**FS-STRIPE-006 itself did NOT issue additional real Stripe test PaymentIntents.** Its CI used a persistent synthetic fixture provider to validate the new separate-process interface. It must not be presented as a separately verified real Stripe capture.

## What remains to be implemented and independently qualified

1. Deploy executor under a different service account/host/container with its **own** Stripe TEST restricted key, isolated runtime secrets, production-grade mutual authentication, service identity and auditable permissions. On a single shared developer/CI host, a separate process is not a security boundary against privileged actors. Do not give agents provider credentials or owner administrative secrets.
2. Confirm the chosen Stripe restricted key permits ONLY necessary read and capture operations, with no second unrestricted credential reachable from the agent or other executable route. Provisioning/authorisation should be separately permissioned.
3. Complete per-mandate institutional authority ownership, monotonic revocation, expiry and capacity at the separate owner, not only a global version counter. Do not claim this standalone reference API represents full institutional competence.
4. Owner commitment and actual Stripe capture remain separate external operations. Direct revocation in that interval is not guaranteed to prevent a provider capture. Correct external finality requires agreed provider-side authority enforcement or an explicit unresolved/compensation/reconciliation model.
5. Protect executor attempt journal from rollback, unauthorised modification, multi-instance duplication and lost acknowledgements. The current local SQLite journal prevents redispatch only under its single-host reference assumptions.
6. Exercise FS-STRIPE-006 itself using a controlled Stripe test-mode payment under a credential-restricted executor deployment and independently retrieve the PaymentIntent from Stripe.
7. Preserve historical first REDs, no merges to frozen main and no changes to Structural Zero.

**Disposition: SEPARATE-PROCESS EXECUTOR AND SIGNED PAYMENT SCOPE REFERENCE GREEN; REAL SERVICE IAM AND STRIPE PAYMENT-RAIL ENFORCEMENT NOT ESTABLISHED. Production prevention: NOT ESTABLISHED.**
