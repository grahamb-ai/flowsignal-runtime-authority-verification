"""FS-STRIPE-006 protected TEST executor service — isolated reference process.

Executor owns Stripe TEST credentials, owner-commit credential, RAI verifier
key and a durable attempt ledger. Agent/client supplies only a signed grant,
specific PaymentIntent and exact binding. The service checks signature + bridge
provenance, then uses FS-STRIPE-005 adapter. On repeated requests it NEVER
redispatches a capture. A read-only outcome endpoint reconciles provider state.

Modes: stripe (requires sk_test/rk_test) or explicit fixture (CI only).
Binds loopback; this alone is NOT deployment-grade credential isolation,
institutional authority, provider atomicity or universal route closure.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import hashlib,hmac,json,os,sqlite3

from app.engines.stripe_protected_capture import execute_capture
from app.engines.rai_export_verifier import validate_export
from experiments.fs_stripe_004 import StripeTestClient,post_json

MODE=os.environ.get("FS_STRIPE_EXECUTOR_MODE","stripe")
LEDGER=Path(os.environ["FS_STRIPE_EXECUTOR_LEDGER"])
CLIENT_TOKEN=os.environ["FS_STRIPE_EXECUTOR_CLIENT_TOKEN"]
OWNER_URL=os.environ["FS_STRIPE_EXECUTOR_OWNER_URL"].rstrip("/")
OWNER_TOKEN=os.environ["FS_RAI_WITNESS_COMMIT_TOKEN"]
if MODE not in ("stripe","fixture"):
    raise RuntimeError("unknown executor mode")
if not OWNER_URL.startswith("http://127.0.0.1:"):
    raise RuntimeError("reference executor owner must be loopback")

class FixtureProvider:
    """Persistent mock provider for contract tests; NEVER claims Stripe use."""
    def __init__(self):
        self.path=Path(os.environ["FS_STRIPE_EXECUTOR_FIXTURE_DB"])
    def _read(self,payment_id):
        with closing(sqlite3.connect(self.path)) as db:
            row=db.execute("SELECT status,binding,amount_received FROM payments "
                           "WHERE id=?",(payment_id,)).fetchone()
        if row is None:raise RuntimeError("fixture payment absent")
        return {"id":payment_id,"livemode":False,"currency":"gbp",
            "amount":100,"capture_method":"manual","status":row[0],
            "amount_received":row[2],
            "metadata":{"rai_action_binding_hash":row[1]}}
    def retrieve(self,payment_id):
        return self._read(payment_id)
    def capture(self,payment_id,signature):
        with closing(sqlite3.connect(self.path,timeout=5,isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT status FROM payments WHERE id=?",(payment_id,)).fetchone()
            if row is None or row[0]!="requires_capture":
                db.execute("ROLLBACK")
                raise RuntimeError("fixture provider state")
            db.execute("UPDATE payments SET status='succeeded',amount_received=100,"
                       "captures=captures+1 WHERE id=?",(payment_id,))
            db.execute("COMMIT")
        return self._read(payment_id)

class Owner:
    def commit(self,envelope,action_hash):
        return post_json(OWNER_URL+"/commit",{
            "envelope":envelope,"action_binding_hash":action_hash,
            "route":"/execute-a"},{"X-Witness-Commit-Token":OWNER_TOKEN})

def db_connect():
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    return sqlite3.connect(LEDGER,timeout=5,isolation_level=None)

def initialize():
    with closing(db_connect()) as db:
        db.execute("CREATE TABLE IF NOT EXISTS attempts ("
            "payment_id TEXT PRIMARY KEY, permit_signature TEXT NOT NULL,"
            "action_binding_hash TEXT NOT NULL, status TEXT NOT NULL,"
            "reason TEXT NOT NULL, provider_status TEXT)")

def stored(payment_id):
    with closing(db_connect()) as db:
        return db.execute("SELECT permit_signature,action_binding_hash,status,"
            "reason,provider_status FROM attempts WHERE payment_id=?",(payment_id,)).fetchone()

def record_once(payment_id,signature,binding):
    with closing(db_connect()) as db:
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?)",
                (payment_id,signature,binding,"UNRESOLVED",
                 "ATTEMPT_RECORDED_BEFORE_DISPATCH",None))
            db.execute("COMMIT")
            return True
        except sqlite3.IntegrityError:
            db.execute("ROLLBACK")
            return False

def outcome_update(payment_id,result):
    with closing(db_connect()) as db:
        db.execute("UPDATE attempts SET status=?,reason=?,provider_status=? "
                   "WHERE payment_id=?",
                   (result.status,result.reason,result.provider_status,payment_id))

def safe_result(payment_id,row):
    return {"payment_id":payment_id,"status":row[2],
            "reason":row[3],"provider_status":row[4]}

class Handler(BaseHTTPRequestHandler):
    def authorized(self):
        token=self.headers.get("X-FS-Executor-Token","")
        return hmac.compare_digest(token,CLIENT_TOKEN)

    def do_GET(self):
        if not self.authorized():
            self.reply(403,{"status":"REFUSE","reason":"UNAUTHORIZED_CALLER"});return
        query=urlsplit(self.path)
        if query.path!="/outcome":
            self.reply(404,{"status":"REFUSE","reason":"UNKNOWN_ENDPOINT"});return
        ids=parse_qs(query.query).get("payment_id",[])
        if len(ids)!=1 or not ids[0].startswith("pi_") or len(ids[0])>128:
            self.reply(400,{"status":"REFUSE","reason":"INVALID_PAYMENT_ID"});return
        payment_id=ids[0]
        row=stored(payment_id)
        if row is None:
            self.reply(404,{"status":"UNRESOLVED","reason":"NO_EXECUTOR_RECORD"});return
        # Reconcile on read; never initiate or retry capture from GET.
        result=safe_result(payment_id,row)
        try:
            external=self.server.provider.retrieve(payment_id)
            if (external.get("livemode") is False and
                external.get("status")=="succeeded" and
                external.get("amount_received")==100 and
                external.get("metadata",{}).get("rai_action_binding_hash")==row[1]):
                result.update(status="CONFIRMED",reason="PROVIDER_READBACK_CONFIRMED",
                              provider_status="succeeded")
        except Exception:
            pass
        self.reply(200,result)

    def do_POST(self):
        if not self.authorized():
            self.reply(403,{"status":"REFUSE","reason":"UNAUTHORIZED_CALLER"});return
        if self.path!="/capture":
            self.reply(404,{"status":"REFUSE","reason":"UNKNOWN_ENDPOINT"});return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=12000:raise ValueError("length")
            payload=json.loads(self.rfile.read(n))
            payment_id=payload["payment_id"]
            binding=payload["action_binding_hash"]
            envelope=payload["envelope"]
            if not isinstance(payment_id,str) or not payment_id.startswith("pi_") or len(payment_id)>128:
                raise ValueError("payment id")
            if not isinstance(binding,str) or len(binding)!=64:
                raise ValueError("binding")
            if not isinstance(envelope,dict):raise ValueError("envelope")
            status,permit=validate_export(envelope,os.environ["FS_RAI_BRIDGE_KEY"].encode())
        except (ValueError,KeyError,TypeError,UnicodeDecodeError):
            self.reply(400,{"status":"REFUSE","reason":"MALFORMED_REQUEST"});return
        if status!="VERIFIED" or permit.action_binding_hash!=binding:
            self.reply(403,{"status":"REFUSE","reason":"INVALID_RAI_AUTHORITY"});return
        existing=stored(payment_id)
        if existing is not None:
            if existing[0]!=permit.signature or existing[1]!=binding:
                self.reply(409,{"status":"REFUSE","reason":"PAYMENT_ALREADY_BOUND"});return
            self.reply(200,safe_result(payment_id,existing));return
        if not record_once(payment_id,permit.signature,binding):
            existing=stored(payment_id)
            self.reply(409,{"status":"UNRESOLVED","reason":"CONCURRENT_ATTEMPT",
                            "payment_id":payment_id});return
        result=execute_capture(self.server.provider,Owner(),
             payment_id=payment_id,envelope=envelope,action_hash=binding)
        outcome_update(payment_id,result)
        self.reply(200,asdict(result))

    def reply(self,code,payload):
        raw=json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self,*args):pass

if __name__=="__main__":
    if not CLIENT_TOKEN or not OWNER_TOKEN or not os.environ.get("FS_RAI_BRIDGE_KEY"):
        raise RuntimeError("missing executor credentials")
    provider=FixtureProvider() if MODE=="fixture" else StripeTestClient()
    initialize()
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    server.provider=provider
    server.daemon_threads=True
    print(server.server_port,flush=True)
    server.serve_forever()
