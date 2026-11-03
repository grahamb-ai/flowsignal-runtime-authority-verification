"""FS-RAW-DENIAL-001: sandbox actuator candidate, two real HTTP routes.

The grant issuer is a trusted TEST fixture, not FlowSignal RAI minting.
No real payment or external endpoint. SQLite observed from test process.
"""
from contextlib import closing
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import hashlib,hmac,json,os,select,sqlite3,subprocess,sys,time,uuid
import pytest
from app.engines.financial_runtime import evaluate_financial
from app.engines.execution_gateway import ExecutionAttempt,validate_execution
from harness.runner import load_scenario

KEY="isolated-test-only-key"
TARGET="sandbox:one"
ACTION="synthetic.transfer"
SCENARIO=Path(__file__).parents[1]/"harness"/"scenarios"/"AP-001_allow.json"

@pytest.fixture
def service(tmp_path):
    db=tmp_path/"independent-actuator.sqlite3"
    env=os.environ.copy()
    env.update(FS_DENIAL_SANDBOX_DB=str(db),FS_DENIAL_TEST_KEY=KEY)
    p=subprocess.Popen([sys.executable,"-u","fs_raw_denial_001_grant_actuator.py"],
        cwd=Path(__file__).parents[1],env=env,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True)
    try:
        assert select.select([p.stdout],[],[],10)[0]
        yield "http://127.0.0.1:"+p.stdout.readline().strip(),db
    finally:
        p.terminate()
        try:p.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            p.kill();p.communicate(timeout=4)

def grant(*,target=TARGET,action=ACTION,expires=None,key=KEY,nonce=None):
    raw={"target":target,"action":action,
         "expires_at":int(time.time())+60 if expires is None else expires,
         "nonce":nonce or str(uuid.uuid4())}
    canonical=json.dumps(raw,sort_keys=True,separators=(",",":")).encode()
    raw["signature"]=hmac.new(key.encode(),canonical,hashlib.sha256).hexdigest()
    return raw

def post(s,route,gr=None,*,target=TARGET,action=ACTION):
    payload=json.dumps({"target":target,"action":action,"grant":gr}).encode()
    req=Request(s[0]+route,data=payload,method="POST",
                headers={"Content-Type":"application/json"})
    try:
        with urlopen(req,timeout=6) as r:
            return r.status,json.loads(r.read())
    except HTTPError as r:
        return r.code,json.loads(r.read())

def rows(s):
    with closing(sqlite3.connect(f"file:{s[1]}?mode=ro",uri=True)) as c:
        return c.execute("SELECT target,action,route,nonce FROM effects").fetchall()

def actual_gateway_refusal():
    req=load_scenario(SCENARIO,rebase_to_now=False)
    now=datetime.now(timezone.utc)
    req=replace(req,requested_execution_time=now,
        screening_captured_at=now,mandate_valid_until=now+timedelta(hours=1))
    decision,receipt=evaluate_financial(req,sealed_at=now)
    assert decision.decision=="ALLOW"
    attempt=ExecutionAttempt(actor_id=req.actor_id,principal_id=req.principal_id,
        action=req.action,target="unapproved-target",amount=req.amount,currency=req.currency,
        source_account=req.source_account,beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,mandate_id=req.mandate_id,attempted_at=now)
    return validate_execution(receipt,attempt)

@pytest.mark.parametrize("route",["/guarded","/direct"])
def test_refused_gateway_and_no_grant_cannot_commit(service,route):
    assert actual_gateway_refusal().status=="BLOCKED"
    status,result=post(service,route)
    assert status==403 and not result["formed"]
    assert rows(service)==[]

@pytest.mark.parametrize("route",["/guarded","/direct"])
def test_valid_test_issuer_grant_commits_once(service,route):
    g=grant()
    assert post(service,route,g)[1]["formed"]
    recorded=rows(service)
    assert len(recorded)==1 and recorded[0][:3]==(TARGET,ACTION,route)
    code,result=post(service,route,g)
    assert (code,result["status"])==(409,"REPLAY_REFUSED")
    assert rows(service)==recorded

def test_signed_grant_cannot_be_reused_via_other_route(service):
    g=grant()
    assert post(service,"/guarded",g)[0]==200
    assert post(service,"/direct",g)[0]==409
    assert len(rows(service))==1

def test_wrong_signer_and_tampering_refused(service):
    incorrect=grant(key="wrong-test-key")
    assert post(service,"/direct",incorrect)[0]==403
    tampered=grant()
    tampered["target"]="different"
    assert post(service,"/direct",tampered,target="different")[0]==403
    assert rows(service)==[]

def test_binding_mismatch_and_expiry_refused(service):
    g=grant()
    assert post(service,"/direct",g,target="other")[1]["status"]=="GRANT_OPERATION_MISMATCH"
    expired=grant(expires=int(time.time())-2)
    assert post(service,"/guarded",expired)[1]["status"]=="EXPIRED_GRANT"
    assert rows(service)==[]

def test_unknown_transport_route_does_not_commit(service):
    assert post(service,"/unknown",grant())[0]==404
    assert rows(service)==[]
