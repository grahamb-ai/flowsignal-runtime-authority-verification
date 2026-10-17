# FS-OUTBOX-001–004 — Engineering review record

**Status:** REVIEW CANDIDATE — NOT PRODUCTION QUALIFIED.  
**Repository:** grahamb-ai/flowsignal-runtime-authority-verification  
**Reference candidate:** `a5a076814afad78b657aae2acc206bd565aca91b` (FS-OUTBOX-004 workflow commit).  
**Review owner:** Alan / Hugo when available. **Do not merge without explicit approval.**

## Scope and observed evidence

| ID | Tested boundary | Observed CI result | Interpretation |
|---|---|---|---|
| FS-OUTBOX-001 | Authority revoked after enqueue, before simulated worker execution | GREEN | Reference worker blocks an already-revoked queued proposal |
| FS-OUTBOX-002 first RED | Revocation after local `CONSEQUENCE_FORMED` but before simulated external dispatch | 2 RED | Local outcome alone is insufficient to authorise later external dispatch |
| FS-OUTBOX-002 remediation | Read-only global/fence checks at simulated dispatch | GREEN | Addresses the two fixed pre-dispatch revocation schedules, not an atomic external call |
| FS-OUTBOX-003 first RED | Revocation after dispatch gate returns ALLOW but before actuator call | 2 RED | Separate check-then-call retains a TOCTOU gap |
| FS-OUTBOX-004 | Reference actuator owns local authority-to-formation critical section | GREEN | Six bounded in-process scenarios pass; not external/provider atomicity |

The FS-OUTBOX-003 original RED remains **unresolved for the check-then-call worker design**. FS-OUTBOX-004 is a separate local actuator reference pattern, not proof that a real remote actuator shares the authority lock.

## Reproducible sources

- FS-OUTBOX-001: `challenge/fs-outbox-001-revocation-before-dispatch`, workflow `fs-outbox-001.yml`.
- FS-OUTBOX-002 original RED: `challenge/fs-outbox-002-post-commit-dispatch-race`, workflow `fs-outbox-002.yml`.
- FS-OUTBOX-002 correction: `remediation/fs-outbox-002-dispatch-gate`, workflow `fs-outbox-002-remediation.yml`.
- FS-OUTBOX-003 original RED: `challenge/fs-outbox-003-check-actuation-race`, workflow `fs-outbox-003.yml`.
- FS-OUTBOX-004 reference actuator: `challenge/fs-outbox-004-actuator-enforced-commit`, workflow `fs-outbox-004.yml`.

The GitHub Actions artifacts retain the logs. Reviewers must pin run IDs, source SHAs and independently calculate artifact SHA-256 digests before using this as a frozen evidentiary record.

## Required architecture decision

Define which component actually controls the external consequence. A queue commit, local `CONSEQUENCE_FORMED` marker, outbox dequeue or local authority recheck is **not** the remote payment/API consequence.

Production qualification requires an enforceable boundary at or within the actuator/provider (or a clearly specified alternative protocol) with:
1. Authoritative and current WHO/WHAT/NOW/MATCH binding at the actual actuation point.
2. A well-defined linearisation/acceptance point and revocation ordering.
3. Durable idempotency and retry rules across crash/restart and concurrent workers.
4. Explicit distinction among queued, admitted, dispatched, accepted, settled, refused and outcome-unknown states.
5. Handling of timeouts and ambiguous remote acceptance without claiming non-formation.
6. Recovery and monotonic evidence that survive relevant failure/rollback models.
7. Tests with a genuinely independent remote executor and network failures; process-local `RLock` cannot provide distributed atomicity.

## Mandatory review questions

- Is the reference actuator's global→institutional lock order consistent with every authority transition and usage path?
- Can a privileged, independent or remote authority source mutate without participating in those guards?
- What is the meaning of `CONSEQUENCE_FORMED` in the existing reference harness versus external acceptance?
- How are duplicate dispatch, replay, cancellation and post-acceptance revocation handled?
- Can evidence prove whether an external effect occurred after a timeout?
- Which exact provider-side integration would make the final authority check enforceable?

## Review disposition

**HOLD**: no production guarantee, no external-provider enforcement, no claim of distributed compare-and-set, no automatic merge to `main`. Retain all REDs and passing bounded tests.
