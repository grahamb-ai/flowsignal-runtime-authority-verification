# TCS-001-GCP — Frozen Artifact Record

## Executable

- container image:
  `europe-west2-docker.pkg.dev/flowsignal-cage-phase-3/flowsignal-cage-phase3/flowsignal-phase4@sha256:71895f786df0219e64556aebef73d825abfb8dd88bb34b1372da733adeb4bfbc`
- Cloud Build ID: `b0566ffd-cc97-4298-a286-6b71fc1868ee`
- evidence ZIP SHA-256:
  `e9ce1efc4f020eb37238e367869dd6d6f9f514f7e0366b3a48ad4d1595370e25`

## Tested environment

- platform: Google Cloud Run
- project recorded in evidence: `flowsignal-cage-phase-3`
- region: `europe-west2`
- service: `flowsignal-cage-phase4-tcs001-candidate`
- tested revision: `flowsignal-cage-phase4-tcs001-candidate-00002-rwh`
- Firestore mode: Native, pessimistic concurrency
- Firestore location: `europe-west2`
- isolated evidence collection: `tcs001_candidate_concurrent_20261010`
- Cloud Run request concurrency: `1`
- warm instances during concurrent test: `2`
- maximum instances during test: `4`

The production service was not modified. The candidate was deployed as a
separate authenticated service and returned to zero minimum instances after
the run.

## Repository freeze

The repository commit containing the first public GCP review package is
recorded in `REPOSITORY_FREEZE.md`. The evidence ZIP contains the tested source,
requests, responses, durable-state snapshots, build metadata, revision
metadata, tests, and per-file SHA-256 manifest.

