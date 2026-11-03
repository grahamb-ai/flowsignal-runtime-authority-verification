"""FS-RAW-DENIAL-001 first RED: two source authority instances with
independent writable SQLite ledgers accept the SAME genuine RAI grant.

This is a deliberately misconfigured split-source localhost sandbox,
not a finding in FlowSignal's existing single-source payment executor.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import pytest
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_online_authority import start,stop
from test_fs_raw_denial_001_parallel_contention import source_env,actuator_env,grant_payload
from test_fs_raw_denial_001_rai_external_actuator import KEY,post

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def two_sources(tmp_path):
    processes=[]
    pairs=[]
    dbs=[]
    try:
        for i in range(2):
            db=tmp_path/f"source-{i}.sqlite3"
            src,url=start("fs_raw_denial_001_contention_server.py",source_env(db))
            processes.append(src)
            exe,exe_url=start("fs_raw_denial_001_contention_server.py",actuator_env(db,url))
            processes.append(exe)
            pairs.append((exe_url,db))
            dbs.append(db)
        yield pairs,dbs
    finally:
        for p in reversed(processes):
            if p.poll() is None:stop(p)

def effects(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as con:
        return con.execute(
            "SELECT permit_signature,action_binding_hash,route FROM committed_effects"
        ).fetchall()

def test_independent_sources_can_both_commit_same_signed_grant_first_red(two_sources,tmp_path):
    pairs,dbs=two_sources
    permit,grant_file=grant_payload(tmp_path)
    import json
    envelope=json.loads(grant_file.read_text())["envelope"]
    first=post(pairs[0],"/execute-a",envelope,permit.action_binding_hash)
    second=post(pairs[1],"/execute-b",envelope,permit.action_binding_hash)
    observed=[effects(db) for db in dbs]
    assert first[0]==200 and second[0]==200,(first,second)
    assert [len(e) for e in observed]==[1,1]
    assert observed[0][0][0]==observed[1][0][0]==permit.signature
    assert sum(len(e) for e in observed)==1, (
        "FIRST RED: two writable authority sources accepted the same "
        "genuine permit and independently committed the same modeled "
        f"consequence. Source rows={observed}."
    )
