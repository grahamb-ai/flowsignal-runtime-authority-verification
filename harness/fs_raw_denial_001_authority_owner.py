"""Single authority owner for the reference execution boundary.

The witness service OWNS the authority revision and synthetic consequence row.
Institutional revocation calls mutate this same DB through /revoke, rather than
advancing a process-local counter and *hoping* replication occurs.

Reference-only loopback service. Test header credentials and SQLite do not
establish production IAM, tamper resistance, external payment settlement,
or administrative protection of other institutional authority data.
"""
from contextlib import closing
from http.server import ThreadingHTTPServer
import json
import os

import fs_raw_denial_001_authority_source as authority
import fs_raw_denial_001_atomic_witness as witness

ADMIN_TOKEN=os.environ["FS_RAI_SOURCE_ADMIN_TOKEN"]

class Handler(witness.Handler):
    def do_POST(self):
        if self.path=="/advance":
            # An arbitrary caller-supplied version must not establish authority.
            self.send_json(404,{"status":"NOT_AUTHORITY_MUTATION_API"});return
        if self.path!="/revoke":
            return super().do_POST()
        if self.headers.get("X-Authority-Admin-Token")!=ADMIN_TOKEN:
            self.send_json(403,{"status":"NO_MUTATION_AUTHORITY"});return
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size<1 or size>128:
                raise ValueError("bad mutation")
            value=json.loads(self.rfile.read(size))
            if not isinstance(value,dict) or set(value)!={"reason"}:
                raise ValueError("bad fields")
            if not isinstance(value["reason"],str) or not (1<=len(value["reason"])<=80):
                raise ValueError("bad reason")
        except (TypeError,ValueError,UnicodeDecodeError):
            self.send_json(400,{"status":"INVALID_MUTATION"});return
        with closing(authority.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT version FROM authority_version WHERE id=1").fetchone()
            if row is None:
                db.execute("ROLLBACK")
                self.send_json(503,{"status":"AUTHORITY_UNAVAILABLE"});return
            version=row[0]+1
            db.execute("UPDATE authority_version SET version=? WHERE id=1",(version,))
            db.execute("COMMIT")
        self.send_json(200,{"status":"AUTHORITY_REVOKED","version":version})

if __name__=="__main__":
    authority.init()
    with closing(authority.connect()) as db:
        db.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
                   "permit_signature TEXT PRIMARY KEY,"
                   "action_binding_hash TEXT NOT NULL,"
                   "route TEXT NOT NULL)")
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    server.daemon_threads=True
    print(server.server_port,flush=True)
    server.serve_forever()
