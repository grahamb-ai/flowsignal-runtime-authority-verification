# FS-XTD-001 remediation result

Date: 2026-10-11

## Result

The preserved RED exposed a real gap in the bounded reference harness: an
execution permit could remain usable after the enrolled external authority
issuer had issued a current revocation.

The narrow remediation adds an explicit cross-domain authority observation
adapter and binds its verified state into permit issuance and consequence
formation. Within the represented execution boundary:

- a confirmed, authentic and current revocation returns
  `DENIED_CROSS_DOMAIN_AUTHORITY_REVOKED`;
- enrolled but unresolved external authority does not mint a permit;
- a change to the externally bound authority epoch prevents use of an older
  permit;
- forged observations, rollback/replay, delegation-scope expansion and an
  implicit transfer to another issuer domain are rejected.

This is evidence that the reference execution boundary refused the represented
consequence. It is not evidence about an uninstrumented downstream system or a
production deployment outside this harness.

## Focused hostile tests

Command:

```text
.venv/bin/python -m pytest -q tests/test_fs_xtd_001_cross_domain_revocation.py
```

Result:

```text
7 passed in 0.08s
```

The seven cases cover:

1. confirmed fresh revocation before consequence formation;
2. forged revocation;
3. unresolved enrolled authority;
4. downstream action-scope expansion;
5. implicit cross-domain issuer transfer;
6. resurrection of a permit after a newer authority epoch;
7. rollback/replay of an older authority epoch.

## Incumbent regression checks

Eight selected incumbent authority, lineage, payment, final-bind and public
receipt test files were run in clean processes. Result: 54 passed.

The execution-boundary integration file produced 55 passed and one deliberately
retained RED: `FS-FMK-001`, the pre-existing duplicate-consequence challenge.

The repository-wide single-process run moved from the pre-remediation baseline
of 112 passed / 25 failed to 116 passed / 28 failed. The three apparent added
failures are FS-XTD cases affected by the repository's pre-existing mutable
reference-state leakage between test modules; all seven FS-XTD cases pass in a
clean process. The original 25 failures, including the deliberately retained
RED and order-dependent state failures, remain outside this remediation.

## Declared boundary

This harness models independently enrolled issuer keys, signed observations,
freshness, monotonic epochs, bounded delegation lineage, policy/evidence
identifiers and a represented execution boundary. It does not establish a
production trust federation, key lifecycle, consensus protocol, external
witness availability or enforcement in systems that can bypass the represented
boundary.
