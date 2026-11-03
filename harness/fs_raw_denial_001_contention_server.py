"""Threaded local source/actuator test servers with isolated imports.

Each role runs in its own Python process; importing the actuator's global
validator hook into the authority source would corrupt source verification.
"""
import os
from contextlib import closing
from http.server import ThreadingHTTPServer

ROLE=os.environ["FS_RAI_CONTENTION_ROLE"]
if __name__=="__main__":
    if ROLE in ("source","crash-source"):
        import fs_raw_denial_001_authority_source as authority
        import fs_raw_denial_001_recovery_source as recovery
        authority.init()
        with closing(authority.connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
                       "permit_signature TEXT PRIMARY KEY,"
                       "action_binding_hash TEXT NOT NULL,route TEXT NOT NULL)")
        if ROLE=="crash-source":
            import fs_raw_denial_001_crash_source as crash
            authority.connect=crash.instrumented_connect
        handler=recovery.Handler
        server=ThreadingHTTPServer(
            ("127.0.0.1",int(os.environ.get("FS_RAI_SOURCE_PORT","0"))),
            handler)
        server.dropped=True
    elif ROLE=="actuator":
        import fs_raw_denial_001_atomic_actuator as actuator
        server=ThreadingHTTPServer(("127.0.0.1",0),actuator.Handler)
    else:
        raise ValueError("unsupported test role")
    server.daemon_threads=True
    print(server.server_port,flush=True)
    server.serve_forever()
