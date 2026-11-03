"""Test-only gateway into a separately owned consequence witness.

First obtains an ACCEPT from the local authority source via its existing
actuator route, then submits the same signed permit to the independent witness.
The witness alone owns the modeled EXTERNAL consequence. A local ACCEPT by
itself is NOT confirmation of external formation.

These two HTTP steps are not atomic. A failure in between is UNRESOLVED;
a previously formed witness consequence may cause local/witness divergence.
"""
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
import json,os

LOCAL=os.environ["FS_RAI_LOCAL_ACTUATOR_URL"].rstrip("/")
WITNESS=os.environ["FS_RAI_WITNESS_URL"].rstrip("/")
WITNESS_TOKEN=os.environ["FS_RAI_WITNESS_COMMIT_TOKEN"]

def post(url,payload,headers=None):
    request=Request(url,data=json.dumps(payload).encode(),method="POST",
        headers={"Content-Type":"application/json",**(headers or {})})
    try:
        with urlopen(request,timeout=4) as response:
            return response.status,json.loads(response.read())
    except HTTPError as err:
        return err.code,json.loads(err.read())

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/execute-a","/execute-b"):
            self.reply(404,{"status":"UNKNOWN_ROUTE","formed":None});return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=12000:raise ValueError("size")
            payload=json.loads(self.rfile.read(n))
            if not isinstance(payload,dict):raise ValueError("body")
        except (ValueError,TypeError,UnicodeDecodeError):
            self.reply(400,{"status":"INVALID_REQUEST","formed":False});return
        try:
            local_status,local_result=post(LOCAL+self.path,payload)
        except (URLError,OSError,TimeoutError,ValueError):
            self.reply(503,{"status":"LOCAL_COMMIT_OUTCOME_UNRESOLVED","formed":None});return
        if local_status!=200:
            self.reply(local_status,{"status":local_result.get("status","LOCAL_REFUSED"),
                "formed":False if local_status in (400,403,404,409) else None});return
        witness_payload=dict(payload,route=self.path)
        try:
            witness_status,witness_result=post(WITNESS+"/commit",witness_payload,
                {"X-Witness-Commit-Token":WITNESS_TOKEN})
        except (URLError,OSError,TimeoutError,ValueError):
            self.reply(503,{"status":"WITNESS_OUTCOME_UNRESOLVED","formed":None});return
        # The second step owns represented external formation. A local
        # consequence formed before witness refusal is not silently erased.
        self.reply(witness_status,witness_result)

    def reply(self,code,value):
        raw=json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self,*args):pass

if __name__=="__main__":
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
