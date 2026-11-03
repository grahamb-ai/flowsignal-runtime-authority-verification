"""Source-owned atomic reference consequence tests, with a deterministic
check-to-commit revocation race and independent source-ledger observation.
Not production settlement or cross-host distributed transactionality.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json,os,sqlite3,time,pytest

from app.engines.authority_store import (
    get_authority_state_version,advance_authority_state_version,
)
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_online_authority import (
    start,stop,advance_online,READER,ADMIN,
)
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request,post

COMMIT_TOKEN="trusted-commit-test"
ROOT=Path(__file__).parents[1]

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def managed(tmp_path,*,barrier_enabled=False):
    db=tmp_path/"authority-and-consequences.sqlite3"
    barrier=tmp_path/"barrier"
    source_env=os.environ.copy()
    source_env.update({
        "FS_RAI_SOURCE_DB":str(db),
        "FS_RAI_SOURCE_READ_TOKEN":READER,
        "FS_RAI_SOURCE_ADMIN_TOKEN":ADMIN,
        "FS_RAI_SOURCE_COMMIT_TOKEN":COMMIT_TOKEN,
        "FS_RAI_SOURCE_INITIAL_VERSION":str(get_authority_state_version()),
        "FS_RAI_EXTERNAL_LEDGER":str(db),
        "FS_RAI_BRIDGE_KEY":KEY.decode(),
    })
    source,source_url=start("fs_raw_denial_001_atomic_source.py",source_env)
    actuator_env=os.environ.copy()
    actuator_env.update({
        "FS_RAI_EXTERNAL_LEDGER":str(db),
        "FS_RAI_BRIDGE_KEY":KEY.decode(),
        "FS_RAI_AUTHORITY_SOURCE_URL":source_url,
        "FS_RAI_SOURCE_READ_TOKEN":READER,
        "FS_RAI_SOURCE_COMMIT_TOKEN":COMMIT_TOKEN,
    })
    if barrier_enabled:
        actuator_env["FS_RAI_TEST_BARRIER"]=str(barrier)
    actuator,actuator_url=start("fs_raw_denial_001_atomic_actuator.py",actuator_env)
    instance={
        "source":source,"source_url":source_url,
        "actuator":actuator,"pair":(actuator_url,db),
        "db":db,"barrier":barrier,
    }
    try:
        yield instance
    finally:
        barrier.mkdir(exist_ok=True)
        (barrier/"continue").touch()
        stop(actuator)
        if source.poll() is None:
            stop(source)

@pytest.fixture
def servers(tmp_path):
    yield from managed(tmp_path)

@pytest.fixture
def race_servers(tmp_path):
    yield from managed(tmp_path,barrier_enabled=True)

def witnessed(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route "
                         "FROM committed_effects").fetchall()

def issued():
    permit=mint(request())
    assert permit is not None
    envelope=export_final_bind(permit,bridge_key=KEY)
    assert envelope is not None
    return permit,envelope

def test_current_raifinalbind_forms_once_in_source_owned_ledger(servers):
    permit,envelope=issued()
    assert post(servers["pair"],"/execute-a",envelope,permit.action_binding_hash)[0]==200
    assert witnessed(servers["db"])==[
        (permit.signature,permit.action_binding_hash,"/execute-a")]
    code,result=post(servers["pair"],"/execute-b",envelope,permit.action_binding_hash)
    assert (code,result["status"])==(409,"REPLAY_REFUSED")
    assert len(witnessed(servers["db"]))==1

def test_revocation_before_request_refuses(servers):
    permit,envelope=issued()
    latest=advance_authority_state_version()
    assert advance_online(servers,latest)[0]==200
    code,result=post(servers["pair"],"/execute-b",envelope,permit.action_binding_hash)
    assert code==403 and result["formed"] is False
    assert witnessed(servers["db"])==[]

def test_revocation_between_lookup_and_source_commit_refuses(race_servers):
    permit,envelope=issued()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(post,race_servers["pair"],"/execute-b",
                           envelope,permit.action_binding_hash)
        deadline=time.monotonic()+6
        while not (race_servers["barrier"]/"looked-up").exists():
            assert time.monotonic()<deadline,"actuator did not reach lookup barrier"
            time.sleep(0.01)
        latest=advance_authority_state_version()
        assert advance_online(race_servers,latest)[0]==200
        (race_servers["barrier"]/"continue").touch()
        code,result=future.result(timeout=6)
    assert (code,result["status"])==(403,"AUTHORITY_STATE_STALE")
    assert witnessed(race_servers["db"])==[]

def test_missing_grant_refused_without_consequence(servers):
    for route in ("/execute-a","/execute-b"):
        assert post(servers["pair"],route,None)[0]==403
    assert witnessed(servers["db"])==[]

def test_source_service_unreachable_fails_closed(servers):
    permit,envelope=issued()
    stop(servers["source"])
    code,result=post(servers["pair"],"/execute-b",envelope,permit.action_binding_hash)
    assert code==403 and result["formed"] is False
    assert witnessed(servers["db"])==[]

def test_commit_endpoint_requires_separate_caller_authority(servers):
    payload=json.dumps({"route":"/execute-a","envelope":None}).encode()
    req=Request(servers["source_url"]+"/commit",method="POST",data=payload,
        headers={"Content-Type":"application/json"})
    try:
        with urlopen(req,timeout=3) as response:
            code=response.status
    except HTTPError as error:
        code=error.code
    assert code==403
    assert witnessed(servers["db"])==[]

def test_revoke_not_committed_to_authoritative_source_remains_open(servers):
    permit,envelope=issued()
    # This highlights an independent source-ownership requirement:
    # mutations to the original in-process authority are not automatically
    # represented in the separately-owned SQLite authority service.
    latest=advance_authority_state_version()
    assert latest>permit.authority_state_version
    code,result=post(servers["pair"],"/execute-a",envelope,permit.action_binding_hash)
    assert (code,result["status"])==(200,"CONSEQUENCE_FORMED")
    assert len(witnessed(servers["db"]))==1
    # This is a residual-gap characterisation, not a passing safety invariant.
