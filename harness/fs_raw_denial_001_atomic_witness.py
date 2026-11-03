"""Synthetic single-owner witness: version and modeled effect share SQLite.

Separate localhost process, test-only credentials, no external settlement.
"""
from contextlib import closing
from http.server import HTTPServer
import json,os,sqlite3

import fs_raw_denial_001_authority_source as authority
import fs_raw_denial_001_rai_actuator as permits

COMMIT_TOKEN=os.environ["FS_RAI_WITNESS_COMMIT_TOKEN"]

class Handler(authority.Handler):
    def do_POST(self):
        if self.path!="/commit":
            return super().do_POST()
        if self.headers.get("X-Witness-Commit-Token")!=COMMIT_TOKEN:
            self.send_json(403,{"status":"UNAUTHORIZED_WITNESS_CALLER","formed":False})
            return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=12000:raise ValueError("size")
            body=json.loads(self.rfile.read(n))
            if not isinstance(body,dict):raise ValueError("payload")
            route=body.get("route")
            if route not in ("/execute-a","/execute-b"):raise ValueError("route")
        except (ValueError,TypeError,UnicodeDecodeError):
            self.send_json(400,{"status":"INVALID_REQUEST","formed":False});return
        status,permit=permits.validate(body.get("envelope"))
        if status!="VERIFIED":
            self.send_json(403,{"status":status,"formed":False});return
        if body.get("action_binding_hash")!=permit.action_binding_hash:
            self.send_json(403,{"status":"ACTION_BINDING_MISMATCH","formed":False});return
        with closing(authority.connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                current=db.execute("SELECT version FROM authority_version WHERE id=1").fetchone()
                if current is None:
                    db.execute("ROLLBACK")
                    self.send_json(403,{"status":"AUTHORITY_UNAVAILABLE","formed":False});return
                if current[0]!=permit.authority_state_version:
                    db.execute("ROLLBACK")
                    self.send_json(403,{"status":"AUTHORITY_STATE_STALE","formed":False});return
                db.execute("INSERT INTO committed_effects "
                    "(permit_signature,action_binding_hash,route) VALUES(?,?,?)",
                    (permit.signature,permit.action_binding_hash,route))
                db.execute("COMMIT")
            except sqlite3.IntegrityError:
                db.execute("ROLLBACK")
                self.send_json(409,{"status":"REPLAY_REFUSED","formed":False});return
        self.send_json(200,{"status":"WITNESSED_CONSEQUENCE_FORMED","formed":True})

if __name__=="__main__":
    authority.init()
    with closing(authority.connect()) as db:
        db.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
                   "permit_signature TEXT PRIMARY KEY,action_binding_hash TEXT NOT NULL,"
                   "route TEXT NOT NULL)")
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
