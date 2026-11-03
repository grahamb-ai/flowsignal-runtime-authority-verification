"""FS-RAW-DENIAL-001: local reference source with surviving commit anchor.

Authority state remains in main SQLite database. Synthetic effects are claimed
in a *separate* anchor SQLite database, attached to the same source connection.
The anchor survives restoration of ONLY the authority DB. This is not external
settlement, tamper-proof storage, distributed consensus or cross-host atomicity.
"""
from contextlib import closing
from datetime import datetime,timezone
from http.server import HTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import json,os,sqlite3

import fs_raw_denial_001_authority_source as authority
import fs_raw_denial_001_rai_actuator as permits

ANCHOR=Path(os.environ["FS_RAI_SURVIVING_ANCHOR_DB"])
COMMIT_TOKEN=os.environ["FS_RAI_SOURCE_COMMIT_TOKEN"]

def connected():
    conn=authority.connect()
    conn.execute("ATTACH DATABASE ? AS anchor_db",(str(ANCHOR),))
    return conn

def init_anchor():
    ANCHOR.parent.mkdir(parents=True,exist_ok=True)
    with closing(connected()) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS anchor_db.committed_effects ("
            "permit_signature TEXT PRIMARY KEY,action_binding_hash TEXT NOT NULL,"
            "route TEXT NOT NULL)")

class Handler(authority.Handler):
    def do_GET(self):
        target=urlsplit(self.path)
        if target.path!="/outcome":
            return super().do_GET()
        if self.headers.get("X-Authority-Read-Token")!=authority.READ_TOKEN:
            self.send_json(403,{"status":"NOT_AUTHORIZED"});return
        signatures=parse_qs(target.query).get("signature",[])
        if len(signatures)!=1 or not signatures[0] or len(signatures[0])>256:
            self.send_json(400,{"status":"INVALID_QUERY"});return
        with closing(connected()) as c:
            row=c.execute("SELECT permit_signature,action_binding_hash,route "
                 "FROM anchor_db.committed_effects WHERE permit_signature=?",
                 (signatures[0],)).fetchone()
        if row is None:
            self.send_json(404,{"status":"OUTCOME_NOT_RECORDED","formed":None});return
        self.send_json(200,{"status":"CONSEQUENCE_FORMED","formed":True,
            "permit_signature":row[0],"action_binding_hash":row[1],"route":row[2]})

    def do_POST(self):
        if self.path!="/commit":
            return super().do_POST()
        if self.headers.get("X-Authority-Commit-Token")!=COMMIT_TOKEN:
            self.send_json(403,{"status":"COMMIT_CALLER_NOT_AUTHORISED","formed":False});return
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=12000:raise ValueError("invalid length")
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError("not a mapping")
            route=body.get("route")
            if route not in ("/execute-a","/execute-b"):raise ValueError("route")
        except (ValueError,TypeError,UnicodeDecodeError):
            self.send_json(400,{"status":"INVALID_REQUEST","formed":False});return

        status,permit=permits.validate(body.get("envelope"))
        if status!="VERIFIED":
            self.send_json(403,{"status":status,"formed":False});return
        if body.get("action_binding_hash")!=permit.action_binding_hash:
            self.send_json(403,{"status":"EXECUTION_BINDING_MISMATCH","formed":False});return
        with closing(connected()) as c:
            try:
                c.execute("BEGIN IMMEDIATE")
                current=c.execute("SELECT version FROM authority_version WHERE id=1").fetchone()
                if current is None:
                    c.execute("ROLLBACK")
                    self.send_json(403,{"status":"AUTHORITY_STATE_UNAVAILABLE","formed":False});return
                if current[0]!=permit.authority_state_version:
                    c.execute("ROLLBACK")
                    self.send_json(403,{"status":"AUTHORITY_STATE_STALE","formed":False});return
                c.execute("INSERT INTO anchor_db.committed_effects "
                    "(permit_signature,action_binding_hash,route) VALUES(?,?,?)",
                    (permit.signature,permit.action_binding_hash,route))
                c.execute("COMMIT")
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                self.send_json(409,{"status":"REPLAY_REFUSED","formed":False});return
        self.send_json(200,{"status":"CONSEQUENCE_FORMED","formed":True})

if __name__=="__main__":
    authority.init()
    init_anchor()
    server=HTTPServer(("127.0.0.1",int(os.environ.get("FS_RAI_SOURCE_PORT","0"))),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
