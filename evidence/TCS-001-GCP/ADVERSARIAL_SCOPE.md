# TCS-001-GCP — Adversarial Review Scope

Qualified reviewers may introduce new inputs and changed conditions within the
declared final-bind claim. Reviewers are not restricted to the supplied cases.

## In scope

- sequential and concurrent movements sharing one capacity key;
- burdens below, equal to, and above the remaining capacity;
- replay of identical execution identities;
- mutation of amount or capacity-relevant material under a reused execution
  identity;
- different request ordering and concurrency schedules;
- process restart and Cloud Run scale-out;
- malformed or missing capacity state;
- authoritative-capacity changes and version-window changes;
- attempts to obtain an execution permit after capacity refusal; and
- counterexamples showing durable aggregate burden exceeding capacity.

## Submission requirements

Provide:

1. exact repository commit and image digest tested;
2. environment and dependency versions;
3. declared property challenged;
4. new input or changed condition;
5. expected and actual results;
6. complete commands and output;
7. whether a reservation or execution permit was issued;
8. durable-state evidence where applicable; and
9. SHA-256 hashes for submitted artifacts.

## Safety boundary

This package does not authorise probing FlowSignal-hosted services, accounts,
credentials, data, payment rails, or third-party infrastructure. Reproduction
must use the published local artifact or a reviewer-controlled cloud project.

