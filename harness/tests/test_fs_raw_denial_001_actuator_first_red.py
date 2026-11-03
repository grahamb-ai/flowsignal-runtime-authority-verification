"""FS-RAW-DENIAL-001 first RED: real HTTP request to an independently
running local sandbox actuator with its own SQLite consequence record.

The direct route is intentionally unsafe. This is a constructed integration
failure, NOT an exploit of FlowSignal payment services or a real payment.
"""
from contextlib import closing
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json,os,select,sqlite3,subprocess,sys
import pytest
from app.engines.financial_runtime import evaluate_financial
from app.engines.execution_gateway import ExecutionAttempt,validate_execution
from harness.runner import load_scenario

SCENARIO=Path(__file__).parents[1]/"harness"/"scenarios"/"AP-001_allow.json"

@pytest.fixture
def actuator(tmp_path):
    db=tmp_path/"actuator-outcome.sqlite3"
    env=os.environ.copy()
    env["FS_DENIAL_SANDBOX_DB"]=str(db)
    p=subprocess.Popen([sys.executable,"-u","fs_raw_denial_001_sandbox_actuator.py"],
        cwd=Path(__file__).parents[1],env=env,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert select.select([p.stdout],[],[],10)[0],"sandbox actuator startup timeout"
        url="http://127.0.0.1:"+p.stdout.readline().strip()
        yield url,db
    finally:
        p.terminate()
        try:p.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            p.kill();p.communicate(timeout=4)

def post(url,route):
    body=json.dumps({"action":"synthetic.transfer","target":"sandbox:one"}).encode()
    request=Request(url+route,data=body,method="POST",
                    headers={"Content-Type":"application/json"})
    try:
        with urlopen(request,timeout=5) as response:
            return response.status,json.loads(response.read())
    except HTTPError as error:
        return error.code,json.loads(error.read())

def effects(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT target,action,route FROM effects ORDER BY id").fetchall()

def blocked_gateway():
    req=load_scenario(SCENARIO,rebase_to_now=False)
    now=datetime.now(timezone.utc)
    req=replace(req,requested_execution_time=now,
        screening_captured_at=now,mandate_valid_until=now+timedelta(hours=1))
    result,receipt=evaluate_financial(req,sealed_at=now)
    assert result.decision=="ALLOW"
    # A changed execution target lacks this receipt's authority.
    attempted=ExecutionAttempt(
        actor_id=req.actor_id,principal_id=req.principal_id,action=req.action,
        target="another-target",amount=req.amount,currency=req.currency,
        source_account=req.source_account,beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,mandate_id=req.mandate_id,attempted_at=now)
    return validate_execution(receipt,attempted)

def test_existing_gateway_refuses_changed_target(actuator):
    result=blocked_gateway()
    assert result.status=="BLOCKED"
    assert effects(actuator[1])==[]

def test_guarded_http_route_refuses_and_does_not_commit(actuator):
    status,response=post(actuator[0],"/guarded")
    assert status==403 and response["effect_formed"] is False
    assert effects(actuator[1])==[]

def test_direct_http_route_forms_real_sandbox_record(actuator):
    status,response=post(actuator[0],"/direct")
    assert status==200 and response["effect_formed"] is True
    assert effects(actuator[1])==[("sandbox:one","synthetic.transfer","direct")]

def test_first_red_global_route_closure(actuator):
    assert blocked_gateway().status=="BLOCKED"
    assert post(actuator[0],"/direct")[0]==200
    assert effects(actuator[1])==[], (
        "FIRST RED: independent sandbox actuator formed a SQLite-recorded "
        "operation through a direct route after the existing gateway refused."
    )
