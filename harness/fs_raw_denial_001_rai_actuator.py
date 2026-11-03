"""Localhost-only independently running RAI assertion consumer.

Verifies both the original signed permit and a post-final-bind bridge assertion
from the source process. It cannot itself reproduce the in-process provenance
registry; the bridge is a trusted reference authority. No external payments.
"""
from datetime import datetime,timezone
from contextlib import closing
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import hashlib,hmac,json,os,sqlite3,time
from app.engines.permit_authority import ExecutionPermit,verify_execution_permit
from app.engines.rai_external_export_reference import canonical

DB=Path(os.environ["FS_RAI_EXTERNAL_LEDGER"])
BRIDGE_KEY=os.environ["FS_RAI_BRIDGE_KEY"].encode()
MAX_AUTHORITY_AGE=float(os.environ.get("FS_RAI_AUTHORITY_MAX_AGE_SECONDS","3"))

def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=5,isolation_level=None)
    c.execute("CREATE TABLE IF NOT EXISTS external_effects (permit_signature TEXT PRIMARY KEY, action_binding_hash TEXT NOT NULL, route TEXT NOT NULL)")
    return c

def validate(envelope):
    if not isinstance(envelope,dict):
        return "MISSING_FINAL_BIND_ASSERTION",None
    try:
        permit=ExecutionPermit(**envelope["permit"])
        statement=envelope["statement"]
        provided=envelope["bridge_mac"]
        if not isinstance(provided,str):return "BAD_ASSERTION",None
        expected=hmac.new(BRIDGE_KEY,canonical(statement),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided,expected):
            return "UNTRUSTED_BRIDGE_ASSERTION",None
        if not verify_execution_permit(permit):
            return "INVALID_RAI_PERMIT",None
        required=("determination_id","constraint_id","operation_id","execution_attempt_id","provenance_id")
        if not all(isinstance(statement.get(k),str) and statement[k] for k in required):
            return "MISSING_FINAL_BIND_PROVENANCE",None
        if (statement["permit_signature"]!=permit.signature or
            statement["action_binding_hash"]!=permit.action_binding_hash or
            statement["determination_id"]!=permit.rai_determination_id or
            statement["constraint_id"]!=permit.rai_constraint_id or
            statement["operation_id"]!=permit.rai_protected_operation_id or
            statement["execution_attempt_id"]!=permit.rai_execution_attempt_id):
            return "FINAL_BIND_CORRESPONDENCE_INVALID",None
        if permit.valid_until is None or datetime.now(timezone.utc)>datetime.fromisoformat(permit.valid_until).astimezone(timezone.utc):
            return "PERMIT_EXPIRED",None
    except (KeyError,TypeError,ValueError,AttributeError):
        return "INVALID_ENVELOPE",None
    return "VERIFIED",permit

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/execute-a","/execute-b"):
            self.reply(404,{"status":"UNKNOWN_ROUTE","formed":False});return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if n<1 or n>12000:
                self.reply(400,{"status":"INVALID_REQUEST","formed":False});return
            payload=json.loads(self.rfile.read(n))
        except (TypeError,ValueError,UnicodeDecodeError):
            self.reply(400,{"status":"INVALID_REQUEST","formed":False});return
        status,permit=validate(payload.get("envelope") if isinstance(payload,dict) else None)
        if status!="VERIFIED":
            self.reply(403,{"status":status,"formed":False});return
        if payload.get("action_binding_hash")!=permit.action_binding_hash:
            self.reply(403,{"status":"EXECUTION_BINDING_MISMATCH","formed":False});return
        with closing(connect()) as c:
            try:
                c.execute("BEGIN IMMEDIATE")
                try:
                    row=c.execute("SELECT version,observed_at FROM authority_fence WHERE singleton=1").fetchone()
                except sqlite3.OperationalError:
                    row=None
                if row is None:
                    c.execute("ROLLBACK")
                    self.reply(403,{"status":"AUTHORITY_STATE_UNAVAILABLE","formed":False});return
                age=time.time()-row[1]
                if MAX_AUTHORITY_AGE<=0 or age<0 or age>MAX_AUTHORITY_AGE:
                    c.execute("ROLLBACK")
                    self.reply(403,{"status":"AUTHORITY_STATE_FRESHNESS_EXPIRED","formed":False});return
                if row[0]!=permit.authority_state_version:
                    c.execute("ROLLBACK")
                    self.reply(403,{"status":"AUTHORITY_STATE_STALE","formed":False});return
                c.execute("INSERT INTO external_effects VALUES(?,?,?)",
                    (permit.signature,permit.action_binding_hash,self.path))
                c.execute("COMMIT")
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                self.reply(409,{"status":"REPLAY_REFUSED","formed":False});return
        self.reply(200,{"status":"CONSEQUENCE_FORMED","formed":True})
    def reply(self,status,payload):
        raw=json.dumps(payload).encode()
        self.send_response(status);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def log_message(self,*args):pass

if __name__=="__main__":
    with connect():pass
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
