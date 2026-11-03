"""Reference recovery server: preserves source-owned local commit while
supporting authenticated lookup after one lost HTTP acknowledgement.
The effect is synthetic and recorded in a local SQLite database.
"""
import json
import os
import socket
from contextlib import closing
from http.server import HTTPServer
from urllib.parse import parse_qs, urlsplit

import fs_raw_denial_001_atomic_source as atomic
import fs_raw_denial_001_authority_source as authority

class Handler(atomic.Handler):
    def do_GET(self):
        parsed=urlsplit(self.path)
        if parsed.path!="/outcome":
            return super().do_GET()
        if self.headers.get("X-Authority-Read-Token")!=authority.READ_TOKEN:
            self.send_json(403,{"status":"NOT_AUTHORIZED"});return
        keys=parse_qs(parsed.query).get("signature",[])
        if len(keys)!=1 or not keys[0] or len(keys[0])>256:
            self.send_json(400,{"status":"INVALID_LOOKUP"});return
        with closing(authority.connect()) as conn:
            row=conn.execute(
                "SELECT permit_signature,action_binding_hash,route "
                "FROM committed_effects WHERE permit_signature=?",
                (keys[0],)).fetchone()
        if row is None:
            self.send_json(404,{"status":"OUTCOME_NOT_RECORDED","formed":None});return
        self.send_json(200,{"status":"CONSEQUENCE_FORMED","formed":True,
            "permit_signature":row[0],"action_binding_hash":row[1],
            "route":row[2]})

    def send_json(self,code,obj):
        if code==200 and obj.get("status")=="CONSEQUENCE_FORMED" and not getattr(self.server,"dropped",False):
            self.server.dropped=True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return
        return super().send_json(code,obj)

if __name__=="__main__":
    authority.init()
    with closing(authority.connect()) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
            "permit_signature TEXT PRIMARY KEY,action_binding_hash TEXT NOT NULL,"
            "route TEXT NOT NULL)")
    port=int(os.environ.get("FS_RAI_SOURCE_PORT","0"))
    server=HTTPServer(("127.0.0.1",port),Handler)
    server.dropped=os.environ.get("FS_RAI_TEST_DROP_ACK","1")!="1"
    print(server.server_port,flush=True)
    server.serve_forever()
