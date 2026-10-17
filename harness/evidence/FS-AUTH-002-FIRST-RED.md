# FS-AUTH-002 — first RED (immutable evidence reference)

- Classification: CONFIRMED RED, bounded Python reference harness; not a production exploit.
- First-run candidate commit: `ad7113c4d42454b4122afc1b27db3453daed56a8`.
- GitHub Actions artifact: `fs-auth-002-first-run-ad7113c4d42454b4122afc1b27db3453daed56a8`.
- ZIP SHA-256: `5badf1fa0ba3719ee2c38f440a5d0454881f1ac13a45f86312c7aba4645c354b`.
- Environment: Python 3.13.16, pytest 9.1.1; isolated run, 1 failed in 0.14s.
- Observed: genuine RAI-bound permit, initial final-bind PERMITTED, institutional authority fence 1 -> 2 in before_formation_hook, then CONSEQUENCE_FORMED.
- Expected: no protected consequence formed after the authoritative fence transition.
- Exact failure: `FS-AUTH-002 FIRST RED: authority fence changed (1 -> 2) inside commitment interval but outcome=CONSEQUENCE_FORMED`.

Do not rewrite the original challenge or replace the original evidence. Any GREEN is a subsequent remediation result. A local SQLite reference-model result does not prove production distributed enforcement.
