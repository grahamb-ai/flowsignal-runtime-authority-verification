"""Multi-threaded LOCAL reference server; same authority and SQLite code.

Purpose: stop HTTPServer's sequential request handling from masking genuine
client contention. Not production concurrency, IAM or external payments.
"""
import os
from contextlib import closing
from http.server import ThreadingHTTPServer
import fs_raw_denial_001_authority_source as authority
import fs_raw_denial_001_atomic_source as atomic
import fs_raw_denial_001_recovery_source as recovery
import fs_raw_denial_001_atomic_actuator as actuator

ROLE=os.environ["FS_RAI_CONTENTION_ROLE"]
if __name__=="__main__":
    if ROLE in ("source","crash-source"):
        authority.init()
        with closing(authority.connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
                       "permit_signature TEXT PRIMARY KEY,"
                       "action_binding_hash TEXT NOT NULL,route TEXT NOT NULL)")
        if ROLE=="crash-source":
            import fs_raw_denial_001_crash_source as crash
            authority.connect=crash.instrumented_connect
            handler=recovery.Handler
        else:
            handler=recovery.Handler
        server=ThreadingHTTPServer(
            ("127.0.0.1",int(os.environ.get("FS_RAI_SOURCE_PORT","0"))),
            handler)
        server.dropped=True
    elif ROLE=="actuator":
        server=ThreadingHTTPServer(("127.0.0.1",0),actuator.Handler)
    else:
        raise ValueError("unsupported test role")
    server.daemon_threads=True
    print(server.server_port,flush=True)
    server.serve_forever()
