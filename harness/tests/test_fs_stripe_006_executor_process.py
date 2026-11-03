"""FS-STRIPE-006 integration against actual separate executor process.

All payment provider effects here are synthetic fixture writes, NOT Stripe
transactions. Genuine RAI mint / final-bind and authority owner are used.
"""
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import json,os,select,sqlite3,subprocess,sys
import pytest

from app.engines.authority_store import advance_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from experiments.fs_stripe_004 import (
    AuthorityOwner,rai_permit_for_payment,BRIDGE_KEY,OWNER_COMMIT,
)
from test_fs_raw_denial_001_online_authority import stop

ROOT=Path(__file__).parents[1]
CLIENT_TOKEN="test-executor-client"

@pytest.fixture(autouse=True)
def clean_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def setup(tmp_path):
    with AuthorityOwner(tmp_path) as owner:
        provider_db=tmp_path/"fixture-provider.sqlite3"
        with closing(sqlite3.connect(provider_db)) as db:
            db.execute("CREATE TABLE payments (id TEXT PRIMARY KEY, status TEXT,"
                       "binding TEXT,amount_received INTEGER,captures INTEGER)")
            db.commit()
        ledger=tmp_path/"executor-state.sqlite3"
        env=os.environ.copy()
        env.pop("STRIPE_TEST_SECRET_KEY",None)
        env.update(FS_STRIPE_EXECUTOR_MODE="fixture",
            FS_STRIPE_EXECUTOR_FIXTURE_DB=str(provider_db),
            FS_STRIPE_EXECUTOR_LEDGER=str(ledger),
            FS_STRIPE_EXECUTOR_CLIENT_TOKEN=CLIENT_TOKEN,
            FS_STRIPE_EXECUTOR_OWNER_URL=owner.url,
            FS_RAI_WITNESS_COMMIT_TOKEN=OWNER_COMMIT,
            FS_RAI_BRIDGE_KEY=BRIDGE_KEY.decode())
        def launch():
            process=subprocess.Popen(
                [sys.executable,"-u","fs_stripe_006_executor_service.py"],
                cwd=ROOT,env=env,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,text=True)
            assert select.select([process.stdout],[],[],8)[0],"executor startup timeout"
            return process,"http://127.0.0.1:"+process.stdout.readline().strip()
        proc,url=launch()
        try:
            yield {"owner":owner,"provider_db":provider_db,"ledger":ledger,
                   "proc":proc,"url":url,"launch":launch}
        finally:
            if proc.poll() is None:stop(proc)
            # A test can restart the service; clean it separately there.

def case(setup,payment_id="pi_fs006_001",amount=100):
    permit,grant=rai_permit_for_payment(payment_id)
    with closing(sqlite3.connect(setup["provider_db"])) as db:
        db.execute("INSERT INTO payments VALUES(?,?,?,?,?)",
            (payment_id,"requires_capture",permit.action_binding_hash,0,0))
        db.commit()
    return permit,{"payment_id":payment_id,
                   "action_binding_hash":permit.action_binding_hash,
                   "envelope":grant}

def request(url,path,body=None,token=CLIENT_TOKEN):
    headers={"X-FS-Executor-Token":token}
    data=None if body is None else json.dumps(body).encode()
    if data is not None:headers["Content-Type"]="application/json"
    req=Request(url+path,data=data,headers=headers,
                method="POST" if body is not None else "GET")
    try:
        with urlopen(req,timeout=8) as response:
            return response.status,json.loads(response.read())
    except HTTPError as response:
        return response.code,json.loads(response.read())

def provider_state(setup,pid):
    with closing(sqlite3.connect(setup["provider_db"])) as db:
        return db.execute("SELECT status,amount_received,captures FROM payments "
                          "WHERE id=?",(pid,)).fetchone()

def ledger_rows(setup):
    with closing(sqlite3.connect(setup["ledger"])) as db:
        return db.execute("SELECT payment_id,status FROM attempts").fetchall()

def test_real_signed_grant_to_subprocess_executor_confirmed_once(setup):
    permit,body=case(setup)
    status,result=request(setup["url"],"/capture",body)
    assert (status,result["status"])==(200,"CONFIRMED")
    assert provider_state(setup,body["payment_id"])==("succeeded",100,1)
    status,again=request(setup["url"],"/capture",body)
    assert status==200 and again["status"]=="CONFIRMED"
    assert provider_state(setup,body["payment_id"])==("succeeded",100,1)
    status,outcome=request(setup["url"],
        "/outcome?"+urlencode({"payment_id":body["payment_id"]}))
    assert status==200 and outcome["status"]=="CONFIRMED"
    assert len(ledger_rows(setup))==1

def test_revocation_owner_prevents_external_fixture_effect(setup):
    permit,body=case(setup)
    assert advance_authority_state_version()>permit.authority_state_version
    status,result=request(setup["url"],"/capture",body)
    assert (status,result["status"])==(200,"REFUSE")
    assert provider_state(setup,body["payment_id"])==("requires_capture",0,0)

def test_uncredentialed_client_cannot_call_capture_or_outcome(setup):
    _,body=case(setup)
    assert request(setup["url"],"/capture",body,token="unauthorised")[0]==403
    assert request(setup["url"],"/outcome?payment_id=pi_fs006_001",
                   token="unauthorised")[0]==403
    assert ledger_rows(setup)==[]
    assert provider_state(setup,body["payment_id"])[2]==0

def test_tampered_grant_cannot_reach_provider_or_owner(setup):
    _,body=case(setup)
    body["envelope"]["bridge_mac"]="0"*64
    status,result=request(setup["url"],"/capture",body)
    assert status==403
    assert ledger_rows(setup)==[]
    assert provider_state(setup,body["payment_id"])[2]==0

def test_provider_binding_mismatch_refuses(setup):
    _,body=case(setup)
    with closing(sqlite3.connect(setup["provider_db"])) as db:
        db.execute("UPDATE payments SET binding=? WHERE id=?",
                   ("b"*64,body["payment_id"]))
        db.commit()
    _,result=request(setup["url"],"/capture",body)
    assert result["reason"]=="PROVIDER_OPERATION_MISMATCH"
    assert provider_state(setup,body["payment_id"])[2]==0

def test_executor_restart_uses_persistent_ledger_and_never_recaptures(setup):
    _,body=case(setup)
    assert request(setup["url"],"/capture",body)[1]["status"]=="CONFIRMED"
    stop(setup["proc"])
    fresh,url=setup["launch"]()
    try:
        _,replay=request(url,"/capture",body)
        assert replay["status"]=="CONFIRMED"
        assert provider_state(setup,body["payment_id"])[2]==1
        assert request(url,"/outcome?payment_id="+body["payment_id"])[1]["status"]=="CONFIRMED"
    finally:
        stop(fresh)

def test_same_payment_id_with_different_grant_is_refused_without_reexecution(setup):
    _,body=case(setup)
    assert request(setup["url"],"/capture",body)[1]["status"]=="CONFIRMED"
    different=dict(body)
    different["envelope"]=dict(body["envelope"])
    different["envelope"]["permit"]=dict(body["envelope"]["permit"])
    different["envelope"]["permit"]["signature"]="different"
    assert request(setup["url"],"/capture",different)[0]==403
    assert provider_state(setup,body["payment_id"])[2]==1
