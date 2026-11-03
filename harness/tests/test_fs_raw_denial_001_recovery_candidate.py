"""FS-RAW-DENIAL-001 recovery candidate: authenticated outcome retrieval,
replay and source-service restart using a persistent local SQLite ledger.

No external payment, production credentials or third-party evidence custodian.
"""
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import json
import os
from urllib.parse import urlsplit

from test_fs_raw_denial_001_ack_loss_red import (
    services,commit_with_lost_ack,ask_outcome,recorded,
    READER,ADMIN,KEY,TOKEN,
)
from test_fs_raw_denial_001_online_authority import start,stop
from test_fs_raw_denial_001_rai_external_actuator import post
from app.engines.authority_store import get_authority_state_version

def raw_lookup(services,signature,token):
    req=Request(services["source_url"]+"/outcome?signature="+signature,
        headers={"X-Authority-Read-Token":token})
    try:
        with urlopen(req,timeout=3) as r:
            return r.status,json.loads(r.read())
    except HTTPError as r:
        return r.code,json.loads(r.read())

def test_lost_ack_authenticated_recovery_matches_independent_ledger(services):
    permit,_,code,result=commit_with_lost_ack(services)
    assert code==503 and result["formed"] is None
    status,outcome=ask_outcome(services,permit.signature)
    assert status==200
    assert outcome["formed"] is True
    assert outcome["action_binding_hash"]==permit.action_binding_hash
    assert outcome["route"]=="/execute-a"
    assert recorded(services["db"])==[(
        permit.signature,permit.action_binding_hash,"/execute-a")]

def test_recovery_requires_read_authority(services):
    permit,_,_,_=commit_with_lost_ack(services)
    code,response=raw_lookup(services,permit.signature,"invalid-reader")
    assert (code,response["status"])==(403,"NOT_AUTHORIZED")
    assert len(recorded(services["db"]))==1

def test_unknown_signature_is_unresolved_not_proof_of_nonformation(services):
    code,response=raw_lookup(services,"nonexistent-reference-signature",READER)
    assert (code,response["status"])==(404,"OUTCOME_NOT_RECORDED")
    assert response["formed"] is None

def test_replay_after_acknowledgement_loss_does_not_duplicate_effect(services):
    permit,envelope,code,_=commit_with_lost_ack(services)
    assert code==503
    retried,result=post(services["pair"],"/execute-b",envelope,permit.action_binding_hash)
    assert (retried,result["status"])==(409,"REPLAY_REFUSED")
    assert recorded(services["db"])==[(
        permit.signature,permit.action_binding_hash,"/execute-a")]

def test_outcome_survives_source_restart_and_replay_is_refused(services):
    permit,envelope,code,_=commit_with_lost_ack(services)
    assert code==503
    stop(services["source"])
    original_port=urlsplit(services["source_url"]).port
    env=os.environ.copy()
    env.update(FS_RAI_SOURCE_DB=str(services["db"]),
        FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,
        FS_RAI_SOURCE_COMMIT_TOKEN=TOKEN,
        FS_RAI_SOURCE_INITIAL_VERSION=str(get_authority_state_version()),
        FS_RAI_EXTERNAL_LEDGER=str(services["db"]),
        FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_SOURCE_PORT=str(original_port))
    restarted,new_url=start("fs_raw_denial_001_recovery_source.py",env)
    try:
        assert new_url==services["source_url"]
        status,outcome=ask_outcome(services,permit.signature)
        assert (status,outcome["status"])==(200,"CONSEQUENCE_FORMED")
        retried,result=post(services["pair"],"/execute-b",envelope,permit.action_binding_hash)
        assert (retried,result["status"])==(409,"REPLAY_REFUSED")
        assert recorded(services["db"])==[(
            permit.signature,permit.action_binding_hash,"/execute-a")]
    finally:
        stop(restarted)
