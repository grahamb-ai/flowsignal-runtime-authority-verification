"""Reference source-owned witness authority and effect commitment tests.

Local test service owns a SQLite authority version and modeled consequence.
The separate original FlowSignal source is NOT automatically linked.
"""
from contextlib import closing
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import json,os,sqlite3
import pytest
from app.engines.authority_store import get_authority_state_version,advance_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_online_authority import start,stop,advance_online
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request
from app.engines.rai_external_export_reference import export_final_bind

TOKEN="witness-test-commit"
ADMIN="source-admin-test-key"
READER="source-read-test-key"

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def witness(tmp_path):
    db=tmp_path/"single-owner.sqlite3"
    env=os.environ.copy()
    env.update(FS_RAI_SOURCE_DB=str(db),
        FS_RAI_SOURCE_INITIAL_VERSION=str(get_authority_state_version()),
        FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,
        FS_RAI_EXTERNAL_LEDGER=str(db),
        FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN)
    process,url=start("fs_raw_denial_001_atomic_witness.py",env)
    try:yield url,db
    finally:
        if process.poll() is None:stop(process)

def send(url,body,token=TOKEN):
    data=json.dumps(body).encode()
    req=Request(url+"/commit",data=data,method="POST",
                headers={"Content-Type":"application/json","X-Witness-Commit-Token":token})
    try:
        with urlopen(req,timeout=4) as res:
            return res.status,json.loads(res.read())
    except HTTPError as res:
        return res.code,json.loads(res.read())

def witness_rows(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as con:
        return con.execute("SELECT permit_signature,action_binding_hash,route "
                           "FROM committed_effects").fetchall()

def signed_request():
    permit=mint(request())
    assert permit is not None
    exported=export_final_bind(permit,bridge_key=KEY)
    assert exported is not None
    return permit,{"envelope":exported,
        "action_binding_hash":permit.action_binding_hash,"route":"/execute-b"}

def test_witness_owned_revocation_before_commit_refuses(witness):
    url,db=witness
    permit,body=signed_request()
    version=advance_authority_state_version()
    assert version>permit.authority_state_version
    assert advance_online({"source_url":url},version)[0]==200
    code,response=send(url,body)
    assert (code,response["status"])==(403,"AUTHORITY_STATE_STALE")
    assert witness_rows(db)==[]

def test_current_authority_commit_and_replay_single_use(witness):
    url,db=witness
    permit,body=signed_request()
    code,response=send(url,body)
    assert (code,response["status"])==(200,"WITNESSED_CONSEQUENCE_FORMED")
    assert witness_rows(db)==[(permit.signature,permit.action_binding_hash,"/execute-b")]
    code,replayed=send(url,body)
    assert (code,replayed["status"])==(409,"REPLAY_REFUSED")
    assert len(witness_rows(db))==1

def test_missing_source_delivery_remains_unresolved(witness):
    url,db=witness
    permit,body=signed_request()
    version=advance_authority_state_version()
    assert version>permit.authority_state_version
    # Deliberately do not update the witness-owned source version.
    code,response=send(url,body)
    assert (code,response["status"])==(200,"WITNESSED_CONSEQUENCE_FORMED")
    assert len(witness_rows(db))==1
    # Characterization of an OPEN source-ownership/delivery gap, not a
    # successful immediate-revocation safety invariant.

def test_unauthorised_commit_cannot_form(witness):
    url,db=witness
    _,body=signed_request()
    code,response=send(url,body,token="untrusted")
    assert code==403 and response["status"]=="UNAUTHORIZED_WITNESS_CALLER"
    assert witness_rows(db)==[]
