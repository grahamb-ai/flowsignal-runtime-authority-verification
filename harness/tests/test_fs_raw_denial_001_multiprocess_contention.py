"""FS-RAW-DENIAL-001 multiprocess contention and crash-retry qualification.

All callers run as separate Python processes. The normal source uses
ThreadingHTTPServer, so its SQLite BEGIN IMMEDIATE is actually contended.
Crash tests use the existing serial HTTP source and are expressly narrower.
Effects are synthetic SQLite rows, not external payments.
"""
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import json,os,sqlite3,subprocess,sys,time
import pytest

from app.engines.authority_store import get_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_online_authority import start,stop,READER,ADMIN
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request

ROOT=Path(__file__).parents[1]
TOKEN="test-contention-commit-token"

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def source_env(db,*,crash=None,port=None):
    env=os.environ.copy()
    env.update(FS_RAI_SOURCE_DB=str(db),
        FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,
        FS_RAI_SOURCE_COMMIT_TOKEN=TOKEN,
        FS_RAI_SOURCE_INITIAL_VERSION=str(get_authority_state_version()),
        FS_RAI_EXTERNAL_LEDGER=str(db),
        FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_TEST_DROP_ACK="0")
    if crash:env["FS_RAI_TEST_CRASH_POINT"]=crash
    if port is not None:env["FS_RAI_SOURCE_PORT"]=str(port)
    return env

def observed(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as conn:
        return conn.execute("SELECT permit_signature,action_binding_hash,route "
                            "FROM committed_effects").fetchall()

def grant():
    permit=mint(request())
    assert permit is not None
    assertion=export_final_bind(permit,bridge_key=KEY)
    assert assertion is not None
    return permit,assertion

def client_batch(tmp_path,url,permit,envelope,count):
    gate=tmp_path/"release-gate"
    children=[]
    for index in range(count):
        config={
            "gate":str(gate),"source_url":url,"commit_token":TOKEN,
            "envelope":envelope,
            "action_binding_hash":permit.action_binding_hash,
            "route":"/execute-a" if index%2==0 else "/execute-b",
            "output":str(tmp_path/f"client-{index}.json"),
        }
        config_path=tmp_path/f"config-{index}.json"
        config_path.write_text(json.dumps(config))
        p=subprocess.Popen([sys.executable,"fs_raw_denial_001_parallel_client.py",
                            str(config_path)],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        children.append((p,config))
    gate.touch()
    responses=[]
    try:
        for p,conf in children:
            stdout,stderr=p.communicate(timeout=12)
            assert p.returncode==0,(stdout,stderr)
            responses.append(json.loads(Path(conf["output"]).read_text()))
    finally:
        for p,_ in children:
            if p.poll() is None:
                p.kill()
                p.communicate(timeout=3)
    return responses

def test_eight_independent_clients_form_one_effect(tmp_path):
    db=tmp_path/"source.sqlite3"
    source,url=start("fs_raw_denial_001_threaded_source.py",source_env(db))
    try:
        permit,envelope=grant()
        responses=client_batch(tmp_path,url,permit,envelope,8)
        codes=[x["http"] for x in responses]
        assert codes.count(200)==1,codes
        assert codes.count(409)==7,codes
        assert observed(db)==[(permit.signature,permit.action_binding_hash,
                               observed(db)[0][2])]
    finally:
        stop(source)

@pytest.mark.parametrize("crash_point,exit_code,expected_before_retry",
                         [("before",91,0),("after",92,1)])
def test_competing_clients_source_exit_recover_retry(
        tmp_path,crash_point,exit_code,expected_before_retry):
    db=tmp_path/"source.sqlite3"
    process,url=start("fs_raw_denial_001_crash_source.py",
                      source_env(db,crash=crash_point))
    restarted=None
    try:
        permit,envelope=grant()
        results=client_batch(tmp_path,url,permit,envelope,4)
        deadline=time.monotonic()+5
        while process.poll() is None and time.monotonic()<deadline:
            time.sleep(0.01)
        assert process.poll()==exit_code
        before=observed(db)
        assert len(before)==expected_before_retry
        # No failed transport response is taken as proof of nonformation.
        assert any(x["http"] is None for x in results)
        port=urlsplit(url).port
        restarted,new_url=start("fs_raw_denial_001_threaded_source.py",
            source_env(db,port=port))
        assert new_url==url
        retry_results=client_batch(tmp_path/"retries",new_url,permit,envelope,4)
        codes=[x["http"] for x in retry_results]
        if crash_point=="before":
            assert codes.count(200)==1 and codes.count(409)==3,codes
        else:
            assert codes.count(200)==0 and codes.count(409)==4,codes
        final=observed(db)
        assert len(final)==1
        assert final[0][:2]==(permit.signature,permit.action_binding_hash)
    finally:
        if restarted is not None:stop(restarted)
        if process.poll() is None:stop(process)
