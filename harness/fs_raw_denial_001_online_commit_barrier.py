"""Deliberately paused test-only online authority lookup before commit.

The barrier lets the test revoke authority AFTER the actuator's source lookup
and BEFORE it enters its SQLite consequence-write transaction.
This is not deployed code, a real payment, or a real external authority service.
"""
from pathlib import Path
import os,time
import fs_raw_denial_001_online_actuator as online
from http.server import HTTPServer

previous=online.verify_online
barrier=Path(os.environ["FS_RAI_TEST_BARRIER"])

def check_with_pause(envelope):
    outcome=previous(envelope)
    if outcome[0]=="VERIFIED":
        barrier.mkdir(parents=True,exist_ok=True)
        (barrier/"looked-up").write_text("ready")
        deadline=time.monotonic()+8
        while not (barrier/"continue").exists():
            if time.monotonic()>deadline:
                return "TEST_BARRIER_TIMED_OUT",None
            time.sleep(0.01)
    return outcome

online.actuator.validate=check_with_pause

if __name__=="__main__":
    with online.actuator.connect():pass
    server=HTTPServer(("127.0.0.1",0),online.actuator.Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
