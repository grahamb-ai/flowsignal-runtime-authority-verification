"""FS-RAW-DENIAL-001: two source service processes sharing ONE authority
ledger, plus a separately characterized restored-database fork.

The common SQLite database is a *single authoritative reference store*.
This is single-host and not a distributed consensus/HA guarantee.
"""
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import json,os,shutil,sqlite3,time
import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_online_authority import start,stop
from test_fs_raw_denial_001_parallel_contention import source_env,actuator_env,grant_payload
from test_fs_raw_denial_001_dual_executor_contention import concurrent_requests
from test_fs_raw_denial_001_rai_external_actuator import post

@pytest.fixture(autouse=True)
def isolated_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def observed(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route "
                         "FROM committed_effects").fetchall()

def start_pair(db):
    source,source_url=start("fs_raw_denial_001_contention_server.py",source_env(db))
    actuator,actuator_url=start("fs_raw_denial_001_contention_server.py",
                                actuator_env(db,source_url))
    return source,source_url,actuator,actuator_url

def close(*processes):
    for p in processes:
        if p.poll() is None:stop(p)

def test_two_authority_frontends_share_one_commitment_ledger(tmp_path):
    db=tmp_path/"canonical-authority.sqlite3"
    s1,u1,a1,v1=start_pair(db)
    s2,u2,a2,v2=start_pair(db)
    try:
        permit,grant=grant_payload(tmp_path)
        responses=concurrent_requests([v1,v2],grant,tmp_path/"clients",count=16)
        assert sorted(r["http"] for r in responses)==[200]+[409]*15,responses
        assert len(observed(db))==1
        assert observed(db)[0][:2]==(permit.signature,permit.action_binding_hash)
        # One source process stops. The OTHER still consults the same ledger.
        stop(s1)
        envelope=json.loads(grant.read_text())["envelope"]
        code,result=post((v2,db),"/execute-b",envelope,permit.action_binding_hash)
        assert (code,result["status"])==(409,"REPLAY_REFUSED")
        assert len(observed(db))==1
    finally:
        close(s1,s2,a1,a2)

def test_restored_independent_database_can_still_duplicate_without_external_anchor(tmp_path):
    db=tmp_path/"canonical-authority.sqlite3"
    s1,u1,a1,v1=start_pair(db)
    rogue=None
    try:
        permit,grant=grant_payload(tmp_path)
        snapshot=tmp_path/"restored-old-copy.sqlite3"
        # Initialised before the first commitment; the snapshot lacks its record.
        shutil.copyfile(db,snapshot)
        envelope=json.loads(grant.read_text())["envelope"]
        assert post((v1,db),"/execute-a",envelope,permit.action_binding_hash)[0]==200
        assert len(observed(db))==1
        s2,u2,a2,v2=start_pair(snapshot)
        rogue=(s2,a2)
        code,result=post((v2,snapshot),"/execute-b",envelope,permit.action_binding_hash)
        assert (code,result["status"])==(200,"CONSEQUENCE_FORMED")
        assert len(observed(snapshot))==1
        assert observed(db)[0][0]==observed(snapshot)[0][0]==permit.signature
        # INTENTIONAL unresolved rollback risk characterization, NOT safety PASS.
    finally:
        close(s1,a1)
        if rogue is not None:close(*rogue)
