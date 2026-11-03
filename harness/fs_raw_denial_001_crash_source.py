"""FS-RAW-DENIAL-001 fault injection at SQLite COMMIT boundary.

Local-only reference test. A separate source process exits immediately before
or after its synthetic consequence COMMIT. Tests independently inspect SQLite.
This does not model power loss, fsync or external financial settlement.
"""
import os
import sqlite3
from contextlib import closing
from http.server import HTTPServer

import fs_raw_denial_001_authority_source as authority
import fs_raw_denial_001_recovery_source as recovery

CRASH_POINT=os.environ["FS_RAI_TEST_CRASH_POINT"]

class CrashConnection(sqlite3.Connection):
    def execute(self, sql, parameters=()):
        statement=sql.strip().upper()
        if statement=="BEGIN IMMEDIATE":
            self._effect_pending=False
        if statement.startswith("INSERT INTO COMMITTED_EFFECTS"):
            self._effect_pending=True
        if statement=="COMMIT" and getattr(self,"_effect_pending",False):
            if CRASH_POINT=="before":
                os._exit(91)
            result=super().execute(sql,parameters)
            if CRASH_POINT=="after":
                os._exit(92)
            return result
        return super().execute(sql,parameters)

def instrumented_connect():
    db=os.environ["FS_RAI_SOURCE_DB"]
    return sqlite3.connect(db,timeout=5,isolation_level=None,factory=CrashConnection)

if __name__=="__main__":
    authority.init()
    with closing(authority.connect()) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
            "permit_signature TEXT PRIMARY KEY,action_binding_hash TEXT NOT NULL,"
            "route TEXT NOT NULL)")
    authority.connect=instrumented_connect
    server=HTTPServer(("127.0.0.1",int(os.environ.get("FS_RAI_SOURCE_PORT","0"))),recovery.Handler)
    server.dropped=True  # Do not also inject lost ACK; only process exit.
    print(server.server_port,flush=True)
    server.serve_forever()
