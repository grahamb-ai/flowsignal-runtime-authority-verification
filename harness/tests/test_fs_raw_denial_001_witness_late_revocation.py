"""Deterministic late revocation during recovery, verified at witness."""
from concurrent.futures import ThreadPoolExecutor
import os,time
from pathlib import Path
import pytest
from app.engines.authority_store import advance_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_online_authority import start,stop,advance_online
from test_fs_raw_denial_001_stranded_reconciliation import prepare_outage,witness,TOKEN
from test_fs_raw_denial_001_rai_external_actuator import KEY,post
from test_fs_raw_denial_001_independent_witness import witness_rows

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def test_late_revocation_before_witness_commit_refuses(tmp_path,witness):
    source,url,actuator,actuator_url,db,wdb,permit,grant=prepare_outage(tmp_path,witness)
    witness_process=None
    proxy=None
    barrier=tmp_path/"barrier"
    try:
        wenv=os.environ.copy()
        wenv.update(FS_RAI_WITNESS_DB=str(wdb),
            FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
            FS_RAI_EXTERNAL_LEDGER=str(wdb),
            FS_RAI_BRIDGE_KEY=KEY.decode(),
            FS_RAI_WITNESS_AUTHORITY_URL=url,
            FS_RAI_WITNESS_AUTHORITY_READ_TOKEN="source-read-test-key")
        witness_process,wurl=start("fs_raw_denial_001_fresh_witness.py",wenv)
        penv=os.environ.copy()
        penv.update(FS_RAI_LOCAL_ACTUATOR_URL=actuator_url,
            FS_RAI_LOCAL_SOURCE_URL=url,
            FS_RAI_SOURCE_READ_TOKEN="source-read-test-key",
            FS_RAI_WITNESS_URL=wurl,
            FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
            FS_RAI_EXTERNAL_LEDGER=str(wdb),
            FS_RAI_BRIDGE_KEY=KEY.decode(),
            FS_RAI_RECOVERY_TEST_BARRIER=str(barrier))
        proxy,purl=start("fs_raw_denial_001_reconciliation_race_proxy.py",penv)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(post,(purl,db),"/execute-b",grant,
                                permit.action_binding_hash)
            deadline=time.monotonic()+6
            while not (barrier/"preflight-complete").exists():
                assert time.monotonic()<deadline
                time.sleep(0.01)
            version=advance_authority_state_version()
            assert version>permit.authority_state_version
            assert advance_online({"source_url":url},version)[0]==200
            (barrier/"continue").touch()
            code,result=pending.result(timeout=6)
        assert (code,result["status"])==(403,"AUTHORITY_STATE_STALE")
        assert witness_rows(wdb)==[]
    finally:
        barrier.mkdir(exist_ok=True)
        (barrier/"continue").touch()
        for process in (proxy,witness_process,actuator,source):
            if process is not None and process.poll() is None:
                stop(process)
