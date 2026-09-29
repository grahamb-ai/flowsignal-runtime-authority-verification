# FlowSignal™ Runtime Authority — Public Verification Candidate v0.1

> **WHO → WHAT → NOW → MATCH = B4 ACT**

**Before AI acts, know it's authorised.**

This branch is a frozen public verification candidate for FlowSignal's Runtime Authority reference implementation.

## Your job: try to make the declared properties fail

FlowSignal built this reference implementation and FlowSignal performed the verification that produced the current baseline. That is useful engineering evidence, but it is not independent third-party validation.

So this candidate is being opened for independent technical scrutiny.

We are not asking reviewers to confirm that FlowSignal is right. We are asking reviewers to try to falsify the bounded claims below with a reproducible case.

If a legitimate new failure is demonstrated, the intended process is:

**preserve the first failure → understand the cause → remediate narrowly → rerun the regression → retain the evidence**

A new reproducible failure is useful evidence, not something to hide.

## The simple model

| Question | Runtime-authority question |
|---|---|
| **WHO** | Who holds the authority? |
| **WHAT** | What is authorised? |
| **NOW** | Is that authority valid at the point of execution? |
| **MATCH** | Does this exact execution still correspond to the authority and decision that were validated? |

**WHO → WHAT → NOW → MATCH = B4 ACT**

The engineering question is whether protected consequence can form when one of the required runtime-authority relationships should prevent it.

## Public WHO / WHAT / NOW / MATCH receipt

The reference harness can project a successful final-bind into
`flowsignal.public-authority-receipt.v1`, a compact JSON view of the runtime
artifacts:

```json
{
  "who": {
    "authority_subject_id": "agent-treasury-01",
    "evidence_anchor": "CTX-...",
    "claim": "AUTHORITY_SUBJECT_BOUND"
  },
  "what": {
    "protected_operation_id": "OP-...",
    "action": "payment.release",
    "amount": "750000",
    "currency": "GBP"
  },
  "now": {
    "status": "VALID_AT_FINAL_BIND",
    "checked_at": "2026-08-10T09:15:00+00:00",
    "valid_until": "2026-08-10T09:16:00+00:00"
  },
  "match": {
    "status": "EXACT_CORRESPONDENCE",
    "final_bind_reason": "FINAL_BIND_AUTHORITY_REVALIDATED"
  },
  "outcome": {
    "decision": "PERMITTED_TO_ACT",
    "consequence_formed": false
  }
}
```

The complete document also carries the principal, mandate, institutional
operation, authority binding and execution-lineage identifiers plus a SHA-256
integrity digest. Verification compares the JSON with the trusted runtime
artifacts; the digest alone is not represented as an external signature.

This is deliberately a presentation layer. It neither grants authority nor
mints an execution capability, and `PERMITTED_TO_ACT` does not assert that a
downstream consequence formed. See
`harness/app/engines/public_authority_receipt.py` and the hostile mutation tests
in `harness/tests/test_public_authority_receipt.py`.

## Original frozen baseline

The engineering checkpoint underlying the original candidate is:

```
257d28cd6171475afd6b6b37b2db2a954399939b
```

The selected cross-family verification workflow completed:

```
124 passed in 0.68s
```

That is a regression result, not 124 independent proofs and not production certification.

The selected verification scope spans:

- R1 exact-money;
- R2 authoritative state, authority domain, evidence adapters, resolution, determination and final-bind;
- R3 approval;
- R4 authority usage;
- R5 lineage;
- R6 final-bind provenance and causal correspondence;
- the integrated payment path; and
- the protected execution boundary.

## What previous verification found

Failure-first work already exposed genuine weaknesses, including:

1. genuine final-bind provenance that could be reused with a separately signed permit;
2. low-level reference capabilities that could originally substitute for causal traversal of successful final-bind;
3. a genuine causal grant that was not initially bound to the exact determination and constraint; and
4. an availability weakness where an incorrect correspondence could consume a genuine grant.

Those findings were preserved, remediated narrowly and retained in the regression evidence.

See `harness/evidence/` for the detailed records.

## What we currently claim

Within the tested reference-harness boundary, the evidence supports the following bounded properties:

- final-bind provenance corresponds to the exact execution permit;
- tested cross-chain provenance transplant does not form a protected consequence;
- the tested low-level reference capabilities cannot substitute for successful causal final-bind;
- the one-shot causal grant corresponds to the exact tested decision artifacts and execution lineage;
- incorrect grant correspondence does not destroy a still-valid grant;
- successful grant consumption remains single-use; and
- the selected R1-R6 and integrated execution families are regression-compatible at the frozen checkpoint.

**These are the claims to challenge.**

## What we do not claim

This candidate does not establish:

- production certification;
- production-grade persistence;
- universal route closure;
- multi-process or distributed coordination;
- distributed atomicity;
- crash or power-loss durability;
- production IAM, HSM or KMS isolation;
- external payment-system idempotency;
- resistance to arbitrary mutation of private process-local reference state;
- complete rollback resistance across every possible state store; or
- global closure of every possible runtime-authority failure mode.

Please do not treat a finding outside this declared boundary as evidence for a claim we have not made. It may still be useful as a proposed extension of scope.

## Reproduce the selected verification

```bash
git clone https://github.com/grahamb-ai/flowsignal-runtime-authority-verification.git
cd flowsignal-runtime-authority-verification

python -m venv .venv

# macOS / Linux
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r harness/requirements.txt

# Windows PowerShell (no script activation required)
# .venv\Scripts\python.exe -m pip install --upgrade pip
# .venv\Scripts\python.exe -m pip install -r harness\requirements.txt

cd harness

# macOS / Linux
../.venv/bin/python -m pytest -q \
  tests/test_fs_rai_r1_exact_money.py \
  tests/test_fs_rai_r2_authoritative_state.py \
  tests/test_fs_rai_r2_authority_domain.py \
  tests/test_fs_rai_r2_authority_evidence_adapters.py \
  tests/test_fs_rai_r2_authority_resolution.py \
  tests/test_fs_rai_r2_authority_determination.py \
  tests/test_fs_rai_r2_final_bind.py \
  tests/test_fs_rai_r5_lineage.py \
  tests/test_fs_rai_r3_approval.py \
  tests/test_fs_rai_r4_authority_usage.py \
  tests/test_fs_rai_integrated_payment_path.py \
  tests/test_fs_rai_execution_boundary_integration.py \
  tests/test_public_authority_receipt.py

# Windows PowerShell: run the same selected suite with
# ..\.venv\Scripts\python.exe -m pytest -q <the same test files above>
```

Expected expanded verification result:

```
134 passed
```

Timing varies by environment.

## Submit a challenge

Please read [PUBLIC-VERIFICATION-CHALLENGE.md](PUBLIC-VERIFICATION-CHALLENGE.md) before submitting a case.

A useful submission should contain:

- the exact candidate commit/ref tested;
- environment and Python version;
- a minimal reproducible test or fixture;
- the authority invariant you believe is violated;
- expected result;
- actual result;
- complete test output; and
- whether protected consequence formed.

Please do not test FlowSignal infrastructure, third-party systems, real payment rails or accounts. The invitation is limited to the published reference implementation.

## Evidence discipline

We will distinguish clearly between:

- a reproducible failure of a declared property;
- a test/setup error;
- a useful new requirement outside the current boundary; and
- a production concern that this reference candidate explicitly does not claim to solve.

Where a reproducible new failure of a declared property is confirmed, the goal is to preserve the first failure before remediation and credit the contributor where they wish to be identified.

---

**FlowSignal™ — EXECUTE WITH AUTHORITY. DEFEND WITH EVIDENCE.**
