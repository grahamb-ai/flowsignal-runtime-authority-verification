"""Fault-injected witness: pause only AFTER successful current-authority check
and BEFORE the modeled SQLite consequence write. Local test only.
"""
from http.server import HTTPServer
from pathlib import Path
import os,time
import fs_raw_denial_001_fresh_witness as fresh

barrier=Path(os.environ["FS_RAI_WITNESS_COMMIT_BARRIER"])
original=fresh.witness.validate

def validated_then_paused(envelope):
    result=original(envelope)
    if result[0]=="VERIFIED":
        barrier.mkdir(parents=True,exist_ok=True)
        (barrier/"authority-checked").write_text("ready")
        deadline=time.monotonic()+8
        while not (barrier/"continue").exists():
            if time.monotonic()>deadline:
                return "TEST_BARRIER_EXPIRED",None
            time.sleep(0.01)
    return result

fresh.witness.validate=validated_then_paused

if __name__=="__main__":
    from contextlib import closing
    with closing(fresh.witness.connect()):pass
    server=HTTPServer(("127.0.0.1",0),fresh.witness.Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
