"""Independent loopback synthetic consequence witness (test only).

Own process, own SQLite file. The local source/anchor rollback never touches this
ledger. This service models a consequence counterparty, not a live bank. It
verifies the genuine reference permit and trusted bridge assertion, and
atomically deduplicates permit signatures. Test HMAC/headers are NOT hardened.
"""
from contextlib import closing
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import json,os,sqlite3

from fs_raw_denial_001_rai_actuator import validate

DB=Path(os.environ["FS_RAI_WITNESS_DB"])
TOKEN=os.environ["FS_RAI_WITNESS_COMMIT_TOKEN"]

def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    connection=sqlite3.connect(str(DB),timeout=5,isolation_level=None)
    connection.execute("CREATE TABLE IF NOT EXISTS external_effects ("
        "permit_signature TEXT PRIMARY KEY, action_binding_hash TEXT NOT NULL,"
        "route TEXT NOT NULL)")
    return connection

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path!="/commit":
            self.reply(404,{"status":"UNKNOWN_PATH","formed":None});return
        if self.headers.get("X-Witness-Commit-Token")!=TOKEN:
            self.reply(403,{"status":"UNAUTHORIZED_WITNESS_CALLER","formed":False});return
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=12000:raise ValueError("length")
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):raise ValueError("body")
            route=payload.get("route")
            if route not in ("/execute-a","/execute-b"):raise ValueError("route")
        except (TypeError,ValueError,UnicodeDecodeError):
            self.reply(400,{"status":"INVALID_REQUEST","formed":False});return
        status,permit=validate(payload.get("envelope"))
        if status!="VERIFIED":
            self.reply(403,{"status":status,"formed":False});return
        if payload.get("action_binding_hash")!=permit.action_binding_hash:
            self.reply(403,{"status":"ACTION_BINDING_MISMATCH","formed":False});return
        with closing(connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO external_effects VALUES(?,?,?)",
                           (permit.signature,permit.action_binding_hash,route))
                db.execute("COMMIT")
            except sqlite3.IntegrityError:
                db.execute("ROLLBACK")
                self.reply(409,{"status":"REPLAY_REFUSED","formed":False});return
        self.reply(200,{"status":"WITNESSED_CONSEQUENCE_FORMED","formed":True})

    def reply(self,code,payload):
        data=json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self,*args):pass

if __name__=="__main__":
    with closing(connect()):pass
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
