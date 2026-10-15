# FS-CCA-001 — Preserved Result

## Case matrix

| Case | Condition | Observed result | Classification |
| --- | --- | --- | --- |
| 01 | Current authority | Permit issued; `CONSEQUENCE_FORMED` | PASS |
| 02 | Authority changes before final bind | `AUTHORITY_CONTEXT_CHANGED`; no permit; no formed consequence | PASS |
| 03 | Stale prepared authority replayed | Both binds blocked; no permit; no formed consequence | PASS |
| 04 | Protected operation mutated | `PROTECTED_OPERATION_CHANGED`; no permit; no formed consequence | PASS |
| 05 | Authority changes after permit mint | `DENIED_AUTHORITY_SNAPSHOT_STALE`; no formed consequence | PASS within bounded harness |

Case 05 also records `CONSEQUENCE_OUTCOME_UNRESOLVED` when the permit is
durably consumed, and a repeated use is classified
`DENIED_EXECUTION_PERMIT_REPLAY`. That is preserved as an implementation fact;
this result does not misdescribe the denial as an unconsumed permit.

## Test results

- Candidate cases, forward order: `5 passed`.
- Candidate cases, reverse order: `5 passed`.
- Candidate plus final-bind, coupled-capacity, and execution-boundary
  integration tests: `65 passed`.
- Candidate followed by the authoritative-state sentinel and adjacent suites:
  `12 passed`.

## Repository-wide suite disclosure

The repository-wide suite is not order-isolated. With this candidate included,
the run completed with `116 passed, 27 failed`. Excluding the candidate file,
the same run completed with `111 passed, 27 failed`, with the same failure
set. The failures arise after older tests mutate shared epoch and compatible
source-generation state. Therefore no repository-wide green-suite claim is
made, and those failures are not counted as FS-CCA-001 passes.

## Conclusion

FS-CCA-001 supports the frozen, bounded proposition for the tested process:
authority changed before final bind does not receive a permit or form the
represented protected consequence. The after-mint race is separately stopped
at the protected boundary. Restart persistence, independent reproduction, and
distributed operation remain unproven.

