"""Test-only source service that commits locally then suppresses the HTTP
acknowledgement once. No real payment. Source-owned SQLite still commits.
"""
import os,socket
from http.server import HTTPServer
import fs_raw_denial_001_atomic_source as source

class Handler(source.Handler):
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
    source.source.init()
    from contextlib import closing
    with closing(source.source.connect()) as c:
        c.execute("CREATE TABLE IF NOT EXISTS committed_effects ("
                  "permit_signature TEXT PRIMARY KEY,"
                  "action_binding_hash TEXT NOT NULL,route TEXT NOT NULL)")
    server=HTTPServer(("127.0.0.1",0),Handler)
    server.dropped=False
    print(server.server_port,flush=True)
    server.serve_forever()
