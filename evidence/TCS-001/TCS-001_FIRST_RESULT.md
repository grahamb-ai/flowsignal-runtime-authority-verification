# TCS-001 — First Actual Result

## Frozen input

- challenge commit: `ff5dd5a`
- shared capacity: `10`
- movement A: `6`
- movement B: `6`
- combined burden: `12`

## Command

```text
PYTHONPATH=.venv/lib/python3.12/site-packages:harness python3 -m pytest -q -s harness/tests/test_tcs001_coupled_capacity.py --junitxml=evidence/TCS-001/TCS-001_FIRST_ACTUAL_RUN.xml -o junit_logging=all
```

The repository virtual environment contained the declared dependencies, but
its Python symlink was broken. The command above uses the available Python 3.12
runtime with that environment's installed packages. The earlier launcher
failures did not collect or execute any test.

The later expanded-suite run exposed a test-observation defect: the initial
test hard-coded `DAY-001`, while a preceding hostile test can advance the
reference usage-window identity. The refusal still occurred, but the assertion
looked up the wrong scope. The test was corrected to derive the scope from the
actual prepared policy before the expanded suite was rerun. This does not alter
the preserved first actual result below or the enforcement implementation.

## Unedited first actual test output

```text
TCS-001 sequential: A=CONSEQUENCE_FORMED; B=REFUSED (aggregate authority capacity exceeded); active_burden=6; capacity=10
.TCS-001 concurrent: [('CONCURRENT-A', 'REFUSED'), ('CONCURRENT-B', 'RESERVED')]; active_burden=6; capacity=10
.TCS-001 combined: burden=12; REFUSED (amount outside effective mandate); active_burden=0; capacity=10
.
3 passed in 0.07s
```

## Classification

| Claim | Result | Evidence |
|---|---|---|
| Sequential coupled-capacity enforcement | PASS | A formed at burden 6; B was refused; active burden remained 6/10. |
| Concurrent coupled-capacity enforcement in the bounded process | PASS | Exactly one 6-unit attempt reserved capacity; the other was refused under the shared lock. |
| Combined burden 12 against capacity 10 | PASS | The request was refused before any active reservation. |
| Protected-state non-formation for the refused movement | PASS within the reference harness | The refused path failed before permit minting or protected-consequence execution. |
| Signed refusal receipt for the capacity rejection | NOT DEMONSTRATED | The current path raises an exception; this test did not obtain a signed denial receipt. |
| Replay of a refusal receipt | NOT DEMONSTRATED | No refusal receipt exists in this tested path to replay. |
| Cross-process/distributed atomicity | OUT OF SCOPE | The published reference mechanism uses a process-local `RLock` and in-memory state. |

## Conclusion

Terry Snyder's exact bounded 10/6/6 capacity challenge does not falsify the
published FlowSignal reference boundary. It passes the sequential, concurrent,
and combined-burden cases within the declared process-local scope. This result
does not support a broader claim that the tested refusal already supplies a
signed receipt, replay, or distributed production guarantee.
