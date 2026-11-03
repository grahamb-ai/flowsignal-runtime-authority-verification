"""Single-owner reference integration.

Unlike copied-state candidates, issuer reads and administrative revocations
use the SAME owner that serializes final synthetic consequence creation.
These tests do not establish production credential isolation or real payments.
"""
from contextlib import closing
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json,os,sqlite3
import pytest

from app.engines.authority_store import (
    get_authority_state_version,advance_authority_state_version,
)
from app.engines.authority_owner_client import AuthorityOwnerUnavailable
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_online_authority import start,stop
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request

READ="reference-authority-reader"
ADMIN="reference-authority-admin"
COMMIT="reference-consequence-executor"

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def owner(tmp_path,monkeypatch):
    db=tmp_path/"one-authority-one-effect.sqlite3"
    initial=get_authority_state_version()
    env=os.environ.copy()
    env.pop("FLOWSIGNAL_AUTHORITY_OWNER_URL",None)
    env.update(FS_RAI_SOURCE_DB=str(db),
        FS_RAI_SOURCE_INITIAL_VERSION=str(initial),
        FS_RAI_SOURCE_READ_TOKEN=READ,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,
        FS_RAI_WITNESS_COMMIT_TOKEN=COMMIT,
        FS_RAI_EXTERNAL_LEDGER=str(db),
        FS_RAI_BRIDGE_KEY=KEY.decode())
    process,url=start("fs_raw_denial_001_authority_owner.py",env)
    monkeypatch.setenv("FLOWSIGNAL_AUTHORITY_OWNER_URL",url)
    monkeypatch.setenv("FLOWSIGNAL_AUTHORITY_OWNER_READ_TOKEN",READ)
    monkeypatch.setenv("FLOWSIGNAL_AUTHORITY_OWNER_ADMIN_TOKEN",ADMIN)
    try:
        yield {"process":process,"url":url,"db":db,"initial":initial}
    finally:
        if process.poll() is None:stop(process)

def form_request():
    permit=mint(request())
    assert permit is not None
    grant=export_final_bind(permit,bridge_key=KEY)
    assert grant is not None
    return permit,{"envelope":grant,
        "action_binding_hash":permit.action_binding_hash,
        "route":"/execute-a"}

def http(url,body,credential=COMMIT,path="/commit"):
    req=Request(url+path,data=json.dumps(body).encode(),
        method="POST",headers={
            "Content-Type":"application/json",
            "X-Witness-Commit-Token":credential})
    try:
        with urlopen(req,timeout=4) as response:
            return response.status,json.loads(response.read())
    except HTTPError as error:
        return error.code,json.loads(error.read())

def effect_rows(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route "
                         "FROM committed_effects ORDER BY rowid").fetchall()

def database_epoch(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT version FROM authority_version WHERE id=1").fetchone()[0]

def test_issuer_reads_one_owner_and_owner_forms_once(owner):
    permit,body=form_request()
    assert permit.authority_state_version==owner["initial"]
    assert permit.authority_state_version==database_epoch(owner["db"])
    code,response=http(owner["url"],body)
    assert (code,response["status"])==(200,"WITNESSED_CONSEQUENCE_FORMED")
    code,response=http(owner["url"],body)
    assert (code,response["status"])==(409,"REPLAY_REFUSED")
    assert effect_rows(owner["db"])==[(
        permit.signature,permit.action_binding_hash,"/execute-a")]

def test_revocation_is_direct_owner_mutation_not_async_copy(owner):
    permit,body=form_request()
    updated=advance_authority_state_version()
    assert updated==owner["initial"]+1
    assert get_authority_state_version()==updated
    assert database_epoch(owner["db"])==updated
    code,response=http(owner["url"],body)
    assert (code,response["status"])==(403,"AUTHORITY_STATE_STALE")
    assert effect_rows(owner["db"])==[]

def test_no_local_fallback_after_owner_unreachable(owner):
    stop(owner["process"])
    with pytest.raises(AuthorityOwnerUnavailable):
        get_authority_state_version()
    with pytest.raises(AuthorityOwnerUnavailable):
        advance_authority_state_version()
    assert effect_rows(owner["db"])==[]

def test_miscredentialed_mutation_fails_without_local_fallback(owner,monkeypatch):
    permit,body=form_request()
    monkeypatch.setenv("FLOWSIGNAL_AUTHORITY_OWNER_ADMIN_TOKEN","invalid-admin")
    with pytest.raises(AuthorityOwnerUnavailable):
        advance_authority_state_version()
    assert get_authority_state_version()==owner["initial"]
    assert database_epoch(owner["db"])==owner["initial"]
    assert http(owner["url"],body)[0]==200

def test_untrusted_arbitrary_version_replacement_is_not_api(owner):
    status,response=http(owner["url"],{"version":999},path="/advance")
    assert status==404
    assert database_epoch(owner["db"])==owner["initial"]
    status,response=http(owner["url"],{"reason":"invalid"},path="/revoke")
    assert status==403 and response["status"]=="NO_MUTATION_AUTHORITY"
    assert database_epoch(owner["db"])==owner["initial"]

def test_after_direct_revocation_new_epoch_permit_can_commit(owner):
    assert advance_authority_state_version()==owner["initial"]+1
    permit,body=form_request()
    assert permit.authority_state_version==get_authority_state_version()
    code,response=http(owner["url"],body)
    assert (code,response["status"])==(200,"WITNESSED_CONSEQUENCE_FORMED")
    assert len(effect_rows(owner["db"]))==1
