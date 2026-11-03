# FS-RAW-DENIAL-001 — First-Evidence Characterisation (3 November 2026)

**Baseline pinned:** `1cfeffa10b9cf2109a11ecbdd0a9a4fd7dd606c0`
**Scope:** Existing reference `execution_gateway.validate_execution`, without enforcement changes. This is NOT proof that FlowSignal would have prevented the reported Claude Code incident.

## Matrix
| ID | Test exercised | What remains untested |
|---|---|---|
| D01 | Altered `action` field vs signed binding | Decoded command semantics and same-effect re-encodings |
| D02 | Altered `target` field vs receipt | Same consequence through another actual executor/tool |
| D03 | Bad receipt integrity rejected | Agent-writable instruction file becoming authoritative |
| D04 | Stale authority version rejected after simulated update | Persisted instructions across real sessions, independent source authenticity |
| D05 | Fresh versioned ALLOW accepted by reference gateway | Real authorisation issuance, permit signing and protected consequence formation |
| Retry | Repeated explicit REFUSE receipts rejected | External rate limits and downstream route closure |

## Limitations and next evidence gate
Integrity verification, state version and permit mint are **test doubles** in this bounded gateway test. A `BLOCKED` result is not evidence that no external consequence formed. An `ALLOW` result is not evidence that a downstream consequence formed. No actual agent, encoded shell, alternate tool, persistence store, external executor or protected consequence was exercised.

**OPEN:** Construct a genuine end-to-end hostile route where the same execution target and operation can be invoked using two adapters, including an encoding transformation, while policy/authority is independently supplied. Require a reliable outcome witness and preserve first RED before remediation. Do not change the frozen baseline.

**Prevention: NOT ESTABLISHED.**
