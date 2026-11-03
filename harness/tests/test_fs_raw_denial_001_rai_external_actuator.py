"""FS-RAW-DENIAL-001 genuine RAI source -> separate HTTP actuator.

No monkeypatching of issuance, provenance or permit signing. Bridge key/test
actuator credentials are local fixtures; no production authority claim.
"""
from contextlib import closing
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json,os,select,sqlite3,subprocess,sys
import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.execution_gateway import ExecutionAttempt,validate_execution
from app.engines.financial_runtime import evaluate_financial
from app.engines.runtime_authority_payment import prepare_payment_execution,mint_rai_bound_execution_permit
from app.engines.rai_external_export_reference import export_final_bind
from harness.runner import load_scenario

KEY=b"test-only-rai-bridge-key"
SCENARIO=Path(__file__).parents[1]/"harness"/"scenarios"/"AP-001_allow.json"

@pytest.fixture(autouse=True)
def usage_state():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def actuator(tmp_path):
    db=tmp_path/"external-outcome.sqlite3"
    env=os.environ.copy()
    env.update(FS_RAI_EXTERNAL_LEDGER=str(db),FS_RAI_BRIDGE_KEY=KEY.decode())
    p=subprocess.Popen([sys.executable,"-u","fs_raw_denial_001_rai_actuator.py"],
      cwd=Path(__file__).parents[1],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert select.select([p.stdout],[],[],10)[0],"actuator startup timeout"
        port=int(p.stdout.readline().strip())
        yield f"http://127.0.0.1:{port}",db
    finally:
        p.terminate()
        try:p.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            p.kill();p.communicate(timeout=4)

def request():
    r=load_scenario(SCENARIO,rebase_to_now=False)
    now=datetime.now(timezone.utc)
    return replace(r,requested_execution_time=now,
       screening_captured_at=now,mandate_valid_until=now+timedelta(hours=1))

def attempt(req):
    return ExecutionAttempt(actor_id=req.actor_id,principal_id=req.principal_id,
        action=req.action,target=req.target,amount=req.amount,currency=req.currency,
        source_account=req.source_account,beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time)

def mint(req):
    prepared=prepare_payment_execution(req,route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",resolved_at=req.requested_execution_time)
    permit=mint_rai_bound_execution_permit(req,prepared,
        bind_at=req.requested_execution_time)
    return permit

def post(actuator,route,envelope,binding=None):
    payload=json.dumps({"envelope":envelope,"action_binding_hash":binding}).encode()
    r=Request(actuator[0]+route,data=payload,method="POST",
              headers={"Content-Type":"application/json"})
    try:
        with urlopen(r,timeout=6) as response:
            return response.status,json.loads(response.read())
    except HTTPError as response:
        return response.code,json.loads(response.read())

def rows(actuator):
    with closing(sqlite3.connect(f"file:{actuator[1]}?mode=ro",uri=True)) as con:
        return con.execute("SELECT permit_signature,action_binding_hash,route FROM external_effects").fetchall()

def test_no_external_grant_after_failed_final_bind(actuator):
    req=request()
    prepared=prepare_payment_execution(req,route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",resolved_at=req.requested_execution_time)
    changed=replace(req,beneficiary_account_reference="NOT-AUTHORISED")
    permit=mint_rai_bound_execution_permit(changed,prepared,
        bind_at=req.requested_execution_time)
    assert permit is None
    assert export_final_bind(permit,bridge_key=KEY) is None
    for route in ("/execute-a","/execute-b"):
        code,result=post(actuator,route,None)
        assert code==403 and not result["formed"]
    assert rows(actuator)==[]

@pytest.mark.parametrize("route,other_route",[("/execute-a","/execute-b"),("/execute-b","/execute-a")])
def test_true_rai_final_bind_forms_exactly_one_external_reference_effect(actuator,route,other_route):
    req=request()
    permit=mint(req)
    assert permit is not None
    envelope=export_final_bind(permit,bridge_key=KEY)
    assert envelope is not None
    code,result=post(actuator,route,envelope,permit.action_binding_hash)
    assert (code,result["status"])==(200,"CONSEQUENCE_FORMED")
    assert rows(actuator)==[(permit.signature,permit.action_binding_hash,route)]
    code,replay=post(actuator,other_route,envelope,permit.action_binding_hash)
    assert (code,replay["status"])==(409,"REPLAY_REFUSED")
    assert len(rows(actuator))==1

def test_original_legacy_gateway_permit_cannot_export_final_bind(actuator):
    req=request()
    response,receipt=evaluate_financial(req,sealed_at=req.requested_execution_time)
    assert response.decision=="ALLOW"
    gateway=validate_execution(receipt,attempt(req))
    assert gateway.status=="PERMITTED"
    assert export_final_bind(gateway.execution_permit,bridge_key=KEY) is None
    assert post(actuator,"/execute-b",None)[0]==403
    assert rows(actuator)==[]

def test_forged_bridge_assertion_is_refused(actuator):
    permit=mint(request())
    env=export_final_bind(permit,bridge_key=KEY)
    assert env is not None
    env["bridge_mac"]="0"*64
    assert post(actuator,"/execute-b",env,permit.action_binding_hash)[0]==403
    assert rows(actuator)==[]

def test_altered_operation_binding_is_refused(actuator):
    permit=mint(request())
    env=export_final_bind(permit,bridge_key=KEY)
    assert post(actuator,"/execute-b",env,"b"*64)[1]["status"]=="EXECUTION_BINDING_MISMATCH"
    assert rows(actuator)==[]

def test_signed_permit_field_tampering_is_refused(actuator):
    permit=mint(request())
    env=export_final_bind(permit,bridge_key=KEY)
    env["permit"]["authority_state_version"]+=1
    code,result=post(actuator,"/execute-a",env,permit.action_binding_hash)
    assert code==403 and result["status"]=="INVALID_RAI_PERMIT"
    assert rows(actuator)==[]



def test_first_red_revocation_after_export_must_prevent_external_commit(actuator):
    """Expect RED until external actuator can verify current authority.

    Genuine final-bind permit and bridge assertion were valid at export;
    advancing authority in source process must make them inadmissible NOW.
    """
    from app.engines.authority_store import (
        advance_authority_state_version, get_authority_state_version
    )
    permit=mint(request())
    envelope=export_final_bind(permit,bridge_key=KEY)
    assert envelope is not None
    assert permit.authority_state_version==get_authority_state_version()
    advance_authority_state_version()
    assert permit.authority_state_version!=get_authority_state_version()
    code,result=post(actuator,"/execute-b",envelope,permit.action_binding_hash)
    assert code==403 and result["formed"] is False and rows(actuator)==[], (
        "FIRST RED: actuator accepted a previously exported grant after the "
        "source authority version changed; cross-process freshness is missing. "
        f"Actual HTTP status={code}, response={result}, ledger={rows(actuator)}"
    )
