"""FIRST RED: source revokes after successful recovery preflight,
before separate witness's irreversible simulated commitment.
No financial rails, only localhost processes and test-owned SQLite ledgers.
"""
from concurrent.futures import ThreadPoolExecutor
import json,os,time
import pytest
from app.engines.authority_store import advance_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_stranded_reconciliation import (
    prepare_outage,revive_witness,witness,TOKEN,stop,advance_online
)
from test_fs_raw_denial_001_independent_witness import witness_rows
from test_fs_raw_denial_001_rai_external_actuator import KEY,post
from test_fs_raw_denial_001_online_authority import start

@pytest.fixture(autouse=True)
def isolated_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def test_revoked_between_recovery_check_and_witness_commit_must_refuse(tmp_path,witness):
    src,url,actuator,actuator_url,db,wdb,permit,assertion=prepare_outage(tmp_path,witness)
    external=None
    recovery=None
    barrier=tmp_path/"barrier"
    try:
        external,witness_url=revive_witness(wdb)
        env=os.environ.copy()
        env.update(FS_RAI_LOCAL_ACTUATOR_URL=actuator_url,
            FS_RAI_LOCAL_SOURCE_URL=url,FS_RAI_SOURCE_READ_TOKEN="source-read-test-key",
            FS_RAI_WITNESS_URL=witness_url,FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
            FS_RAI_EXTERNAL_LEDGER=str(wdb),FS_RAI_BRIDGE_KEY=KEY.decode(),
            FS_RAI_RECOVERY_TEST_BARRIER=str(barrier))
        recovery,recovery_url=start("fs_raw_denial_001_reconciliation_race_proxy.py",env)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future=executor.submit(post,(recovery_url,db),"/execute-b",assertion,
                                   permit.action_binding_hash)
            deadline=time.monotonic()+7
            while not (barrier/"preflight-complete").exists():
                assert time.monotonic()<deadline,"preflight barrier not reached"
                time.sleep(0.01)
            newer=advance_authority_state_version()
            assert newer>permit.authority_state_version
            assert advance_online({"source_url":url},newer)[0]==200
            (barrier/"continue").touch()
            status,response=future.result(timeout=7)
        observed=witness_rows(wdb)
        assert (status,response.get("formed"),observed)==(403,False,[]),(
            "FIRST RED: independent witness formed an effect after authority "
            f"was revoked following recovery preflight. HTTP={status} "
            f"response={response}; witness ledger={observed}")
    finally:
        barrier.mkdir(exist_ok=True)
        (barrier/"continue").touch()
        for p in (recovery,external,actuator,src):
            if p is not None and p.poll() is None:stop(p)
