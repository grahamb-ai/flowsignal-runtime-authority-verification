"""FS-RAW-DENIAL-001 test-only source-owned online authority service.

Runs as a separate loopback process with its own SQLite version ledger.
Writer and reader test tokens are independent TEST fixtures; there is no
production IAM, durable consensus, or guarantee that upstream mutations
are automatically published to this service.
"""
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import json,os,sqlite3
from contextlib import closing

DB=Path(os.environ["FS_RAI_SOURCE_DB"])
READ_TOKEN=os.environ["FS_RAI_SOURCE_READ_TOKEN"]
WRITE_TOKEN=os.environ["FS_RAI_SOURCE_ADMIN_TOKEN"]
INITIAL=int(os.environ["FS_RAI_SOURCE_INITIAL_VERSION"])

def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    return sqlite3.connect(str(DB),timeout=5,isolation_level=None)

def init():
    with closing(connect()) as c:
        c.execute("CREATE TABLE IF NOT EXISTS authority_version "
                  "(id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL)")
        c.execute("INSERT OR IGNORE INTO authority_version(id,version) VALUES(1,?)",(INITIAL,))

class Handler(BaseHTTPRequestHandler):
    def send_json(self,code,obj):
        raw=json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path!="/current":
            self.send_json(404,{"error":"UNKNOWN_PATH"});return
        if self.headers.get("X-Authority-Read-Token")!=READ_TOKEN:
            self.send_json(403,{"error":"NO_READ_AUTHORITY"});return
        with closing(connect()) as c:
            row=c.execute("SELECT version FROM authority_version WHERE id=1").fetchone()
        if row is None:
            self.send_json(503,{"error":"STATE_MISSING"});return
        self.send_json(200,{"version":row[0]})

    def do_POST(self):
        if self.path!="/advance":
            self.send_json(404,{"error":"UNKNOWN_PATH"});return
        if self.headers.get("X-Authority-Admin-Token")!=WRITE_TOKEN:
            self.send_json(403,{"error":"NO_ADMIN_AUTHORITY"});return
        n=int(self.headers.get("Content-Length","0"))
        if n<=0 or n>256:
            self.send_json(400,{"error":"INVALID_UPDATE"});return
        try:
            obj=json.loads(self.rfile.read(n))
            version=obj["version"]
            if type(version) is not int or version<1:
                raise ValueError("invalid version")
        except (TypeError,KeyError,ValueError):
            self.send_json(400,{"error":"INVALID_UPDATE"});return
        with closing(connect()) as c:
            c.execute("BEGIN IMMEDIATE")
            current=c.execute("SELECT version FROM authority_version WHERE id=1").fetchone()[0]
            if version<=current:
                c.execute("ROLLBACK")
                self.send_json(409,{"error":"NON_MONOTONIC_UPDATE","version":current});return
            c.execute("UPDATE authority_version SET version=? WHERE id=1",(version,))
            c.execute("COMMIT")
        self.send_json(200,{"version":version})

    def log_message(self,*args):pass

if __name__=="__main__":
    init()
    server=HTTPServer(("127.0.0.1",0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
