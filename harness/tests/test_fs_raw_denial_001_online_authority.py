"""Online source-of-truth reference path: genuine RAI permits, two localhost
processes, independent SQLite effect witness, and direct authority lookup.

Test-only authority publisher remains a trust assumption, NOT proved closure
of the underlying FlowSignal source-to-service update gap or commit-time race.
"""
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import json,os,select,sqlite3,subprocess,sys
import pytest

from app.engines.authority_store import (
    get_authority_state_version,advance_authority_state_version,
)
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from app.engines.sandbox_authority_fence_publisher import publish_authority_version
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request,post,rows

ROOT=Path(__file__).parents[1]
READER="source-read-test-key"
ADMIN="source-admin-test-key"

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def start(command,env):
    p=subprocess.Popen([sys.executable,"-u",command],cwd=ROOT,env=env,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert select.select([p.stdout],[],[],10)[0], "server start timeout"
    return p,"http://127.0.0.1:"+p.stdout.readline().strip()

def stop(p):
    p.terminate()
    try:p.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate(timeout=3)

@pytest.fixture
def setup(tmp_path):
    authority_db=tmp_path/"authoritative.sqlite3"
    effects_db=tmp_path/"effects.sqlite3"
    source_env=os.environ.copy()
    source_env.update({
        "FS_RAI_SOURCE_DB":str(authority_db),
        "FS_RAI_SOURCE_READ_TOKEN":READER,
        "FS_RAI_SOURCE_ADMIN_TOKEN":ADMIN,
        "FS_RAI_SOURCE_INITIAL_VERSION":str(get_authority_state_version()),
    })
    source,source_url=start("fs_raw_denial_001_authority_source.py",source_env)
    actuator_env=os.environ.copy()
    actuator_env.update({
        "FS_RAI_EXTERNAL_LEDGER":str(effects_db),
        "FS_RAI_BRIDGE_KEY":KEY.decode(),
        "FS_RAI_AUTHORITY_SOURCE_URL":source_url,
        "FS_RAI_SOURCE_READ_TOKEN":READER,
        "FS_RAI_AUTHORITY_MAX_AGE_SECONDS":"20",
    })
    actuator,actuator_url=start("fs_raw_denial_001_online_actuator.py",actuator_env)
    assert publish_authority_version(effects_db,get_authority_state_version())
    instance={"source":source,"source_url":source_url,
              "actuator":actuator,"pair":(actuator_url,effects_db)}
    try:yield instance
    finally:
        stop(actuator)
        if source.poll() is None:stop(source)

def advance_online(instance,version,*,token=ADMIN):
    payload=json.dumps({"version":version}).encode()
    req=Request(instance["source_url"]+"/advance",data=payload,method="POST",
        headers={"X-Authority-Admin-Token":token,"Content-Type":"application/json"})
    try:
        with urlopen(req,timeout=3) as response:
            return response.status,json.loads(response.read())
    except HTTPError as response:
        return response.code,json.loads(response.read())

def issued():
    permit=mint(request())
    assert permit is not None
    envelope=export_final_bind(permit,bridge_key=KEY)
    assert envelope is not None
    return permit,envelope

def test_current_source_allows_single_consequence(setup):
    permit,envelope=issued()
    pair=setup["pair"]
    assert post(pair,"/execute-a",envelope,permit.action_binding_hash)[0]==200
    assert len(rows(pair))==1
    code,result=post(pair,"/execute-b",envelope,permit.action_binding_hash)
    assert (code,result["status"])==(409,"REPLAY_REFUSED")
    assert len(rows(pair))==1

def test_source_revoked_without_actuator_publication_refuses(setup):
    permit,envelope=issued()
    latest=advance_authority_state_version()
    assert advance_online(setup,latest)[0]==200
    # No update to the actuator's locally published fence.
    code,result=post(setup["pair"],"/execute-b",envelope,permit.action_binding_hash)
    assert (code,result["status"])==(403,"AUTHORITY_SOURCE_STALE")
    assert rows(setup["pair"])==[]

def test_source_unreachable_fails_closed(setup):
    permit,envelope=issued()
    stop(setup["source"])
    code,result=post(setup["pair"],"/execute-a",envelope,permit.action_binding_hash)
    assert (code,result["status"])==(403,"AUTHORITY_SOURCE_UNAVAILABLE")
    assert rows(setup["pair"])==[]

def test_untrusted_update_cannot_advance_source(setup):
    permit,envelope=issued()
    latest=get_authority_state_version()+1
    assert advance_online(setup,latest,token="invalid-token")[0]==403
    # Original permit remains valid because no legitimate revocation occurred.
    assert post(setup["pair"],"/execute-a",envelope,permit.action_binding_hash)[0]==200

def test_source_rejects_older_version_update(setup):
    current=get_authority_state_version()
    code,result=advance_online(setup,current-1)
    assert (code,result["error"])==(409,"NON_MONOTONIC_UPDATE")

def test_missing_grant_is_refused(setup):
    for route in ("/execute-a","/execute-b"):
        assert post(setup["pair"],route,None)[0]==403
    assert rows(setup["pair"])==[]

def test_undelivered_update_to_source_service_still_exposes_gap(setup):
    permit,envelope=issued()
    new_source_version=advance_authority_state_version()
    assert new_source_version>permit.authority_state_version
    # This upstream mutation is deliberately NOT delivered to the online
    # authority service. The service still claims the old version is current.
    code,result=post(setup["pair"],"/execute-b",envelope,permit.action_binding_hash)
    assert (code,result["status"])==(200,"CONSEQUENCE_FORMED")
    assert len(rows(setup["pair"]))==1
    # This is a characterization of an unresolved SOURCE OWNERSHIP / UPDATER
    # AUTHENTICITY gap, NOT an immediate-revocation safety test pass.
