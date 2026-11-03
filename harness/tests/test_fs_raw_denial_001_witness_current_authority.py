"""Candidate characterization of source revocation between recovery preflight
and independent witness commitment. Reference-only, not production atomicity.
"""
import json,os
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from app.engines.authority_store import advance_authority_state_version
from test_fs_raw_denial_001_online_authority import start,stop,advance_online
from test_fs_raw_denial_001_stranded_reconciliation import (
    prepare_outage,witness,TOKEN
)
from test_fs_raw_denial_001_rai_external_actuator import KEY
from test_fs_raw_denial_001_independent_witness import witness_rows

def test_witness_refuses_old_permit_when_source_version_advanced(tmp_path,witness):
    source,source_url,actuator,actuator_url,db,witness_db,permit,assertion=prepare_outage(tmp_path,witness)
    external=None
    try:
        version=advance_authority_state_version()
        assert version>permit.authority_state_version
        assert advance_online({"source_url":source_url},version)[0]==200
        env=os.environ.copy()
        env.update(FS_RAI_WITNESS_DB=str(witness_db),
            FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
            FS_RAI_EXTERNAL_LEDGER=str(witness_db),
            FS_RAI_BRIDGE_KEY=KEY.decode(),
            FS_RAI_WITNESS_AUTHORITY_URL=source_url,
            FS_RAI_WITNESS_AUTHORITY_READ_TOKEN="source-read-test-key")
        external,url=start("fs_raw_denial_001_fresh_witness.py",env)
        payload=json.dumps({"envelope":assertion,
            "action_binding_hash":permit.action_binding_hash,
            "route":"/execute-b"}).encode()
        request=Request(url+"/commit",data=payload,method="POST",
            headers={"Content-Type":"application/json",
                     "X-Witness-Commit-Token":TOKEN})
        try:
            with urlopen(request,timeout=5) as response:
                code=response.status
                result=json.loads(response.read())
        except HTTPError as response:
            code=response.code
            result=json.loads(response.read())
        assert (code,result["status"])==(403,"AUTHORITY_STATE_STALE")
        assert witness_rows(witness_db)==[]
    finally:
        for process in (external,actuator,source):
            if process is not None and process.poll() is None:
                stop(process)
