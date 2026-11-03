"""FS-RAW-DENIAL-001 reference forwarding actuator.

The actuator first makes an online freshness check (which can race); the
source-owned /commit endpoint performs the authoritative final check and
synthetic consequence write in one local SQLite transaction. A test-only
barrier permits deterministic revocation after lookup and before commit.
"""
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
import json,os,time

import fs_raw_denial_001_online_actuator as online

SOURCE=os.environ["FS_RAI_AUTHORITY_SOURCE_URL"].rstrip("/")
COMMIT_TOKEN=os.environ["FS_RAI_SOURCE_COMMIT_TOKEN"]
BARRIER=os.environ.get("FS_RAI_TEST_BARRIER")

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/execute-a","/execute-b"):
            self.reply(404,{"status":"UNKNOWN_ROUTE","formed":False});return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=12000:
                raise ValueError("bad length")
            payload=json.loads(self.rfile.read(n))
            if not isinstance(payload,dict):
                raise ValueError("bad request")
        except (TypeError,ValueError,UnicodeDecodeError):
            self.reply(400,{"status":"INVALID_REQUEST","formed":False});return
        status,permit=online.verify_online(payload.get("envelope"))
        if status!="VERIFIED":
            self.reply(403,{"status":status,"formed":False});return
        if payload.get("action_binding_hash")!=permit.action_binding_hash:
            self.reply(403,{"status":"EXECUTION_BINDING_MISMATCH","formed":False});return
        if BARRIER:
            barrier=Path(BARRIER)
            barrier.mkdir(parents=True,exist_ok=True)
            (barrier/"looked-up").write_text("ready")
            deadline=time.monotonic()+8
            while not (barrier/"continue").exists():
                if time.monotonic()>deadline:
                    self.reply(503,{"status":"TEST_BARRIER_TIMED_OUT","formed":False});return
                time.sleep(0.01)
        payload["route"]=self.path
        request=Request(SOURCE+"/commit",data=json.dumps(payload).encode(),
            method="POST",headers={
                "Content-Type":"application/json",
                "X-Authority-Commit-Token":COMMIT_TOKEN,
            })
        try:
            with urlopen(request,timeout=3) as response:
                result=json.loads(response.read())
                self.reply(response.status,result)
        except HTTPError as error:
            self.reply(error.code,json.loads(error.read()))
        except (URLError,OSError,TimeoutError,ValueError):
            # An indeterminate transport error is NOT proof of non-formation.
            self.reply(503,{"status":"COMMIT_OUTCOME_UNRESOLVED","formed":None})
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
