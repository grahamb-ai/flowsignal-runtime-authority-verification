"""Reference reconciliation after local commit and witness outage.

A trusted test client checks surviving local commitment evidence and current
source epoch before completing the modeled external effect. This is not a
distributed transaction or guaranteed production compensation protocol.
"""
from pathlib import Path
import json,os,pytest

from app.engines.authority_store import (
    get_authority_state_version,advance_authority_state_version,
)
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_independent_witness import (
    witness,proxy,TOKEN,witness_rows
)
from test_fs_raw_denial_001_online_authority import start,stop,advance_online
from test_fs_raw_denial_001_parallel_contention import (
    source_env,actuator_env,grant_payload
)
from test_fs_raw_denial_001_rai_external_actuator import KEY,post

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def source_pair(tmp_path):
    db=tmp_path/"authority.sqlite3"
    anchor=tmp_path/"anchor.sqlite3"
    env=source_env(db)
    env["FS_RAI_SURVIVING_ANCHOR_DB"]=str(anchor)
    src,url=start("fs_raw_denial_001_surviving_anchor_source.py",env)
    actuator,actuator_url=start("fs_raw_denial_001_contention_server.py",
        actuator_env(db,url))
    return src,url,actuator,actuator_url,db,anchor

def recovery_proxy(actuator_url,source_url,witness_url):
    env=os.environ.copy()
    env.update(FS_RAI_LOCAL_ACTUATOR_URL=actuator_url,
        FS_RAI_LOCAL_SOURCE_URL=source_url,
        FS_RAI_SOURCE_READ_TOKEN="source-read-test-key",
        FS_RAI_WITNESS_URL=witness_url,
        FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
        FS_RAI_EXTERNAL_LEDGER="unused-reference-path",
        FS_RAI_BRIDGE_KEY=KEY.decode())
    return start("fs_raw_denial_001_reconciliation_proxy.py",env)

def revive_witness(db):
    env=os.environ.copy()
    env.update(FS_RAI_WITNESS_DB=str(db),
        FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
        FS_RAI_EXTERNAL_LEDGER=str(db),FS_RAI_BRIDGE_KEY=KEY.decode())
    return start("fs_raw_denial_001_independent_witness.py",env)

def prepare_outage(tmp_path,witness):
    old_witness,witness_url,witness_db=witness
    src,source_url,actuator,actuator_url,db,anchor=source_pair(tmp_path)
    permit,grant_file=grant_payload(tmp_path)
    assertion=json.loads(grant_file.read_text())["envelope"]
    first_proxy,first_url=proxy(actuator_url,witness_url)
    stop(old_witness)
    original=post((first_url,db),"/execute-a",assertion,
                  permit.action_binding_hash)
    stop(first_proxy)
    assert (original[0],original[1]["status"])==(503,"WITNESS_OUTCOME_UNRESOLVED")
    assert witness_rows(witness_db)==[]
    return src,source_url,actuator,actuator_url,db,witness_db,permit,assertion

def test_stranded_local_commit_can_complete_one_external_witness(tmp_path,witness):
    src,source_url,actuator,actuator_url,db,wdb,permit,assertion=prepare_outage(tmp_path,witness)
    restored=None
    recover=None
    try:
        restored,witness_url=revive_witness(wdb)
        recover,recovery_url=recovery_proxy(actuator_url,source_url,witness_url)
        code,result=post((recovery_url,db),"/execute-b",
                         assertion,permit.action_binding_hash)
        assert (code,result["status"])==(200,"WITNESSED_CONSEQUENCE_FORMED")
        assert witness_rows(wdb)==[(
            permit.signature,permit.action_binding_hash,"/execute-b")]
        repeated=post((recovery_url,db),"/execute-a",assertion,permit.action_binding_hash)
        assert repeated[0] in (403,409)
        assert len(witness_rows(wdb))==1
    finally:
        for proc in (recover,restored,actuator,src):
            if proc is not None and proc.poll() is None:stop(proc)

def test_recovery_refuses_if_source_authority_version_has_advanced(tmp_path,witness):
    src,source_url,actuator,actuator_url,db,wdb,permit,assertion=prepare_outage(tmp_path,witness)
    restored=None
    recover=None
    try:
        new_version=advance_authority_state_version()
        instance={"source_url":source_url}
        assert advance_online(instance,new_version)[0]==200
        restored,witness_url=revive_witness(wdb)
        recover,recovery_url=recovery_proxy(actuator_url,source_url,witness_url)
        code,result=post((recovery_url,db),"/execute-b",
                         assertion,permit.action_binding_hash)
        assert code==403
        assert witness_rows(wdb)==[]
    finally:
        for proc in (recover,restored,actuator,src):
            if proc is not None and proc.poll() is None:stop(proc)
