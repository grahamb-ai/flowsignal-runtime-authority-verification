"""FS-RAW-DENIAL-001 isolated sandbox actuator, deliberately vulnerable mode.

Local loopback only. Independent OS process and separate SQLite consequence
journal; no payment API, external services or real transfers. /direct bypasses
the reference gateway by design, to establish a first-RED baseline.
"""
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DB=Path(os.environ["FS_DENIAL_SANDBOX_DB"])

def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(str(DB))
    con.execute("CREATE TABLE IF NOT EXISTS effects (id INTEGER PRIMARY KEY, target TEXT NOT NULL, action TEXT NOT NULL, route TEXT NOT NULL)")
    con.commit()
    return con

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        size=int(self.headers.get("Content-Length","0"))
        if size<1 or size>2048:
            self.reply(400,{"status":"INVALID_INPUT"});return
        try:
            payload=json.loads(self.rfile.read(size))
        except (ValueError,UnicodeDecodeError):
            self.reply(400,{"status":"INVALID_INPUT"});return
        if self.path=="/guarded":
            # Demonstrates refusal at the intended guarded port.
            self.reply(403,{"status":"REFUSED","effect_formed":False});return
        if self.path!="/direct":
            self.reply(404,{"status":"UNKNOWN_ROUTE","effect_formed":False});return
        if (payload.get("action"),payload.get("target"))!=("synthetic.transfer","sandbox:one"):
            self.reply(403,{"status":"REFUSED","effect_formed":False});return
        with connect() as db:
            db.execute("INSERT INTO effects(target,action,route) VALUES(?,?,?)",
                       ("sandbox:one","synthetic.transfer","direct"))
        self.reply(200,{"status":"ACCEPTED","effect_formed":True})
    def reply(self,status,payload):
        body=json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args):pass

if __name__=="__main__":
    with connect():pass
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
