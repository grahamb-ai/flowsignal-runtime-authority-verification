"""FS-RAW-DENIAL-001 independent witness qualification.

A separate witness process and SQLite database model a consequence external to
the restorable local authority DB + anchor. All interfaces are localhost-only.
Test credential possession is deliberately assumed, not production isolated.
"""
from contextlib import closing
import json,os,shutil,sqlite3
import pytest
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_surviving_anchor import start_group,stop_group,commitments
from test_fs_raw_denial_001_parallel_contention import grant_payload
from test_fs_raw_denial_001_online_authority import start,stop
from test_fs_raw_denial_001_rai_external_actuator import KEY,post

TOKEN="test-witness-commit-token"

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def witness(tmp_path):
    db=tmp_path/"witness-externally-owned.sqlite3"
    env=os.environ.copy()
    env.update(FS_RAI_WITNESS_DB=str(db),FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
        FS_RAI_EXTERNAL_LEDGER=str(db),FS_RAI_BRIDGE_KEY=KEY.decode())
    process,url=start("fs_raw_denial_001_independent_witness.py",env)
    try:
        yield process,url,db
    finally:
        if process.poll() is None:stop(process)

def witness_rows(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route "
                         "FROM external_effects").fetchall()

def proxy(local_url,witness_url):
    env=os.environ.copy()
    env.update(FS_RAI_LOCAL_ACTUATOR_URL=local_url,
        FS_RAI_WITNESS_URL=witness_url,
        FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN)
    return start("fs_raw_denial_001_witness_proxy.py",env)

def test_restoring_both_local_stores_cannot_duplicate_external_witness(tmp_path,witness):
    _,witness_url,witness_db=witness
    authority=tmp_path/"source.sqlite3"
    anchor=tmp_path/"source-anchor.sqlite3"
    saved_source=tmp_path/"source-old.sqlite3"
    saved_anchor=tmp_path/"anchor-old.sqlite3"
    permit,grant_path=grant_payload(tmp_path)
    envelope=json.loads(grant_path.read_text())["envelope"]
    local,pair=start_group(authority,anchor)
    gateway,gateway_url=proxy(pair[0],witness_url)
    try:
        shutil.copyfile(authority,saved_source)
        shutil.copyfile(anchor,saved_anchor)
        code,response=post((gateway_url,authority),"/execute-a",
                           envelope,permit.action_binding_hash)
        assert (code,response["status"])==(200,"WITNESSED_CONSEQUENCE_FORMED")
        initial=witness_rows(witness_db)
        assert initial==[(permit.signature,permit.action_binding_hash,"/execute-a")]
        assert len(commitments(anchor))==1
    finally:
        stop(gateway)
        stop_group(local)

    shutil.copyfile(saved_source,authority)
    shutil.copyfile(saved_anchor,anchor)
    local,pair=start_group(authority,anchor)
    gateway,gateway_url=proxy(pair[0],witness_url)
    try:
        code,response=post((gateway_url,authority),"/execute-b",
                           envelope,permit.action_binding_hash)
        assert (code,response["status"])==(409,"REPLAY_REFUSED")
        assert witness_rows(witness_db)==initial
        # Critical: local anchor was restored and now wrongly records a second
        # local 'formation'. This test only establishes ONE WITNESSED EXTERNAL
        # formation, NOT consistency of source and external systems.
        assert commitments(anchor)==[
            (permit.signature,permit.action_binding_hash,"/execute-b")]
    finally:
        stop(gateway)
        stop_group(local)

def test_external_witness_unavailable_does_not_claim_formation(tmp_path,witness):
    process,url,db=witness
    authority=tmp_path/"authority.sqlite3"
    anchor=tmp_path/"anchor.sqlite3"
    permit,grant_path=grant_payload(tmp_path)
    envelope=json.loads(grant_path.read_text())["envelope"]
    local,pair=start_group(authority,anchor)
    gateway,gateway_url=proxy(pair[0],url)
    try:
        stop(process)
        code,response=post((gateway_url,authority),"/execute-a",
                           envelope,permit.action_binding_hash)
        assert (code,response["status"])==(503,"WITNESS_OUTCOME_UNRESOLVED")
        assert response["formed"] is None
        assert witness_rows(db)==[]
        # Local authority commitment already exists; it must NOT be described
        # as externally formed without independent witness evidence.
        assert len(commitments(anchor))==1
    finally:
        stop(gateway)
        stop_group(local)

def test_witness_refuses_call_without_separate_commit_credential(witness):
    _,url,db=witness
    req=Request(url+"/commit",data=b'{}',method="POST",
                headers={"Content-Type":"application/json"})
    try:
        with urlopen(req,timeout=3) as result:
            code=result.status
    except HTTPError as err:
        code=err.code
    assert code==403
    assert witness_rows(db)==[]
