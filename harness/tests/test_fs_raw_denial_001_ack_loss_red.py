"""FS-RAW-DENIAL-001 loss-of-acknowledgement FIRST RED.

One local authority service records synthetic effect, drops its response,
and actuator returns UNKNOWN/UNRESOLVED. A caller then asks the authority
source for authoritative disposition: this endpoint is initially absent.
No live payments or production process; effect rows checked independently.
"""
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import json,os,sqlite3
import pytest
from app.engines.authority_store import get_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_online_authority import start,stop,READER,ADMIN
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request,post
from app.engines.rai_external_export_reference import export_final_bind

TOKEN="test-source-commit-only"
@pytest.fixture(autouse=True)
def usage_reset():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def services(tmp_path):
    db=tmp_path/"source.sqlite3"
    env=os.environ.copy()
    env.update(FS_RAI_SOURCE_DB=str(db),FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,FS_RAI_SOURCE_COMMIT_TOKEN=TOKEN,
        FS_RAI_SOURCE_INITIAL_VERSION=str(get_authority_state_version()),
        FS_RAI_EXTERNAL_LEDGER=str(db),FS_RAI_BRIDGE_KEY=KEY.decode())
    source,source_url=start("fs_raw_denial_001_recovery_source.py",env)
    actuator_env=os.environ.copy()
    actuator_env.update(FS_RAI_EXTERNAL_LEDGER=str(db),FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_AUTHORITY_SOURCE_URL=source_url,FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_COMMIT_TOKEN=TOKEN)
    actuator,actuator_url=start("fs_raw_denial_001_atomic_actuator.py",actuator_env)
    result={"source":source,"source_url":source_url,
            "actuator":actuator,"pair":(actuator_url,db),"db":db}
    try:yield result
    finally:
        stop(actuator)
        if source.poll() is None:stop(source)

def recorded(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route FROM committed_effects").fetchall()

def commit_with_lost_ack(services):
    permit=mint(request())
    assert permit is not None
    envelope=export_final_bind(permit,bridge_key=KEY)
    assert envelope is not None
    code,response=post(services["pair"],"/execute-a",envelope,permit.action_binding_hash)
    return permit,envelope,code,response

def ask_outcome(services,signature):
    url=services["source_url"]+"/outcome?signature="+signature
    req=Request(url,headers={"X-Authority-Read-Token":READER})
    try:
        with urlopen(req,timeout=3) as response:
            return response.status,json.loads(response.read())
    except HTTPError as err:
        return err.code,json.loads(err.read())

def test_commit_is_recorded_but_acknowledgement_is_unresolved(services):
    permit,_,code,response=commit_with_lost_ack(services)
    assert (code,response["status"])==(503,"COMMIT_OUTCOME_UNRESOLVED")
    assert response["formed"] is None
    assert recorded(services["db"])==[
        (permit.signature,permit.action_binding_hash,"/execute-a")]

def test_first_red_authoritative_outcome_recovery_after_ack_loss(services):
    permit,_,code,response=commit_with_lost_ack(services)
    assert code==503 and response["formed"] is None
    # User cannot safely retry as if nothing happened. An authoritative,
    # authenticated outcome read is required before classifying the result.
    status,outcome=ask_outcome(services,permit.signature)
    assert status==200 and outcome.get("status")=="CONSEQUENCE_FORMED", (
        "FIRST RED: the source committed the synthetic consequence and the "
        "acknowledgement was lost, but there is no authenticated outcome "
        f"recovery contract. Actual HTTP={status}, payload={outcome}"
    )
