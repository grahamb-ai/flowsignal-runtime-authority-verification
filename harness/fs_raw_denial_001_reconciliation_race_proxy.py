"""Test-only pause after recovery preflight and before witness commit.

The proxy's preflight has succeeded before we permit the witness request,
so the test can update authoritative source state in the interval.
"""
from pathlib import Path
import os,time
import fs_raw_denial_001_reconciliation_proxy as proxy
from http.server import HTTPServer

barrier=Path(os.environ["FS_RAI_RECOVERY_TEST_BARRIER"])
original=proxy.eligible_recovery

def checked_with_pause(envelope,binding):
    eligible=original(envelope,binding)
    if eligible:
        barrier.mkdir(parents=True,exist_ok=True)
        (barrier/"preflight-complete").write_text("1")
        deadline=time.monotonic()+8
        while not (barrier/"continue").exists():
            if time.monotonic()>=deadline:
                return False
            time.sleep(0.01)
    return eligible

proxy.eligible_recovery=checked_with_pause

if __name__=="__main__":
    server=HTTPServer(("127.0.0.1",0),proxy.Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
