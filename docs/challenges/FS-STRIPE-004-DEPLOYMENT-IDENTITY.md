# FS-STRIPE-004 — Cloud Run staging deployment identity

Date: 2026-10-18  
Status: **REVISION AND IMAGE IDENTIFIED; INDEPENDENT AUTHORITY NOT YET QUALIFIED**

- Google Cloud project: `flowsignal-cage-phase-3`
- Cloud Run service: `flowsignal-cage-phase3-staging`
- Revision observed in Cloud Console: `flowsignal-cage-phase3-staging-00005-8mp`
- Region: `europe-west2`
- Container image: `europe-west2-docker.pkg.dev/flowsignal-cage-phase-3/flowsignal-cage-phase3/flowsignal-cage-phase3@sha256:ec26099cf1ee11aa1491ef14f716acd84d87dccc0ba3c59fca0a6e0f9fc80929`
- Console configuration observed: request concurrency 80; maximum instances 3; 512 MiB memory; bearer-required application configuration; bearer token referenced from Google Secret Manager; no mounted volumes.

## Evidence classification

These values were transcribed from the owner's Cloud Run Console observations. The image digest identifies the container artifact associated with the inspected revision. Active traffic percentage, deployed source provenance, authenticated endpoint contract, external durable state, monotonic version semantics, revocation interface and transaction coordination have **not** been verified.

Do not confuse a configured bearer-token requirement with proof of application-level authorization or tenant isolation. Do not infer absence of external persistence from zero mounted volumes.

## Next checks

1. Inspect service Revision history for active traffic routing to this revision.
2. Obtain documented API contract for the deployed image (not a guessed path).
3. Determine whether the deployed service reads/writes durable authority state outside its process, and whether revocation can be independently administered.
4. Verify access controls and evidence for monotonic authority versions across multiple instances.
5. Only then design a test-only Stripe capture gateway using a separate credential boundary.

**No FS-STRIPE-004 Stripe capture is authorized by this record.**
