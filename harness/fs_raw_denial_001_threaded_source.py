"""FS-RAW-DENIAL-001: threaded localhost source for concurrent client tests.

Uses the unchanged source-owned SQLite authority/effect transaction.
ThreadingHTTPServer permits requests to contend; unlike HTTPServer it does
not serialize incoming client requests before the database.
"""
import os
from contextlib import closing
from http.server import ThreadingHTTPServer
import fs_raw_denial_001_authority_source as authority
import fs_raw_denial_001_recovery_source as recovery

if __name__=="__main__":
    authority.init()
    with closing(authority.connect()) as db:
        db.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
                   "permit_signature TEXT PRIMARY KEY,"
                   "action_binding_hash TEXT NOT NULL,route TEXT NOT NULL)")
    server=ThreadingHTTPServer(("127.0.0.1",int(os.environ.get("FS_RAI_SOURCE_PORT","0"))),recovery.Handler)
    server.dropped=True
    print(server.server_port,flush=True)
    server.serve_forever()
