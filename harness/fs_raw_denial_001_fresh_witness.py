"""Reference witness-side online freshness check before synthetic commit.

The witness reads source authority after recovery preflight but before its own
SQLite insert. This closes the SPECIFIC deterministic test window, not the
check-to-witness-commit race or a distributed atomicity claim.
"""
from http.server import HTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from contextlib import closing
import json,os
import fs_raw_denial_001_independent_witness as witness

SOURCE=os.environ["FS_RAI_WITNESS_AUTHORITY_URL"].rstrip("/")
READ_TOKEN=os.environ["FS_RAI_WITNESS_AUTHORITY_READ_TOKEN"]
original_validate=witness.validate

def verify_with_current_authority(envelope):
    status,permit=original_validate(envelope)
    if status!="VERIFIED":
        return status,permit
    try:
        request=Request(SOURCE+"/current",
            headers={"X-Authority-Read-Token":READ_TOKEN})
        with urlopen(request,timeout=2) as response:
            if response.status!=200:
                return "AUTHORITY_UNAVAILABLE",None
            state=json.loads(response.read())
        version=state.get("version")
        if type(version) is not int:
            return "AUTHORITY_UNAVAILABLE",None
        if version!=permit.authority_state_version:
            return "AUTHORITY_STATE_STALE",None
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError):
        return "AUTHORITY_UNAVAILABLE",None
    return "VERIFIED",permit

witness.validate=verify_with_current_authority

if __name__=="__main__":
    with closing(witness.connect()):pass
    server=HTTPServer(("127.0.0.1",0),witness.Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
