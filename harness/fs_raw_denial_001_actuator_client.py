"""Independent local client calling one of TWO separate actuator processes.

The caller has no commit-source token; the actuator forwards a genuine RAI
permit and test bridge to a source-owned commit service. Local simulation only.
"""
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from http.client import RemoteDisconnected
import json,sys,time

def main():
    cfg=json.loads(Path(sys.argv[1]).read_text())
    gate=Path(cfg["gate"])
    deadline=time.monotonic()+10
    while not gate.exists():
        if time.monotonic()>deadline:raise RuntimeError("gate timeout")
        time.sleep(0.005)
    body=json.dumps({"envelope":cfg["envelope"],
                     "action_binding_hash":cfg["action_binding_hash"]}).encode()
    r=Request(cfg["actuator_url"]+cfg["route"],data=body,
              method="POST",headers={"Content-Type":"application/json"})
    try:
        with urlopen(r,timeout=6) as res:
            outcome={"code":res.status,"body":json.loads(res.read())}
    except HTTPError as err:
        outcome={"code":err.code,"body":json.loads(err.read())}
    except (URLError,RemoteDisconnected,TimeoutError,OSError) as err:
        outcome={"code":None,"body":{"status":"COMMIT_OUTCOME_UNRESOLVED",
                                     "formed":None,"error_type":type(err).__name__}}
    Path(cfg["output"]).write_text(json.dumps(outcome))

if __name__=="__main__":
    main()
