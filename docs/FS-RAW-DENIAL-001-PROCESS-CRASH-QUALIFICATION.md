# FS-RAW-DENIAL-001 — Forced Process Exit Qualification

**3 November 2026 | Local reference scope only**

**Code baseline:** `main` remains frozen at `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`.  
**Challenge:** [Draft PR #44](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/pull/44).  
**Verified run:** [41600765638](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41600765638) — **2 passed / 0 failed**, 0.49s.  
**Existing public verification regression:** [41600765481](https://github.com/grahamb-ai/flowsignal-runtime-authority-verification/actions/runs/41600765481) — success.

## Test execution

A source-owned reference service holds authoritative version and synthetic consequence in one local SQLite database. The forwarding actuator and source run as separate loopback Python processes. A test-only SQLite connection intercepts `COMMIT` **only after the synthetic effect INSERT is pending** and terminates the source process either just before or just after the commit statement using distinct exit codes.

### Before-commit exit

- Source process exits with test code 91 before `COMMIT`.
- HTTP caller receives `COMMIT_OUTCOME_UNRESOLVED`, `formed=None`.
- Independent SQLite observer sees zero committed effect rows.
- Source restarts against the original database; authenticated outcome lookup returns `OUTCOME_NOT_RECORDED` with `formed=None`.
- Retry through the other actuator route records exactly one synthetic effect.

### After-commit exit

- Source process completes `COMMIT` then exits with test code 92 before returning an acknowledgement.
- HTTP caller receives `COMMIT_OUTCOME_UNRESOLVED`, `formed=None`.
- Independent SQLite observer sees exactly one committed effect row.
- Source restarts against the original database; authenticated outcome lookup returns `CONSEQUENCE_FORMED`.
- Retry through the other route returns `REPLAY_REFUSED`; exactly one effect remains.

## Interpretation and limitations

These two tests provide positive reference evidence that local effect state and replay classification survive **normal OS process termination** at the specified boundaries.

They do **not** establish safety against power loss, `fsync` failure, storage-controller cache loss, SQLite journal rollback, filesystem corruption, restored DB snapshots, cross-host failover, multi-writer replication, split-brain, clock/epoch rollback, remote payment execution or provider idempotency.

The authenticated outcome endpoint reads the same source-owned local database; the test inspects it independently, but no third-party outcome custodian or financial institution is involved. The SQLite effect represents a synthetic consequence and not an irreversible external act.

The test intentionally treats absence of a local row as **UNKNOWN for real-world formation**. A safe reference retry can be justified only within the single-source/single-ledger test trust assumptions.

The original missing-authority-delivery RED and upstream source-ownership gap remain open. None of these crash tests demonstrate an agent's inability to invoke other external actuators.

## Remaining qualification

- Two or more simultaneous retry clients across independent processes and routes.
- Crash/restart during multi-client contention and after uncertain transport completion.
- Journal rollback and restored-source state detection.
- An actuator/provider-owned independent consequence witness and real external commit/idempotency semantics.

**Prevention: NOT ESTABLISHED. No frozen-baseline modification or merge.**
