# TCS-001-GCP — Reproduction Guide

## 1. Verify the evidence archive

```bash
sha256sum TCS001-GCP-COUPLED-CAPACITY-EVIDENCE.zip
```

Expected:

```text
e9ce1efc4f020eb37238e367869dd6d6f9f514f7e0366b3a48ad4d1595370e25
```

Extract it and verify the internal manifest:

```bash
unzip TCS001-GCP-COUPLED-CAPACITY-EVIDENCE.zip -d tcs001-evidence
cd tcs001-evidence
sha256sum -c TCS001-FINAL-SHA256.txt
```

Every listed file must report `OK`.

## 2. Reproduce the bounded container tests

From the extracted evidence directory:

```bash
docker build -t flowsignal-tcs001-review .
docker run --rm \
  -e PYTHONPATH=/srv/flowsignal \
  flowsignal-tcs001-review \
  pytest -q \
  tests/test_tcs001_coupled_capacity.py \
  tests/test_tcs001_final_bind_api.py
```

Expected result:

```text
6 passed
```

## 3. Reproduce in a reviewer-controlled cloud project

The reviewer must use their own authenticated project and secrets. Do not test
the FlowSignal-hosted candidate.

Required characteristics:

1. build the supplied Dockerfile without altering the test or claim;
2. deploy the resulting immutable digest to a separate Cloud Run service;
3. configure Firestore Native mode in the same region;
4. configure `FLOWSIGNAL_CAPACITY_BACKEND=firestore`;
5. use an isolated `FLOWSIGNAL_CAPACITY_COLLECTION`;
6. retain authenticated access and application-level bearer protection;
7. submit two distinct 600,000 movements concurrently against one
   authoritative 1,000,000 capacity scope; and
8. preserve requests, responses, revision metadata, durable Firestore state,
   and SHA-256 hashes.

The pass condition is exactly one successful reservation and permit, exactly
one capacity refusal, and a durable total no greater than 600,000.

## Independent reproduction status

The FlowSignal-authored GCP result is preserved. Independent reproduction is
invited and is not claimed until a third party repeats the run and publishes
their environment, commands, outputs, and hashes.

