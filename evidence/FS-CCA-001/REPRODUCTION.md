# FS-CCA-001 — Reproduction

## Environment

Run from the repository's `harness` directory. The checked-in virtual
environment currently has a broken Python launcher symlink, so the available
Python 3.12 runtime can load its installed packages explicitly:

```bash
PYTHONPATH=../.venv/lib/python3.12/site-packages \
python3 -m pytest -q -vv \
tests/test_fs_cca_001_constitutional_revocation.py
```

Expected result:

```text
5 passed
```

## Adjacent integration regression

```bash
PYTHONPATH=../.venv/lib/python3.12/site-packages \
python3 -m pytest -q \
tests/test_fs_cca_001_constitutional_revocation.py \
tests/test_fs_rai_integrated_payment_path.py \
tests/test_tcs001_coupled_capacity.py \
tests/test_fs_rai_execution_boundary_integration.py
```

Expected result:

```text
65 passed
```

## Independent reproduction status

These results were produced by the FlowSignal-authored harness. Independent
reproduction is invited and is not claimed until another party freezes the
artifact, runs it in a reviewer-controlled environment, and publishes the
commands and unedited output.

