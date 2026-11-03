"""Independent test client process for source-owned synthetic commits.

Each invocation waits for its own release gate, then POSTs an existing signed
RAI assertion to the independently running localhost authority source. One
result file per process avoids sharing Python state or result channels.
"""
import json,os,sys,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from http.client import RemoteDisconnected

def main():
    config=json.loads(Path(sys.argv[1]).read_text())
    gate=Path(config["gate"])
    deadline=time.monotonic()+12
    while not gate.exists():
        if time.monotonic()>deadline:
            raise RuntimeError("client gate timeout")
        time.sleep(0.005)
    payload=json.dumps({"envelope":config["envelope"],
                        "action_binding_hash":config["action_binding_hash"],
                        "route":config["route"]}).encode()
    request=Request(config["source_url"]+"/commit",data=payload,
        method="POST",headers={
            "Content-Type":"application/json",
            "X-Authority-Commit-Token":config["commit_token"]})
    try:
        with urlopen(request,timeout=5) as response:
            result={"http":response.status,"body":json.loads(response.read())}
    except HTTPError as error:
        result={"http":error.code,"body":json.loads(error.read())}
    except (URLError,RemoteDisconnected,TimeoutError,OSError) as error:
        result={"http":None,"body":{"status":"COMMIT_OUTCOME_UNRESOLVED",
                                    "formed":None,"error_type":type(error).__name__}}
    Path(config["output"]).write_text(json.dumps(result))
if __name__=="__main__":
    main()
