"""Local HTTP transport integration — actual reference executor + SQLite witness.

Runs only on 127.0.0.1. Service process cannot access external payment rails.
Reads SQLite consequence store from test process, not service response alone.
"""
import json
import os
import select
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

HARNESS_ROOT=Path(__file__).parents[1]

@pytest.fixture
def service(tmp_path):
    db=tmp_path/"outcomes.sqlite3"
    env=os.environ.copy()
    env.update({
       "FLOWSIGNAL_PERMIT_CONSUMPTION_STORE":str(tmp_path/"permits.sqlite3"),
       "FLOWSIGNAL_CONSEQUENCE_OUTCOME_STORE":str(db),
       "FLOWSIGNAL_ROLLBACK_ANCHOR_STORE":str(tmp_path/"anchor.sqlite3"),
    })
    p=subprocess.Popen([sys.executable,"-u","fs_raw_denial_001_local_http.py"],
        cwd=HARNESS_ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True)
    try:
        assert select.select([p.stdout],[],[],10)[0], "HTTP service readiness timeout"
        port=int(p.stdout.readline().strip())
        yield (f"http://127.0.0.1:{port}",db)
    finally:
        p.terminate()
        try:p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate(timeout=5)

def invoke(service,route):
    address,_=service
    request=Request(f"{address}/{route}",data=b"{}",method="POST",
                    headers={"Content-Type":"application/json"})
    with urlopen(request,timeout=10) as response:
        assert response.status==200
        return json.loads(response.read())

def witnessed_rows(db):
    if not db.exists():
        return []
    with sqlite3.connect(f"file:{db}?mode=ro",uri=True) as conn:
        return conn.execute("SELECT permit_signature,action_binding_hash,outcome "
                            "FROM consequence_outcomes ORDER BY permit_signature").fetchall()

def test_legacy_route_denied_no_sqlite_consequence(service):
    result=invoke(service,"legacy")
    assert result["outcome"]=="DENIED_RAI_EXECUTION_BINDING_REQUIRED"
    assert witnessed_rows(service[1])==[]

def test_actual_rai_final_bind_forms_one_witnessed_consequence_and_replay_refused(service):
    result=invoke(service,"rai")
    assert result["outcome"]=="CONSEQUENCE_FORMED"
    rows=witnessed_rows(service[1])
    assert len(rows)==1
    assert rows[0]==(result["signature"],result["action_binding_hash"],"CONSEQUENCE_FORMED")
    repeated=invoke(service,"replay")
    assert repeated["outcome"]=="DENIED_EXECUTION_PERMIT_REPLAY"
    assert witnessed_rows(service[1])==rows

def test_substituted_beneficiary_refused_before_consequence(service):
    result=invoke(service,"rai-substitute")
    assert result["outcome"]=="DENIED_NO_EXECUTION_PERMIT"
    assert witnessed_rows(service[1])==[]

def test_http_no_permit_does_not_form_consequence(service):
    result=invoke(service,"no-permit")
    assert result["outcome"]=="DENIED_NO_EXECUTION_PERMIT"
    assert witnessed_rows(service[1])==[]

def test_unknown_http_route_has_no_execution(service):
    result=invoke(service,"unknown")
    assert result["outcome"]=="UNSUPPORTED_ROUTE"
    assert witnessed_rows(service[1])==[]
