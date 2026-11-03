# FS-RAW-DENIAL-001 — Independent Witness and Stranded-Commit Recovery

**Date:** 3 November 2026. **Scope:** Synthetic single-host reference. **Production prevention: NOT ESTABLISHED.**

## Evidence

1. [PR #54: dual-store restore FIRST RED](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/54), [CI 41605548615](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41605548615): **1 intentional failure**. Two local source stores were rolled back; a third test-owned witness preserved two accepted consequences.
2. [PR #55: independent consequence witness](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/55), [CI 41605887179](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41605887179): **3 passed**. Separate localhost witness process and SQLite DB refused a second modeled external consequence after both local stores were restored. Missing witness classified as UNRESOLVED, not nonformation. Separate witness caller credential required.
3. [PR #56: stranded external commitment FIRST RED](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/56), [CI 41606174210](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41606174210): **1 intentional failure**. The local authority committed while witness was down. After witness restart, local replay refusal prevented the outstanding modeled external effect from completing; local record existed but witness record remained empty.
4. [PR #57: bounded stranded commitment recovery](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/57), [CI 41606478976](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41606478976): **2 passed** in 1.24s. Reference recovery first checks a genuine signed permit, authenticated local source outcome for exactly the same action binding, and currently published source authority version. After such checks, a previously consumed local permit may complete **one** synthetic external witness effect. When the source version has advanced, recovery is refused.
5. [Existing public baseline CI 41606479016](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41606479016): successful. Frozen `main` remains `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`, unchanged.

## Important interpretation

This is a **bounded reconciliation demonstration**, not a production-grade, universally safe recovery protocol. Local source commitment and independent witness formation remain two HTTP operations, two trust domains and two durable stores. Their relative ordering and visibility can diverge. A final authority-version read can become stale before witness commit. The witness does not itself verify current institutional authority, and the test bridge's HMAC signer and service tokens are trusted fixture credentials, not independently controlled production infrastructure.

The candidate does not prove one-and-only-one external financial payment, absence of a competing direct route, cross-host idempotency, exact once under network partition, rollback resistance for all stores, power-loss durability, or correct treatment of a provider that forms a consequence but loses its own receipt.

No actual agent, real shell-command encoding, financial institution, payment rail, cloud external actuator or third-party consequence custodian was exercised.

## Next gate

Make the **independent witness's authority to form a consequence** and its current-state check causally inseparable at the externally controlled commitment boundary. Test revocation between recovery preflight and actual witness commit, concurrent recoveries, lost witness acknowledgement and witness database restoration.

**Disposition:** Dual-local-restore RED and stranded-commit RED preserved; third-witness candidate GREEN (3/3); bounded recovery candidate GREEN (2/2); real external atomicity and production prevention **NOT ESTABLISHED**.
