"""FS-RAW-DENIAL-001 localhost-only HTTP adapter to EXISTING reference executor.

A test service, not a hardened network security boundary. No external payment
provider, customer data, production environment, shell commands, or autonomous
agent is involved. The parent test independently reads the SQLite outcome DB.
"""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.engines.execution_gateway import ExecutionAttempt, action_binding_hash, validate_execution
from app.engines.financial_runtime import evaluate_financial
from app.engines.runtime_authority_payment import prepare_payment_execution, mint_rai_bound_execution_permit
from app.engines.protected_consequence import execute_protected_consequence
from harness.runner import load_scenario

SCENARIO = Path(__file__).parent / "harness" / "scenarios" / "AP-001_allow.json"
STATE = {}

def fixture_request():
    req=load_scenario(SCENARIO,rebase_to_now=False)
    now=datetime.now(timezone.utc)
    return replace(req,requested_execution_time=now,screening_captured_at=now,
                   mandate_valid_until=now+timedelta(hours=1))

def action_attempt(req):
    return ExecutionAttempt(actor_id=req.actor_id,principal_id=req.principal_id,
        action=req.action,target=req.target,amount=req.amount,currency=req.currency,
        source_account=req.source_account,beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time)

def handle(kind):
    if kind == "no-permit":
        return {"outcome":execute_protected_consequence(None,"nonexistent"),
                "signature":None}
    if kind == "replay":
        permit=STATE.get("last_permit")
        if permit is None:
            return {"outcome":"NOT_PREPARED","signature":None}
        return {"outcome":execute_protected_consequence(permit,permit.action_binding_hash),
                "signature":permit.signature}
    req=fixture_request()
    if kind=="legacy":
        response,receipt=evaluate_financial(req,sealed_at=req.requested_execution_time)
        gateway=validate_execution(receipt,action_attempt(req))
        permit=gateway.execution_permit
    elif kind in ("rai","rai-substitute"):
        prepared=prepare_payment_execution(req,route_id="R1",
            executor_id="PAYMENT-EXECUTOR-1",resolved_at=req.requested_execution_time)
        bind_req=req if kind=="rai" else replace(req,beneficiary_account_reference="UNAPPROVED-ACCOUNT")
        permit=mint_rai_bound_execution_permit(bind_req,prepared,
                                               bind_at=req.requested_execution_time)
    else:
        return {"outcome":"UNSUPPORTED_ROUTE","signature":None}
    binding=action_binding_hash(action_attempt(req))
    outcome=execute_protected_consequence(permit,binding)
    if kind=="rai" and permit is not None:
        STATE["last_permit"]=permit
    return {"outcome":outcome,"signature":permit.signature if permit else None,
            "action_binding_hash":binding}

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length=int(self.headers.get("Content-Length","0"))
        if length>0:
            self.rfile.read(min(length,4096))
        try:
            result=handle(self.path.removeprefix("/"))
            status=200
        except Exception as exc:
            result={"error":type(exc).__name__,"detail":str(exc)}
            status=500
        output=json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(output)))
        self.end_headers()
        self.wfile.write(output)
    def log_message(self,*args):
        pass

if __name__=="__main__":
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
