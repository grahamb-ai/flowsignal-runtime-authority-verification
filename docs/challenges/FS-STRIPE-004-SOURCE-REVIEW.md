# FS-STRIPE-004 — Existing authority-source review

Date: 2026-10-18  
Status: **SOURCE REVIEW COMPLETE; DEPLOYED SERVICE UNVERIFIED**

## Reviewed public implementation

Repository: `grahamb-ai/flowsignal-agentic-payments`

- `harness/app/engines/authority_store.py` (file SHA `38c8d7018f38a625ff397b99d83ec3e702361892`): `_MonotonicAuthorityState` maintains a version in process memory, protected by `threading.RLock`. `authority_state_guard()` explicitly states in-process reference-harness scope and no distributed transaction semantics.
- `harness/app/engines/execution_gateway.py` (file SHA `6ed2feff74bbcc0a6bb6398e3b5881d6cad452ff`): `validate_execution` verifies receipt HMAC, compares `receipt.authority_state_version` to `get_authority_state_version()`, validates ALLOW/freshness/action binding and issues an execution permit. It is not by itself a remote Stripe capture transaction.

## Finding

**The reviewed source does not meet FS-STRIPE-004's independent durable authority requirement.** It does not establish a separately deployed authority service, durable monotonic storage across restarts, authenticated remote revocation, or atomic provider acceptance. It must not be substituted for deployment evidence.

## Required evidence from Google Cloud staging

- Active Cloud Run revision and image digest.
- Actual deployed authority-determination and revocation interfaces, authentication and authorization model.
- Persistence service and monotonic state guarantees across service restarts and multiple instances.
- An independent principal controlling authority mutations, separate from the capture gateway.
- Traceable decision/receipt binding to PaymentIntent and provider request.
- Explicit failure behaviour for unavailable authority service and in-flight provider outcome ambiguity.

## Next decision

If staging provides these capabilities, test with a non-live Stripe gateway on an isolated branch. If not, design a dedicated durable authority service and qualify it independently first. Do not guess routes or claim independent enforcement based on the repository source.
