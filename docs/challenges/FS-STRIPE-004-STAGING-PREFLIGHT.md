# FS-STRIPE-004 — Staging qualification gate

Status: **BLOCKED PENDING DEPLOYED AUTHORITY EVIDENCE**  
Date: 2026-10-18  
Target candidate: FlowSignal Google Cloud staging (CAGE integration)

## Known candidate

Previously recorded staging service: `https://flowsignal-cage-phase3-staging-jtw7fsky5a-nw.a.run.app`. Historical revision `-00005-8mp`; these are not proof of the currently deployed revision, route contract, or current authority persistence. Do not send Stripe credentials to this endpoint.

Existing repository code includes authority-state and execution-gateway constructs; repository source is not evidence of the active deployed revision.

## Mandatory preflight before provider execution

1. Obtain current Cloud Run service revision, container digest and immutable deployment evidence.
2. Identify a *documented, authenticated* determination endpoint and request/response contract; confirm whether it can determine authority for a Stripe PaymentIntent capture and bind actor, action, resource, idempotency key, authority version and freshness.
3. Verify the authority store is independently writable only by a trusted authority administrator; provide durable backing store and monotonic version transition evidence across restarts.
4. Verify a separate, authenticated revocation API or controlled administrative mechanism and a test-only grant; no production authority mutations.
5. Verify that the gateway obtains trusted authority directly, rejects caller-supplied decisions, and mediates all supported Stripe capture paths.
6. Establish whether provider dispatch can be coordinated with revocation, and specify the point of no return. If not, explicitly record the unresolved distributed race.
7. Use separate credentials for the authority service and the existing restricted Stripe sandbox key. Keep both in GitHub environment secrets; never log or commit them.
8. Define independent event and provider evidence correlation, provider outcome reconciliation and artifact retention.

## Hold points

**Do not** deploy a guessed endpoint, assume a public staging URL is an authenticated authority service, use a locally simulated authority version as proof of independence, or trigger Stripe write operations from FS-STRIPE-004 until the above preflight is qualified.

## Decision record

Proceed with existing staging **only if** the deployed independent authority and persistence contract can be verified. Otherwise use a dedicated isolated authority service with persistent storage and separately authenticated administrative revocation; treat that as a new engineering implementation, not an already qualified FlowSignal deployment.

Next state: **AWAITING DEPLOYMENT CONTRACT / REVIEW**.
