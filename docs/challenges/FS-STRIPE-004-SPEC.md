# FS-STRIPE-004 — Independent Authority / Stripe Capture Boundary

Status: **DESIGN CANDIDATE — NOT QUALIFIED**  
Predecessor: [FS-STRIPE-001–003](../evidence/FS-STRIPE-001-003-QUALIFICATION.md)

## Purpose

Test the relationship between an independently controlled, versioned authority state and an external Stripe manual-capture consequence. This is not a claim of distributed atomicity.

## Architecture and trust separation

- **Authority service**: separate process and persistence boundary, owns grant/revocation, monotonically increasing authority version, actor/action/resource binding, signed or authenticated decisions, audit record. Gateway cannot edit authority state.
- **Capture gateway**: only approved path to Stripe capture; checks the independent service and binds the determination to the specific PaymentIntent, action, caller, and idempotency key. Gateway must not trust caller-supplied ALLOW or version.
- **Stripe sandbox**: external provider of truth for PaymentIntent state and capture acceptance.
- **Test coordinator**: injects deterministic barriers and revocation, controls scenarios but does not forge gateway decisions.
- **Evidence witness**: preserves ordered events, independent authority version, gateway dispatch attempt, Stripe request/response identifiers, provider final status, and uncertainty states.

A service running as another Python object in the gateway process does **not** qualify as independent.

## Required hostile cases

| ID | Interleaving | Expected qualification |
| --- | --- | --- |
| 004-A | Revoke before independent authority determination | Refuse, zero capture calls |
| 004-B | Revoke after determination but before dispatch | Refuse only if fresh revalidation detects revocation; record the tested barrier |
| 004-C | Revoke after dispatch but before Stripe accepts capture | Do not claim non-formation without provider-side coordination; preserve accepted/unknown/rejected actual outcome |
| 004-D | Capture accepted, then revoke | Provider consequence remains formed; compensation, if available, is separate |
| 004-E | Retry with same idempotency key after ambiguous timeout | Reconcile Stripe state; no invented refusal or success |
| 004-F | Retry with different idempotency key / alternate caller | Must prove mediation, deduplication, and route closure, or mark open |
| 004-G | Authority-service outage or stale witness | Fail closed for new dispatch; do not misclassify already in-flight provider result |
| 004-H | Tamper with caller-supplied authority version / receipt | Reject; obtain authority directly from trusted service |

## Evidence obligations

1. Pin source commit, environment and service revision; never publish credentials.
2. Capture independent authority state transition IDs and version numbers.
3. Correlate one payment intent, one proposed action, gateway decision, outbound Stripe request and final provider state.
4. Preserve original RED and remediate on a distinct branch.
5. Clearly separate **no dispatch**, **dispatch attempted**, **provider accepted**, **provider rejected**, **provider outcome unknown**, and **compensation**.
6. Publish SHA-256 artifact manifest and exact scope statement.

## Acceptance criteria

**PASS_BOUNDED** only if each tested interleaving satisfies its stated local/provider invariants with preserved evidence.  
**RED** if an unambiguously revoked pre-dispatch request is sent or accepted contrary to the specified gateway rule.  
**INCONCLUSIVE** for missing provider/authority evidence or ambiguous network outcome.  
**OPEN** for all unsupported routes or any unproven atomicity claim.

## Decision before implementation

Select the actual independent authority service deployment, durable state store, authenticated interface and gateway execution host. Do not substitute an in-memory authority variable and label it independent. Obtain approval of the architecture before giving GitHub Actions Stripe write access to a new implementation.

## Boundary statement

A fresh remote check can reduce or expose stale authority, but a revocation immediately after that check may still race a provider capture. Closing that window requires a defined commitment protocol or provider-side enforcement capability, not merely another check.
