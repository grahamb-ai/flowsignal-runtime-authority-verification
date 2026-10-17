# FS-AV-001 — Reproduction

From `harness/`, with the repository test dependencies available:

```bash
PYTHONPATH=. python -m pytest -q tests/test_fs_av_001_conflicting_hazard.py -vv
```

Run the reference model and CARLA adapter contract together:

```bash
PYTHONPATH=. python -m pytest -q \
  tests/test_fs_av_001_conflicting_hazard.py \
  tests/test_fs_av_001_carla_adapter.py -vv
```

Candidate implementation:

- `harness/app/engines/autonomous_vehicle_boundary.py`
- `harness/app/engines/carla_vehicle_boundary.py`
- `harness/scripts/run_fs_av_001_carla.py`

Frozen tests:

- `harness/tests/test_fs_av_001_conflicting_hazard.py`
- `harness/tests/test_fs_av_001_carla_adapter.py`

The evidence result must be interpreted with `DECLARED_CLAIM.md` and its
explicit non-claims. See `CARLA_INTEGRATION.md` for the live-run boundary.
