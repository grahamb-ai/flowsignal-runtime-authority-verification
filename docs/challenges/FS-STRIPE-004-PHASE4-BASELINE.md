# FS-STRIPE-004 — Phase 4 baseline correction

Date: 2026-10-18  
Status: **PHASE 4 STEP 1 BASELINE IDENTIFIED; STRIPE INTEGRATION NOT YET QUALIFIED**

## Authoritative public partner record

Google CAGE: `docs/partners/provider_01/CAGE_FLOWSIGNAL_PHASE3_STEP1_RECORD.json` (public Google repository).

- Step 1 exercised FlowSignal deployment: `flowsignal-cage-phase4-staging`
- Revision: `flowsignal-cage-phase4-staging-00001-8nr`
- Region: `europe-west2`
- Candidate adaptation commit: `ea836ab023cc63d966e23f5f3ba481041138998e`
- Image digest: `sha256:d681fd2df24f4585ac40c43a76c1eb73ffb7bdb7611f67d4ba2a717cd43d951d`
- Preflight file: `run_phase4_live.json`; SHA-256 `5e4966ca5f101ed4181241b6970240c4cefccf645fe44c59ce269f23be167141`
- Joint conformance: 6 cases, 21 subcases, 6 passed, 0 failed.
- Composition invariant reported: `EXECUTED => CAGE_GOVERNANCE_ALLOW && FLOWSIGNAL_RUNTIME_AUTHORITY_ALLOW`.
- CAGE code seams: `src/gateway/governance/consequence_gateway.py`, `execution_actuator.py`, `consequence_authority_store.py`, `consequence_token.py`.

## Critical distinctions

This record explicitly distinguishes the frozen Phase 3 37-field wire contract from the Phase 4 Step 1 enforcement path. The older `flowsignal-cage-phase3-staging-00005-8mp` is not the strongest exercised deployment.

Step 1 evidence does not establish the currently deployed Phase 4 revision, the latest Step 2 adapter/receipt implementation, independently persisted and revocable authority across multiple instances, or atomicity with Stripe capture. None of those properties should be inferred from the recorded GREEN cases.

## Next qualification gates

1. Inspect Step 1 case results and relevant CAGE consequence/actuator source.
2. Locate the Step 2 candidate at commit `ea836ab...` and compare its current HEAD with the frozen qualification baseline.
3. Determine the actual independent authority persistence and revocation contract; identify the deployed revision currently receiving traffic.
4. Bind a test-only Stripe PaymentIntent capture to a trusted authority decision and provider outcome, with no caller-supplied ALLOW.
5. Preserve FS-STRIPE-003 RED and GREEN as earlier provider evidence, not proof of distributed commit.

**No Stripe write action is authorised by this record.**
