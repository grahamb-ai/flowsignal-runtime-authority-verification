"""Independent retry CLIENT PROCESS for the localhost test actuator."""
import json,sys,time
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

base,route,grant_path,release_path=sys.argv[1:]
deadline=time.monotonic()+10
while not Path(release_path).exists():
    if time.monotonic()>deadline:
        print(json.dumps({"status":"NO_RELEASE"}),flush=True)
        sys.exit(2)
    time.sleep(0.005)
payload=Path(grant_path).read_bytes()
try:
    req=Request(base+route,data=payload,method="POST",
        headers={"Content-Type":"application/json"})
    with urlopen(req,timeout=6) as response:
        result=json.loads(response.read())
        print(json.dumps({"http":response.status,"result":result}),flush=True)
except HTTPError as error:
    print(json.dumps({"http":error.code,"result":json.loads(error.read())}),flush=True)
except (URLError,OSError,ValueError,TimeoutError) as exc:
    # Lost response is NOT proof of non-formation.
    print(json.dumps({"http":None,"result":{"status":"TRANSPORT_UNRESOLVED",
                                        "error_type":type(exc).__name__}}),flush=True)
