"""FS-RAW-DENIAL-001 actuator with online authority-source read.

This composes the existing RAI/bridge permit checks and local SQLite ledger
with a fresh HTTP query to a separately running SOURCE authority service
before invoking the existing actuator commit path.

IMPORTANT: The HTTP lookup and actual SQLite consequence commit are NOT
atomic; revocation between them remains a testable TOCTOU window.
No real payment rail, external infrastructure or production identity isolation.
"""
import json,os
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from http.server import HTTPServer
import fs_raw_denial_001_rai_actuator as actuator

SOURCE=os.environ["FS_RAI_AUTHORITY_SOURCE_URL"].rstrip("/")
READ_TOKEN=os.environ["FS_RAI_SOURCE_READ_TOKEN"]
base_validate=actuator.validate

def verify_online(envelope):
    status,permit=base_validate(envelope)
    if status!="VERIFIED":
        return status,permit
    try:
        request=Request(SOURCE+"/current",headers={"X-Authority-Read-Token":READ_TOKEN})
        with urlopen(request,timeout=1.0) as response:
            if response.status!=200:
                return "AUTHORITY_SOURCE_UNAVAILABLE",None
            data=json.loads(response.read())
        source_version=data.get("version")
        if type(source_version) is not int:
            return "AUTHORITY_SOURCE_INVALID",None
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError):
        return "AUTHORITY_SOURCE_UNAVAILABLE",None
    if source_version!=permit.authority_state_version:
        return "AUTHORITY_SOURCE_STALE",None
    return "VERIFIED",permit

actuator.validate=verify_online

if __name__=="__main__":
    with actuator.connect():pass
    server=HTTPServer(("127.0.0.1",0),actuator.Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
