# FS-XTD-001 — Preserved First RED

## Frozen proposition

One trust domain must not be able to implicitly grant, expand or resurrect
authority on behalf of another.

## Frozen scenario exercised

- Domain A issues and then revokes authority.
- Domain B supplies policy.
- Domain C witnesses supporting evidence.
- Domain D controls the represented execution boundary.
- The original permit is minted before revocation.
- Domain A then emits a signed, current revocation for that exact authority.
- Domain D independently verifies the reference revocation fixture's
  authenticity and freshness before the old permit is presented.

## Baseline

- Repository: `grahamb-ai/flowsignal-runtime-authority-verification`
- Branch: `challenge/fs-fmk-003-consequence-state-candidate`
- Commit: `638b4248e81381e99ebdaefc7298de165747211e`
- Test: `harness/tests/test_fs_xtd_001_cross_domain_revocation.py`

## Command

```text
.venv/bin/python -m pytest -q tests/test_fs_xtd_001_cross_domain_revocation.py
```

## Preserved result

```text
FAILED test_confirmed_fresh_cross_domain_revocation_must_prevent_consequence
FS-XTD-001 RED: Domain D formed the consequence after an independently
authentic and fresh Domain A revocation because the execution boundary has no
cross-domain revocation-consumption seam
1 failed in 0.07s
```

Observed outcome: `CONSEQUENCE_FORMED`.

Expected outcome for confirmed revocation: `REFUSE` / no consequence formation.

## Classification

**RED — CROSS-DOMAIN REVOCATION NOT CONSUMED AT THE REPRESENTED EXECUTION BOUNDARY**

The existing local reference controls validated the permit against their local
current state, but had no seam through which the independently verified Domain A
revocation could alter that state before execution.

This result is bounded. It demonstrates a missing cross-domain revocation
ingestion and reconciliation mechanism in this reference harness. It does not
invalidate the already-declared local-boundary controls, and it does not by
itself make a production-system claim.

## Determination versus prevention

The result is stronger than a decision-only discrepancy because the represented
execution boundary returned `CONSEQUENCE_FORMED`. Conversely, the harness result
is not evidence about any external payment rail, actuator or production system.

No remediation had been applied when this record was created.
