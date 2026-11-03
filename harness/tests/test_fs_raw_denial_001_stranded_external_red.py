"""FS-RAW-DENIAL-001 FIRST RED: local commitment strands external effect.

The original local source commits while the independent witness is down.
After the witness is restarted the same signed reference grant cannot reach
it because the proxy's local stage treats the permit as consumed. This is a
synthetic reference reconciliation failure, not a real payment.
"""
from pathlib import Path
import json,os
import pytest
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_independent_witness import (
    witness,proxy,TOKEN,witness_rows
)
from test_fs_raw_denial_001_surviving_anchor import start_group,stop_group,commitments
from test_fs_raw_denial_001_parallel_contention import grant_payload
from test_fs_raw_denial_001_online_authority import start,stop
from test_fs_raw_denial_001_rai_external_actuator import KEY,post

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def test_local_committed_witness_outage_retry_must_reconcile(tmp_path,witness):
    witness_process,witness_url,witness_db=witness
    main=tmp_path/"authority.sqlite3"
    anchor=tmp_path/"anchor.sqlite3"
    permit,grant_file=grant_payload(tmp_path)
    assertion=json.loads(grant_file.read_text())["envelope"]
    group,pair=start_group(main,anchor)
    front,front_url=proxy(pair[0],witness_url)
    replacement=None
    new_front=None
    try:
        stop(witness_process)
        first=post((front_url,main),"/execute-a",assertion,permit.action_binding_hash)
        assert (first[0],first[1]["status"])==(503,"WITNESS_OUTCOME_UNRESOLVED")
        assert len(commitments(anchor))==1
        assert witness_rows(witness_db)==[]
        stop(front)

        env=os.environ.copy()
        env.update(FS_RAI_WITNESS_DB=str(witness_db),
                   FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
                   FS_RAI_EXTERNAL_LEDGER=str(witness_db),
                   FS_RAI_BRIDGE_KEY=KEY.decode())
        replacement,new_url=start("fs_raw_denial_001_independent_witness.py",env)
        new_front,new_front_url=proxy(pair[0],new_url)
        retried=post((new_front_url,main),"/execute-b",assertion,
                     permit.action_binding_hash)
        assert len(commitments(anchor))==1
        assert len(witness_rows(witness_db))==1, (
            "FIRST RED: local source has consumed the permit, while the "
            "recovered independent witness has no synthetic effect; replay "
            f"cannot complete external commitment. retry={retried}"
        )
    finally:
        if new_front is not None and new_front.poll() is None:stop(new_front)
        if replacement is not None and replacement.poll() is None:stop(replacement)
        if front.poll() is None:stop(front)
        stop_group(group)
