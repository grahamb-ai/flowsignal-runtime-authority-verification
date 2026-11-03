"""FS-RAW-DENIAL-001 actual process-exit reference qualification.

Source-owned SQLite effect and authority version share one local database.
The source PROCESS exits at controlled before/after commit points, then
restarts against the same DB. Test independently inspects the outcome ledger.
"""
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import os,sqlite3,time
import pytest

from app.engines.authority_store import get_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_online_authority import start,stop,READER,ADMIN
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request,post
from test_fs_raw_denial_001_ack_loss_red import ask_outcome

TOKEN="synthetic-crash-commit-token"

@pytest.fixture(autouse=True)
def isolated_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture(params=["before","after"])
def services(request,tmp_path):
    point=request.param
    db=tmp_path/"source-effects.sqlite3"
    env=os.environ.copy()
    env.update(FS_RAI_SOURCE_DB=str(db),
        FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,
        FS_RAI_SOURCE_COMMIT_TOKEN=TOKEN,
        FS_RAI_SOURCE_INITIAL_VERSION=str(get_authority_state_version()),
        FS_RAI_EXTERNAL_LEDGER=str(db),
        FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_TEST_CRASH_POINT=point)
    source,url=start("fs_raw_denial_001_crash_source.py",env)
    actuator_env=env.copy()
    actuator_env.update(FS_RAI_AUTHORITY_SOURCE_URL=url,
        FS_RAI_SOURCE_READ_TOKEN=READER)
    actuator,actuator_url=start("fs_raw_denial_001_atomic_actuator.py",actuator_env)
    result={"source":source,"source_url":url,"actuator":actuator,
            "pair":(actuator_url,db),"db":db,"point":point,"env":env}
    try:
        yield result
    finally:
        if actuator.poll() is None:stop(actuator)
        if source.poll() is None:stop(source)

def witness(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route FROM committed_effects").fetchall()

def restart_source(s):
    env=s["env"].copy()
    env.pop("FS_RAI_TEST_CRASH_POINT",None)
    env["FS_RAI_TEST_DROP_ACK"]="0"
    env["FS_RAI_SOURCE_PORT"]=str(urlsplit(s["source_url"]).port)
    p,url=start("fs_raw_denial_001_recovery_source.py",env)
    assert url==s["source_url"]
    return p

def test_forced_exit_recovery_and_replay(services):
    permit=mint(request())
    assert permit is not None
    assertion=export_final_bind(permit,bridge_key=KEY)
    assert assertion is not None
    code,response=post(services["pair"],"/execute-a",assertion,
                       permit.action_binding_hash)
    assert (code,response["status"],response["formed"])==(
        503,"COMMIT_OUTCOME_UNRESOLVED",None)
    deadline=time.monotonic()+4
    while services["source"].poll() is None and time.monotonic()<deadline:
        time.sleep(0.01)
    assert services["source"].poll() in (91,92)
    observed=witness(services["db"])
    if services["point"]=="before":
        assert observed==[]
    else:
        assert observed==[(permit.signature,permit.action_binding_hash,"/execute-a")]

    restarted=restart_source(services)
    try:
        status,outcome=ask_outcome(services,permit.signature)
        if services["point"]=="before":
            assert (status,outcome["status"],outcome["formed"])==(
                404,"OUTCOME_NOT_RECORDED",None)
            # Absence is only evidence about this test-owned reference ledger.
            retried,reply=post(services["pair"],"/execute-b",assertion,
                               permit.action_binding_hash)
            assert (retried,reply["status"])==(200,"CONSEQUENCE_FORMED")
            assert witness(services["db"])==[
                (permit.signature,permit.action_binding_hash,"/execute-b")]
        else:
            assert (status,outcome["status"],outcome["formed"])==(
                200,"CONSEQUENCE_FORMED",True)
            retried,reply=post(services["pair"],"/execute-b",assertion,
                               permit.action_binding_hash)
            assert (retried,reply["status"])==(409,"REPLAY_REFUSED")
            assert witness(services["db"])==observed
    finally:
        stop(restarted)
