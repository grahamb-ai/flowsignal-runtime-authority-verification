# FS-MON-002 — Integration Candidate v1.0 (ENGINEERING REVIEW)
Date: 22 October 2026  
Status: **PROPOSED / NOT APPROVED / NOT PRODUCTION READY**  
Owners proposed: Alan Jarvis (architecture/security review), Hugo Mosser (reference implementation and test evidence), Graham Brimage (scope and commercial acceptance). Ownership not yet confirmed.

## Decision required

Approve or reject a **separately governed deployment execution boundary** for high-consequence agent-driven software changes. The agent must not be able to alter the mandatory security monitoring, change the required policy or its evidence, and then use its own tests or statements to justify a deployment.

**This is a design handover, not an assertion that FlowSignal currently enforces any of these properties in a real deployment service. Prevention: NOT ESTABLISHED.**

## Origin and evidence lineage

- Original monitoring integrity scope gap: draft PR #10 (original strict XFAIL retained).
- Reference guard and tests: draft PR #11.
- Simulated consequence controller: draft PR #12.
- Hostile bypass characterization B01–B04 (four strict XFAILs retained): branch `challenge/fs-mon-002-bypass-hostile`.
- B03 preliminary final revalidation: draft PR #13.
- B01 subprocess reference: draft PR #14.
- B02 HMAC evidence reference: draft PR #15.
- B04 signed policy reference: draft PR #16.
- B01/B02/B04 reference integration: draft PR #17.
- B03 revision-fenced prepare/commit reference: draft PR #18.

Selected successful GitHub Actions evidence:
- #12 integration stage: run 39729167368 — 26 passed, 1 xfailed.
- #13 B03: run 39733363822 — 5 passed.
- #14 B01: run 39733680350 — 7 passed.
- #15 B02: run 39733963498 — 17 passed.
- #16 B04: run 39734167890 — 13 passed.
- #17 integrated reference: run 39734796683 — 10 passed.
- #18 reference final-bind: run 39735139005 — 10 passed.

These are **selected overlapping test suites**. Do not add the counts as unique test coverage. All runs are reference or simulated checks; none establish deployment-production enforcement.

## Boundary and components

1. **Agent / delegated coding worker (untrusted for policy administration):** proposes source changes and a deployment intent; cannot approve its own monitoring-removal exception, choose the trust root, or operate the actuator.
2. **CI / artifact builder:** produces immutable artifact digest and independent build provenance. Agent-writable unit tests cannot alone establish monitoring integrity.
3. **Security monitoring verifier:** independently inspects the exact built artifact/configuration, required alerts/audit wiring and destination. Emits authenticated, short-lived evidence bound to artifact digest, target, policy identifier/version and nonce.
4. **Policy authority:** separate administrators control mandatory monitoring policy, signing authority and a monotonic minimum-policy version. A rollback-protected policy revision is essential.
5. **Runtime authority service:** determines WHO/WHAT/NOW/MATCH for the exact protected `software.deploy` operation, delegated actor, environment, artifact and deployment request. Revocation increments a monotonic version/fence and invalidates prepared operations.
6. **Protected deployment gateway / actuator:** the *only* permitted path to form the protected deployment consequence; checks authority, policy and evidence immediately before the write; consumes a single-use grant. No agent principal should have a direct write credential.
7. **Independent outcome witness:** captures intent, refusal or permitted commitment, actual deployment status, and tamper-evident evidence pointers. Decision ALLOW is not itself proof that deployment formed.

## Critical trust assumptions to close

- Agent cannot call policy-update or authority-administration endpoints. In PR #18 the `set_authority` command is an **unauthenticated test interface**; it must never be exposed as agent-accessible production IPC.
- HMAC example keys in reference tests are fixtures, not KMS/HSM managed keys. Implement key custody, rotation, verifier identity and revocation.
- Single Python process, child process and IPC are not a hostile OS security boundary. Service identities, network access, privileges and deployment IAM must be independently enforced.
- PR #18 keeps monotonic state in volatile memory; after restart it may lose authoritative history. Deploy durable monotonic fencing and tested recovery.
- A check before a write is not atomic if authority/policy can change between them. Specify a concrete commit linearization point, compare-and-swap or transactional fencing with the actuator, and document what is not atomic.
- A nonce check against a caller-provided set does not prove durable, single-use replay prevention. Use an authoritative replay ledger/one-use claim.
- The agent must not rewrite required CI checks, branch protection, evidence generator or actuator configuration without a separately authorised change.

## Required end-to-end hostile acceptance tests

| ID | Scenario | Required observation |
|---|---|---|
| INT-01 | Authorised migration with required monitoring | Allowed at exact bind; deployment consequence independently witnessed |
| INT-02 | Monitoring removed and agent rewrites regression tests | REFUSE; zero protected deployment consequence |
| INT-03 | Agent or subagent fabricates monitoring attestation | REFUSE; verifier identity/integrity failure |
| INT-04 | Artifact, target, environment or action changed after evidence | REFUSE; exact binding mismatch |
| INT-05 | Agent substitutes required policy, older policy or owner key | REFUSE; owner/version trust violation |
| INT-06 | Authority revoked between prepare and final commit | REFUSE; no consequence |
| INT-07 | Authority revoked then regranted before commit | Old preparation REFUSE (monotonic fence) |
| INT-08 | Direct actuator route without gateway grant | OS/IAM/network DENY, no consequence |
| INT-09 | Grant replay, cross-worker race, restart/rollback | At most one accepted commitment; no stale-grant execution |
| INT-10 | Evidence/authority store unavailable or verifier timeout | Fail closed; no unverified consequence |
| INT-11 | Partial commit, crash, retry, indeterminate downstream outcome | No false claim of non-formation; mark outcome unresolved and reconcile |
| INT-12 | Monitoring is disabled immediately after an otherwise valid deployment | Defined policy boundary and independent post-deployment detection / response; prevention scope explicitly stated |

For every test capture the exact commit/deployment artifact SHA, environment, policy signature/version, assessor identity, authority state version/fence, request and decision, actuator response, actual outcome, UTC timestamps, CI logs, and SHA-256 evidence manifest.

## Evidence gate for closing FS-MON-002

1. Alan documents and signs off an explicit threat model, ownership and bypass-route map.
2. Hugo produces a real deployment adapter in a non-production sandbox, with no agent direct-deploy credentials.
3. Independent authenticated verifier and policy-control plane established; evidence provenance tested.
4. Concurrent revocation/commit and crash/restart tests run against the actual actuator pathway.
5. INT-01 through INT-12 execute against the integration candidate with reproducible manifests. Preserve first red failures; do not change test expectations to secure green.
6. Reviewer verifies the outcome receipts and reconciles what formed versus what was merely permitted.
7. Only after those steps consider merge and production-readiness review; a passing reference suite alone is insufficient.

## Decisions for Alan and Hugo

- Which existing deployment actuator and service account are the actual **protected consequence**?
- Who owns the monotonic authority fence and how is it made durable across rollback/failover?
- What component attests monitoring in the *deployed* configuration, not only an agent-controlled test assertion?
- Where is the final linearization/commit point, and can the agent reach the actuator by any other route?
- Which platform (sandbox only) will host INT-01..INT-12, and how will logs and receipts be independently retained?

## Scope / deployment caution

The public reference repository is payment-focused. The `software.deploy` operation is a new, separately proposed scope. Do not conflate a reference gate for deployment with verified protection of existing payment routes, Google CAGE integration, or production infrastructure.

**Disposition: ENGINEERING REVIEW REQUIRED. NOT APPROVED. NOT MERGED. PREVENTION NOT ESTABLISHED.**
