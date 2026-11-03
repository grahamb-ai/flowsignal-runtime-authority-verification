"""Bounded reconciliation proxy for a locally committed but externally
unconfirmed reference operation.

On local replay refusal, verify genuine reference permit, authenticated local
commitment evidence, matching binding and currently published authority before
requesting a first external witness commit. This is TWO services and multiple
HTTP reads, NOT atomic authority/provider commitment or general saga recovery.
"""
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from urllib.parse import quote
import json,os
from fs_raw_denial_001_rai_actuator import validate

LOCAL=os.environ["FS_RAI_LOCAL_ACTUATOR_URL"].rstrip("/")
SOURCE=os.environ["FS_RAI_LOCAL_SOURCE_URL"].rstrip("/")
READ_TOKEN=os.environ["FS_RAI_SOURCE_READ_TOKEN"]
WITNESS=os.environ["FS_RAI_WITNESS_URL"].rstrip("/")
WITNESS_TOKEN=os.environ["FS_RAI_WITNESS_COMMIT_TOKEN"]

def post(url,payload,extra=None):
    r=Request(url,data=json.dumps(payload).encode(),method="POST",
        headers={"Content-Type":"application/json",**(extra or {})})
    try:
        with urlopen(r,timeout=3) as response:
            return response.status,json.loads(response.read())
    except HTTPError as err:
        return err.code,json.loads(err.read())

def read(url):
    r=Request(url,headers={"X-Authority-Read-Token":READ_TOKEN})
    try:
        with urlopen(r,timeout=3) as response:
            return response.status,json.loads(response.read())
    except HTTPError as err:
        return err.code,json.loads(err.read())

def eligible_recovery(envelope,binding):
    verified,permit=validate(envelope)
    if verified!="VERIFIED" or binding!=getattr(permit,"action_binding_hash",None):
        return False
    outcome_status,outcome=read(SOURCE+"/outcome?signature="+quote(permit.signature,safe=""))
    if outcome_status!=200 or outcome.get("status")!="CONSEQUENCE_FORMED":
        return False
    if outcome.get("action_binding_hash")!=permit.action_binding_hash:
        return False
    source_status,source_state=read(SOURCE+"/current")
    if source_status!=200 or source_state.get("version")!=permit.authority_state_version:
        return False
    return True

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/execute-a","/execute-b"):
            self.reply(404,{"status":"UNKNOWN_ROUTE","formed":None});return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=12000:raise ValueError("length")
            payload=json.loads(self.rfile.read(n))
            if not isinstance(payload,dict):raise ValueError("payload")
        except (TypeError,ValueError,UnicodeDecodeError):
            self.reply(400,{"status":"INVALID_REQUEST","formed":False});return
        try:
            code,local_result=post(LOCAL+self.path,payload)
            if code==409 and local_result.get("status")=="REPLAY_REFUSED":
                if not eligible_recovery(payload.get("envelope"),payload.get("action_binding_hash")):
                    self.reply(403,{"status":"RECOVERY_NOT_AUTHORIZED_OR_UNVERIFIED","formed":None});return
            elif code!=200:
                self.reply(code,{"status":local_result.get("status","LOCAL_REFUSED"),
                    "formed":False if code in (400,403,404) else None});return
            witness_payload=dict(payload,route=self.path)
            witness_code,witness_result=post(WITNESS+"/commit",witness_payload,
                {"X-Witness-Commit-Token":WITNESS_TOKEN})
            self.reply(witness_code,witness_result)
        except (URLError,OSError,TimeoutError,ValueError,KeyError):
            self.reply(503,{"status":"RECOVERY_OUTCOME_UNRESOLVED","formed":None})

    def reply(self,code,payload):
        raw=json.dumps(payload).encode()
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
