"""FS-RAW-DENIAL-001 source-owned atomic reference commitment.

The authority service owns both its monotonic version and a SYNTHETIC
consequence ledger in one local SQLite file. A separate actuator may request
a commitment, but cannot form this modeled consequence directly.

This proves only *local same-database* transactionality, not distributed
payment settlement, production service identity or cross-host authority.
"""
import json,os,sqlite3
from contextlib import closing
from http.server import HTTPServer

import fs_raw_denial_001_authority_source as source
import fs_raw_denial_001_rai_actuator as permit_verifier

COMMIT_TOKEN=os.environ["FS_RAI_SOURCE_COMMIT_TOKEN"]

class Handler(source.Handler):
    def do_POST(self):
        if self.path!="/commit":
            return super().do_POST()
        if self.headers.get("X-Authority-Commit-Token")!=COMMIT_TOKEN:
            self.send_json(403,{"status":"COMMIT_CALLER_NOT_AUTHORISED","formed":False});return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=12000:
                raise ValueError("bad length")
            payload=json.loads(self.rfile.read(n))
            if not isinstance(payload,dict):
                raise ValueError("bad request")
            envelope=payload.get("envelope")
            binding=payload.get("action_binding_hash")
            route=payload.get("route")
            if route not in ("/execute-a","/execute-b"):
                raise ValueError("unsupported route")
        except (TypeError,ValueError,UnicodeDecodeError):
            self.send_json(400,{"status":"INVALID_REQUEST","formed":False});return

        status,permit=permit_verifier.validate(envelope)
        if status!="VERIFIED":
            self.send_json(403,{"status":status,"formed":False});return
        if binding!=permit.action_binding_hash:
            self.send_json(403,{"status":"EXECUTION_BINDING_MISMATCH","formed":False});return
        with closing(source.connect()) as c:
            try:
                c.execute("BEGIN IMMEDIATE")
                row=c.execute("SELECT version FROM authority_version WHERE id=1").fetchone()
                if row is None:
                    c.execute("ROLLBACK")
                    self.send_json(403,{"status":"AUTHORITY_STATE_UNAVAILABLE","formed":False});return
                if row[0]!=permit.authority_state_version:
                    c.execute("ROLLBACK")
                    self.send_json(403,{"status":"AUTHORITY_STATE_STALE","formed":False});return
                c.execute("INSERT INTO committed_effects "
                    "(permit_signature,action_binding_hash,route) VALUES(?,?,?)",
                    (permit.signature,binding,route))
                c.execute("COMMIT")
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                self.send_json(409,{"status":"REPLAY_REFUSED","formed":False});return
        self.send_json(200,{"status":"CONSEQUENCE_FORMED","formed":True})

if __name__=="__main__":
    source.init()
    with closing(source.connect()) as c:
        c.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
            "permit_signature TEXT PRIMARY KEY,"
            "action_binding_hash TEXT NOT NULL,"
            "route TEXT NOT NULL)")
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
