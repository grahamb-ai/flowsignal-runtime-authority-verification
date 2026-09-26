# FlowSignal™ Public Verification Challenge — v0.1

## Purpose

This challenge invites independent reviewers to try to falsify the bounded runtime-authority properties declared in the public verification candidate.

It is not a bug bounty, penetration-testing authorisation, production certification exercise or invitation to test FlowSignal infrastructure or third-party systems.

The permitted scope is the published reference implementation and its local test harness.

## The proposition

**WHO → WHAT → NOW → MATCH = B4 ACT**

Immediately before protected consequence formation:

- **WHO** — is the authority holder established?
- **WHAT** — does the authority cover the proposed action?
- **NOW** — does the authority remain valid at this point in time and state?
- **MATCH** — does this exact execution correspond to the authority, determination, constraints and execution material that were validated?

The strongest useful challenge is a reproducible case where protected consequence forms despite a required relationship not holding.

## Frozen reference

Engineering checkpoint:

`257d28cd6171475afd6b6b37b2db2a954399939b`

Published candidate branch:

`public-verification-candidate-v0.1`

Frozen selected regression baseline:

`124 passed`

## In scope

Reviewers may:

- inspect the published source and tests;
- run the reference harness locally;
- add new local tests and fixtures;
- exercise malformed, stale, replayed, substituted, mismatched or cross-chain execution material;
- challenge correspondence between authority, determination, constraint, provenance, permit, usage state and protected execution;
- test whether a declared property can be falsified; and
- report test/setup defects or bounded availability weaknesses separately.

## Out of scope

Do not:

- probe or test FlowSignal-hosted infrastructure;
- access or interfere with accounts, credentials or data belonging to others;
- test real banks, payment rails or third-party services;
- perform denial-of-service activity against external systems;
- use social engineering;
- seek secrets or private data; or
- treat production properties explicitly excluded by the candidate as if they were claimed by this reference implementation.

This challenge does not grant permission beyond the published code and local reference harness.

## What makes a strong submission

Please provide:

1. candidate branch and exact commit tested;
2. operating system and Python version;
3. minimal test/fixture required to reproduce;
4. the declared property being challenged;
5. expected result;
6. actual result;
7. complete relevant test output;
8. whether protected consequence formed; and
9. any assumptions required by the case.

Prefer the smallest case that demonstrates the issue.

## How results will be classified

A submission may be classified as:

**Confirmed failure of a declared property**  
A reproducible case within the declared boundary demonstrates that the claimed property does not hold.

**Test or fixture defect**  
The observed RED does not demonstrate a boundary weakness because the intended boundary was not reached or the setup is invalid.

**New requirement / scope extension**  
The case is technically useful but exercises a property the candidate does not currently claim.

**Production architecture concern**  
The case concerns deployment properties such as distributed coordination, infrastructure isolation or production persistence that are explicitly outside this reference boundary.

## Failure-first handling

For a confirmed failure of a declared property, FlowSignal's intended evidence discipline is:

1. preserve the first reproducible failure;
2. identify the exact boundary and cause;
3. avoid weakening or deleting the demonstrating case;
4. remediate narrowly;
5. rerun the affected case and selected cross-family regression;
6. record the result and remaining limitations; and
7. credit the contributor if they wish to be identified.

A confirmed failure is therefore a useful result.

## Submission route

Use a GitHub issue or pull request against the public candidate once the repository is made public.

Suggested issue title:

`Verification challenge: <short description>`

Suggested first line:

`Declared property challenged: <property>`

Please include the reproduction material directly or link to a minimal branch/fork.

---

**Before AI acts, know it's authorised.**

**FlowSignal™ — EXECUTE WITH AUTHORITY. DEFEND WITH EVIDENCE.**
