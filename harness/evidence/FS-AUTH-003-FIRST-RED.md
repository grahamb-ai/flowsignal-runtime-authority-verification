# FS-AUTH-003 — preserved first RED

- Original hostile challenge commit: `2083b2339c563c1b1f1d42a4dbe827c84d5f31dc`.
- Original GitHub Actions workflow: `.github/workflows/fs-auth-003.yml` on `challenge/fs-auth-003-global-version-commit-race`.
- Original outcome: global authority state 1 -> 2 in commitment hook, yet `CONSEQUENCE_FORMED`.
- Test summary: 1 failed in 0.10s; `FS-AUTH-003 FIRST RED` assertion.
- Original evidence artifact retained by GitHub Actions; its SHA-256 has not yet been independently verified.

The remediation must not replace or reinterpret this original failure. The test is an injected, re-entrant same-thread state transition in a bounded Python reference model. It is not a demonstrated multi-process or production exploit.
