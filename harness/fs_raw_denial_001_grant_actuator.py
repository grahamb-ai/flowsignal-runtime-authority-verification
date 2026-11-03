"""FS-RAW-DENIAL-001 candidate: two HTTP interfaces, one grant-gated actuator.

Independent loopback process and SQLite outcome ledger. Both /guarded and
/direct require an authenticated exact-operation grant. A toy HMAC key is
supplied via environment solely for reference integration testing.
NOT connected to FlowSignal RAI minting, production KMS, or payment rails.
"""
import hashlib
import hmac
import json
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DB=Path(os.environ["FS_DENIAL_SANDBOX_DB"])
KEY=os.environ["FS_DENIAL_TEST_KEY"].encode()

def canonical(grant):
    return json.dumps({k:grant[k] for k in ("action","target","expires_at","nonce")},
        sort_keys=True,separators=(",",":")).encode()

def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(DB),timeout=5,isolation_level=None)
    c.execute("CREATE TABLE IF NOT EXISTS effects (id INTEGER PRIMARY KEY, target TEXT NOT NULL, action TEXT NOT NULL, route TEXT NOT NULL, nonce TEXT NOT NULL UNIQUE)")
    return c

def verify(grant,requested):
    if not isinstance(grant,dict):
        return "MISSING_GRANT"
    if not all(k in grant for k in ("action","target","expires_at","nonce","signature")):
        return "INVALID_GRANT"
    try:
        if not isinstance(grant["nonce"],str) or not grant["nonce"]:
            return "INVALID_GRANT"
        if not isinstance(grant["expires_at"],int):
            return "INVALID_GRANT"
        mac=hmac.new(KEY,canonical(grant),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac,str(grant["signature"])):
            return "INVALID_SIGNATURE"
        if (grant["action"],grant["target"])!=(requested.get("action"),requested.get("target")):
            return "GRANT_OPERATION_MISMATCH"
        if int(time.time())>=grant["expires_at"]:
            return "EXPIRED_GRANT"
    except (TypeError,KeyError,ValueError):
        return "INVALID_GRANT"
    return "VERIFIED"

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/guarded","/direct"):
            self.reply(404,{"status":"UNKNOWN_ROUTE","formed":False});return
        try:
            size=int(self.headers.get("Content-Length","0"))
            if not (0<size<=4096):
                self.reply(400,{"status":"INVALID_REQUEST","formed":False});return
            payload=json.loads(self.rfile.read(size))
            if not isinstance(payload,dict):
                raise ValueError("not a mapping")
        except (ValueError,UnicodeDecodeError):
            self.reply(400,{"status":"INVALID_REQUEST","formed":False});return
        result=verify(payload.get("grant"),payload)
        if result!="VERIFIED":
            self.reply(403,{"status":result,"formed":False});return
        grant=payload["grant"]
        with connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO effects(target,action,route,nonce) VALUES(?,?,?,?)",
                           (grant["target"],grant["action"],self.path,grant["nonce"]))
                db.execute("COMMIT")
            except sqlite3.IntegrityError:
                db.execute("ROLLBACK")
                self.reply(409,{"status":"REPLAY_REFUSED","formed":False});return
        self.reply(200,{"status":"COMMITTED","formed":True})
    def reply(self,code,payload):
        raw=json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self,*args):pass

if __name__=="__main__":
    with connect():pass
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
