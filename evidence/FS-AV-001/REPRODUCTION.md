# FS-AV-001 — Reproduction

From `harness/`, with the repository test dependencies available:

```bash
PYTHONPATH=. python -m pytest -q tests/test_fs_av_001_conflicting_hazard.py -vv
```

Candidate implementation:

- `harness/app/engines/autonomous_vehicle_boundary.py`

Frozen tests:

- `harness/tests/test_fs_av_001_conflicting_hazard.py`

The evidence result must be interpreted with `DECLARED_CLAIM.md` and its
explicit non-claims.
